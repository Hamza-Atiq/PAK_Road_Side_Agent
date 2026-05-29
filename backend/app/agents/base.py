"""BaseAgent — foundation for every agent in the system.

Every agent has:
- A **persona** (who it is, in natural language)
- A **goal** (what it optimizes for)
- A **model** (the Claude model ID it calls)
- A **tools allow-list** (which tool names it is authorized to invoke)
- A **run()** method that takes an `AgentContext` and returns an `AgentResult`

The base class provides:
- Lifecycle logging to `task_logs` (STARTED / SUCCESS / FAILURE / RETRY)
- Wall-clock timing
- A `_call_claude()` helper using AsyncAnthropic
- A `_check_tool_authorized()` guard that subclasses call before invoking any tool
- Hooks for Prometheus counters (`agent_calls_total`, `agent_errors_total`)

Subclasses override `_execute(context)`, never `run()` directly.
"""
from __future__ import annotations

import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Generic, TypeVar

from anthropic import AsyncAnthropic
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.metrics import record_agent_call
from app.middleware.logging import get_logger
from app.models.enums import TaskLogStatus
from app.models.task_log import TaskLog

log = get_logger("agents.base")

TOutput = TypeVar("TOutput")


# ----------------------------------------------------------------------
# Context + Result
# ----------------------------------------------------------------------


@dataclass
class AgentContext:
    """Per-invocation context passed into every agent.

    db is required for any agent that reads/writes data. incident_id
    is the strong correlation key for task_logs.
    """

    db: AsyncSession
    incident_id: uuid.UUID | None = None
    user_id: uuid.UUID | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentResult(Generic[TOutput]):
    """The structured outcome of an agent run."""

    success: bool
    output: TOutput | None = None
    reasoning: str | None = None
    error: str | None = None
    duration_ms: int = 0
    agent_name: str = ""


# ----------------------------------------------------------------------
# Errors
# ----------------------------------------------------------------------


class ToolNotAuthorizedError(Exception):
    """Raised when an agent tries to call a tool outside its allow-list."""


class AgentExecutionError(Exception):
    """Raised inside _execute() when the agent cannot fulfil its goal."""


# ----------------------------------------------------------------------
# BaseAgent
# ----------------------------------------------------------------------


