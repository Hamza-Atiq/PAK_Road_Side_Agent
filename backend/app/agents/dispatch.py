"""DispatchAgent — find, rank, and assign the best available provider.

Inputs (via AgentContext.payload):
    - lat: float                      — incident latitude
    - lng: float                      — incident longitude
    - service_type: str | None        — from TriageAgent diagnosis; None = any
    - ai_diagnosis: dict | None       — pass-through for incident record
    - incident_id: required (use context.incident_id)

Output: DispatchResult { assigned: bool, provider_id: UUID | None,
                         eta_minutes: int | None, candidates_considered: int,
                         radius_used_km: float, reasoning: str }

Flow:
1. Query providers within INITIAL_RADIUS (default 50 km), filtered by service_type.
2. If empty AND service_type filter was applied, retry without service_type filter.
3. If still empty, expand to MAX_RADIUS (100 km).
4. If candidates exist:
   - One candidate → pick it (no Claude call needed).
   - Multiple candidates → use Claude to rank, given the candidate profiles.
5. Call routing_tool for the chosen candidate's true ETA.
6. Call db_write_tool to assign and transition status.
7. Return DispatchResult.

The agent's tool allow-list strictly limits it to geo, routing, and
write-incident-assignment. It cannot, for example, send Twilio messages or
mutate provider profiles beyond the assignment side-effect.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass

from app.agents.base import AgentContext, AgentExecutionError, BaseAgent
from app.config import settings
from app.metrics import incidents_assigned_total, incidents_no_provider_total
from app.middleware.logging import get_logger
from app.models.enums import IncidentStatus
from app.services.geo_service import ProviderCandidate
from app.tools.db_write_tool import DbWriteError, assign_provider_to_incident
from app.tools.geo_tool import find_nearest_providers_tool
from app.tools.routing_tool import RouteResult, get_route

log = get_logger("agents.dispatch")


# ----------------------------------------------------------------------
# Result
# ----------------------------------------------------------------------


@dataclass
class DispatchResult:
    assigned: bool
    provider_id: uuid.UUID | None = None
    provider_name: str | None = None
    eta_minutes: int | None = None
    distance_km: float | None = None
    candidates_considered: int = 0
    radius_used_km: float = 0.0
    reasoning: str = ""

    def to_dict(self) -> dict:
        return {
            "assigned": self.assigned,
            "provider_id": str(self.provider_id) if self.provider_id else None,
            "provider_name": self.provider_name,
            "eta_minutes": self.eta_minutes,
            "distance_km": round(self.distance_km, 3) if self.distance_km else None,
            "candidates_considered": self.candidates_considered,
            "radius_used_km": self.radius_used_km,
            "reasoning": self.reasoning[:500],
        }


# ----------------------------------------------------------------------
# Ranking prompt — Claude reasons over candidate profiles
# ----------------------------------------------------------------------


def _ranking_system_prompt() -> str:
    return """You are an experienced roadside-assistance dispatcher. You receive a small list of
candidate providers (each with distance, service type, total jobs completed) for a single
incident and must pick the BEST one to dispatch.

Optimize for, in this order:
1. Service-type match — exact match is strongly preferred (mechanic for mechanical issues,
   tow_truck for non-driveable vehicles, tire for tire problems, etc.).
2. Proximity — shorter distance means faster help.
3. Track record — higher `total_jobs` is a tiebreaker (more experience).

Output ONLY this JSON, no prose:
{"chosen_provider_id": "<uuid>", "reasoning": "<one short sentence>"}