class BaseAgent(ABC, Generic[TOutput]):
    """Abstract base class. Subclasses set the class attributes and implement _execute."""

    name: str = "BaseAgent"
    persona: str = ""
    goal: str = ""
    model: str = ""
    max_tokens: int = 1024
    tools: tuple[str, ...] = ()  # Names of tools this agent may invoke

    def __init__(self, anthropic_client: AsyncAnthropic | None = None) -> None:
        # Allow injection for testing; default to a real client.
        if anthropic_client is not None:
            self._client = anthropic_client
        elif settings.ANTHROPIC_API_KEY:
            self._client = AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
        else:
            self._client = None  # tests / dev without key

        if not self.model:
            self.model = settings.CLAUDE_MODEL

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    async def run(self, context: AgentContext) -> AgentResult[TOutput]:
        """Wraps _execute with timing, logging, and error handling."""
        start = time.perf_counter()
        await self._log_step(context, TaskLogStatus.STARTED, step="run")

        try:
            output = await self._execute(context)
        except AgentExecutionError as exc:
            duration_seconds = time.perf_counter() - start
            duration_ms = int(duration_seconds * 1000)
            await self._log_step(
                context,
                TaskLogStatus.FAILURE,
                step="run",
                error=str(exc),
                duration_ms=duration_ms,
            )
            log.warning("agent_failed", agent=self.name, error=str(exc))
            record_agent_call(self.name, success=False, duration_seconds=duration_seconds)
            return AgentResult(
                success=False,
                error=str(exc),
                duration_ms=duration_ms,
                agent_name=self.name,
            )
        except Exception as exc:
            duration_seconds = time.perf_counter() - start
            duration_ms = int(duration_seconds * 1000)
            await self._log_step(
                context,
                TaskLogStatus.FAILURE,
                step="run",
                error=f"unexpected: {exc!r}",
                duration_ms=duration_ms,
            )
            log.exception("agent_unexpected_error", agent=self.name)
            record_agent_call(self.name, success=False, duration_seconds=duration_seconds)
            return AgentResult(
                success=False,
                error=f"unexpected error: {exc}",
                duration_ms=duration_ms,
                agent_name=self.name,
            )

        duration_seconds = time.perf_counter() - start
        duration_ms = int(duration_seconds * 1000)
        await self._log_step(
            context,
            TaskLogStatus.SUCCESS,
            step="run",
            duration_ms=duration_ms,
            payload=self._safe_payload(output),
        )
        record_agent_call(self.name, success=True, duration_seconds=duration_seconds)
        return AgentResult(
            success=True,
            output=output,
            duration_ms=duration_ms,
            agent_name=self.name,
        )

    # ------------------------------------------------------------------
    # Subclass contract
    # ------------------------------------------------------------------

    @abstractmethod
    async def _execute(self, context: AgentContext) -> TOutput:
        """Subclass implementation. Return whatever output type the agent produces.

        Raise AgentExecutionError for expected failures the orchestrator
        should handle. Anything else is treated as an unexpected error.
        """

    # ------------------------------------------------------------------
    # Helpers for subclasses
    # ------------------------------------------------------------------

    async def _call_claude(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        max_tokens: int | None = None,
        temperature: float = 0.0,
    ) -> str:
        """Send a Claude messages request and return the text of the first content block.

        Subclasses that need tool-use or vision should compose their own call;
        this helper is for plain text completions.
        """
        if self._client is None:
            raise AgentExecutionError(
                "Anthropic client is not configured (ANTHROPIC_API_KEY missing)"
            )
        response = await self._client.messages.create(
            model=self.model,
            max_tokens=max_tokens or self.max_tokens,
            temperature=temperature,
            system=system,
            messages=messages,
        )
        # response.content is a list of content blocks; we read the first text block.
        for block in response.content:
            if getattr(block, "type", None) == "text":
                return block.text
        # Fallback: stringify whatever is there
        return str(response.content)

    def _check_tool_authorized(self, tool_name: str) -> None:
        """Raise ToolNotAuthorizedError if `tool_name` isn't in self.tools."""
        if tool_name not in self.tools:
            raise ToolNotAuthorizedError(
                f"Agent '{self.name}' is not authorized to call tool '{tool_name}'. "
                f"Allowed: {self.tools}"
            )

    async def _log_step(
        self,
        context: AgentContext,
        status: TaskLogStatus,
        *,
        step: str,
        reasoning: str | None = None,
        payload: dict[str, Any] | None = None,
        error: str | None = None,
        duration_ms: int | None = None,
    ) -> None:
        """Write a row to task_logs in a SAVEPOINT so a failure here (e.g. an
        FK violation when incident_id refers to a row that doesn't exist yet,
        or a JSON serialization error on the payload) can't poison the outer
        transaction. The outer transaction stays usable; only the failed log
        row is rolled back."""
        try:
            async with context.db.begin_nested():
                row = TaskLog(
                    incident_id=context.incident_id,
                    agent_name=self.name,
                    step=step,
                    status=status.value,
                    reasoning=reasoning,
                    payload=payload,
                    error=error,
                    duration_ms=duration_ms,
                )
                context.db.add(row)
                # The async-with savepoint exit flushes + commits the savepoint;
                # if anything raises in between, the savepoint is rolled back.
        except Exception:
            # Never let log failures bubble up; just record at app-log level.
            log.exception("task_log_write_failed", agent=self.name, step=step)

    @staticmethod
    def _safe_payload(output: Any) -> dict[str, Any] | None:
        """Best-effort conversion of an output object into a JSON-safe dict for the log."""
        if output is None:
            return None
        if isinstance(output, dict):
            return output
        if hasattr(output, "model_dump"):
            try:
                return output.model_dump(mode="json")
            except Exception:
                return None
        return {"output": str(output)[:1000]}