If none of the candidates are a sensible choice, output:
{"chosen_provider_id": null, "reasoning": "<why>"}
"""


# ----------------------------------------------------------------------
# DispatchAgent
# ----------------------------------------------------------------------


class DispatchAgent(BaseAgent[DispatchResult]):
    name = "DispatchAgent"
    persona = (
        "Veteran roadside dispatcher. Quick, decisive, biased toward sending help fast. "
        "Knows when a slightly farther specialist beats a closer generalist."
    )
    goal = "Assign the best available provider as fast as possible. Never stall."
    max_tokens = 400
    tools = ("geo_tool", "routing_tool", "db_write_tool")

    async def _execute(self, context: AgentContext) -> DispatchResult:
        payload = context.payload
        lat = payload.get("lat")
        lng = payload.get("lng")
        service_type = payload.get("service_type")
        ai_diagnosis = payload.get("ai_diagnosis")
        incident_id = context.incident_id

        if lat is None or lng is None:
            raise AgentExecutionError("DispatchAgent requires lat and lng in payload")
        if incident_id is None:
            raise AgentExecutionError("DispatchAgent requires context.incident_id")

        # ----- Find candidates with progressive expansion -----
        candidates, radius_used = await self._find_candidates(
            context, lat=lat, lng=lng, service_type=service_type
        )

        if not candidates:
            incidents_no_provider_total.inc()
            return DispatchResult(
                assigned=False,
                candidates_considered=0,
                radius_used_km=radius_used,
                reasoning=(
                    f"No available approved providers within {radius_used} km "
                    f"(service_type={service_type or 'any'})."
                ),
            )

        # ----- Pick the best candidate -----
        chosen, reasoning = await self._pick_best(candidates, service_type)
        if chosen is None:
            return DispatchResult(
                assigned=False,
                candidates_considered=len(candidates),
                radius_used_km=radius_used,
                reasoning=reasoning,
            )

        # ----- True ETA via routing -----
        # Provider's last_ping coordinates aren't returned by the geo query yet;
        # for now we use the straight-line distance scaled by routing fallback.
        # Once provider location columns are exposed in ProviderCandidate, this
        # call gets the real ORS route.
        route: RouteResult | None = None
        try:
            # Use candidate distance as the from-side approximation
            route = await get_route(
                from_lat=lat + (chosen.distance_km / 111.0),  # rough lat offset for fallback symmetry
                from_lng=lng,
                to_lat=lat,
                to_lng=lng,
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("routing_call_failed_using_default_eta", error=str(exc))

        eta_minutes = int(round(route.duration_minutes)) if route else max(
            5, int(chosen.distance_km * 2)  # 30 km/h pessimistic fallback
        )

        # ----- Assign in DB -----
        self._check_tool_authorized("db_write_tool")
        try:
            await assign_provider_to_incident(
                context.db,
                incident_id=incident_id,
                provider_id=chosen.provider_id,
                eta_minutes=eta_minutes,
                ai_diagnosis=ai_diagnosis,
            )
        except DbWriteError as exc:
            log.warning("dispatch_assign_failed", error=str(exc))
            return DispatchResult(
                assigned=False,
                candidates_considered=len(candidates),
                radius_used_km=radius_used,
                reasoning=f"assignment write failed: {exc}",
            )

        incidents_assigned_total.inc()
        return DispatchResult(
            assigned=True,
            provider_id=chosen.provider_id,
            provider_name=chosen.name,
            eta_minutes=eta_minutes,
            distance_km=chosen.distance_km,
            candidates_considered=len(candidates),
            radius_used_km=radius_used,
            reasoning=reasoning,
        )

    # ------------------------------------------------------------------
    # Candidate search with progressive radius / service-type relaxation
    # ------------------------------------------------------------------

    async def _find_candidates(
        self,
        context: AgentContext,
        *,
        lat: float,
        lng: float,
        service_type: str | None,
    ) -> tuple[list[ProviderCandidate], float]:
        """Try initial radius, then drop service-type filter, then expand to max radius."""
        self._check_tool_authorized("geo_tool")

        attempts: list[tuple[float, str | None]] = [
            (settings.DISPATCH_INITIAL_RADIUS_KM, service_type),
        ]
        # If we filtered by service_type, also try without it before expanding
        if service_type is not None:
            attempts.append((settings.DISPATCH_INITIAL_RADIUS_KM, None))
        attempts.append((settings.DISPATCH_MAX_RADIUS_KM, service_type))
        if service_type is not None:
            attempts.append((settings.DISPATCH_MAX_RADIUS_KM, None))

        last_radius = settings.DISPATCH_MAX_RADIUS_KM
        for radius, svc in attempts:
            candidates = await find_nearest_providers_tool(
                context.db,
                lat=lat,
                lng=lng,
                radius_km=radius,
                service_type=svc,
                limit=5,
            )
            last_radius = radius
            if candidates:
                return candidates, radius

        return [], last_radius

    # ------------------------------------------------------------------
    # Selection — Claude-assisted ranking
    # ------------------------------------------------------------------

    async def _pick_best(
        self, candidates: list[ProviderCandidate], desired_service: str | None
    ) -> tuple[ProviderCandidate | None, str]:
        """Pick the best candidate. Skips Claude for trivial 1-candidate cases."""
        if len(candidates) == 1:
            only = candidates[0]
            return only, f"Sole candidate within radius (distance {only.distance_km:.2f} km)."

        # Multi-candidate: ask Claude to reason, with a deterministic fallback
        # if Claude isn't reachable.
        candidate_payload = json.dumps(
            {
                "desired_service": desired_service,
                "candidates": [c.to_dict() for c in candidates[:5]],
            },
            ensure_ascii=False,
        )

        try:
            raw = await self._call_claude(
                system=_ranking_system_prompt(),
                messages=[{"role": "user", "content": candidate_payload}],
                max_tokens=self.max_tokens,
                temperature=0.0,
            )
            chosen, reasoning = self._parse_ranking(raw, candidates)
            if chosen is not None:
                return chosen, reasoning
            log.info("claude_returned_no_choice_using_heuristic", reason=reasoning)
        except Exception as exc:  # noqa: BLE001
            log.warning("ranking_claude_call_failed_using_heuristic", error=str(exc))

        # Deterministic fallback: prefer exact service match, then distance, then total_jobs.
        chosen = self._heuristic_pick(candidates, desired_service)
        match_note = (
            "matches requested service" if (desired_service and chosen.service_type == desired_service)
            else "best generalist available"
        )
        return chosen, (
            f"Heuristic pick: {chosen.name} ({match_note}; "
            f"{chosen.distance_km:.2f} km; {chosen.total_jobs} prior jobs)."
        )

    @staticmethod
    def _parse_ranking(
        raw: str, candidates: list[ProviderCandidate]
    ) -> tuple[ProviderCandidate | None, str]:
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned.rsplit("```", 1)[0].strip()

        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            return None, "ranking response was not valid JSON"

        if not isinstance(data, dict):
            return None, "ranking response was not a JSON object"

        chosen_id = data.get("chosen_provider_id")
        reasoning = str(data.get("reasoning") or "")[:500]

        if chosen_id is None:
            return None, reasoning or "model declined to pick"

        try:
            chosen_uuid = uuid.UUID(str(chosen_id))
        except (ValueError, TypeError):
            return None, f"invalid uuid in ranking: {chosen_id}"

        for c in candidates:
            if c.provider_id == chosen_uuid:
                return c, reasoning or "selected by ranking model"
        return None, f"chosen id {chosen_id} not in candidate list"

    @staticmethod
    def _heuristic_pick(
        candidates: list[ProviderCandidate], desired_service: str | None
    ) -> ProviderCandidate:
        def score(c: ProviderCandidate) -> tuple:
            service_match = 0 if (desired_service and c.service_type == desired_service) else 1
            # Lower is better: prefer service match, then closer, then more experience
            return (service_match, c.distance_km, -c.total_jobs)

        return sorted(candidates, key=score)[0]


# ----------------------------------------------------------------------
# Convenience wrapper for the orchestrator
# ----------------------------------------------------------------------


async def dispatch_for_incident(
    *,
    db,
    incident_id: uuid.UUID,
    lat: float,
    lng: float,
    service_type: str | None,
    ai_diagnosis: dict | None = None,
) -> DispatchResult:
    """One-call helper used by the OrchestratorAgent in Phase 8."""
    agent = DispatchAgent()
    context = AgentContext(
        db=db,
        incident_id=incident_id,
        payload={
            "lat": lat,
            "lng": lng,
            "service_type": service_type,
            "ai_diagnosis": ai_diagnosis,
        },
    )
    result = await agent.run(context)
    if result.output is not None:
        return result.output
    return DispatchResult(
        assigned=False,
        reasoning=result.error or "dispatch run failed",
    )
