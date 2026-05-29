"""Consolidated agent-contract tests.

Each agent subclasses BaseAgent and ships:
- a non-empty name, persona, goal
- a tools allow-list (tuple of str)
- an _execute coroutine
- correct tool-authorization enforcement

Per-agent behavior is exercised in test_<agent>.py. This module guards the
**contract** so a new agent that forgets to declare its persona/tools/etc.
fails CI immediately.
"""
from __future__ import annotations

import asyncio
import inspect
from unittest.mock import MagicMock

import pytest

from app.agents.admin_agent import AdminAgent
from app.agents.base import (
    AgentContext,
    AgentExecutionError,
    BaseAgent,
    ToolNotAuthorizedError,
)
from app.agents.communication import CommunicationAgent
from app.agents.dispatch import DispatchAgent
from app.agents.escalation import EscalationAgent
from app.agents.guardrail import GuardrailAgent
from app.agents.orchestrator import OrchestratorAgent
from app.agents.tracking import TrackingAgent
from app.agents.triage import TriageAgent

ALL_AGENT_CLASSES: list[type[BaseAgent]] = [
    GuardrailAgent,
    TriageAgent,
    DispatchAgent,
    CommunicationAgent,
    OrchestratorAgent,
    TrackingAgent,
    EscalationAgent,
    AdminAgent,
]


# ============================================================
# Contract: every agent declares the required attributes
# ============================================================


@pytest.mark.parametrize("AgentCls", ALL_AGENT_CLASSES)
def test_agent_declares_name(AgentCls):
    assert isinstance(AgentCls.name, str) and AgentCls.name, \
        f"{AgentCls.__name__}.name must be a non-empty string"
    # Avoid leaking the abstract default
    assert AgentCls.name != "BaseAgent"


@pytest.mark.parametrize("AgentCls", ALL_AGENT_CLASSES)
def test_agent_declares_persona_and_goal(AgentCls):
    assert isinstance(AgentCls.persona, str) and AgentCls.persona.strip(), \
        f"{AgentCls.__name__}.persona must be set"
    assert isinstance(AgentCls.goal, str) and AgentCls.goal.strip(), \
        f"{AgentCls.__name__}.goal must be set"


@pytest.mark.parametrize("AgentCls", ALL_AGENT_CLASSES)
def test_agent_tools_is_tuple_of_strings(AgentCls):
    assert isinstance(AgentCls.tools, tuple), \
        f"{AgentCls.__name__}.tools must be a tuple (got {type(AgentCls.tools)})"
    for t in AgentCls.tools:
        assert isinstance(t, str) and t, \
            f"{AgentCls.__name__} has non-string tool entry: {t!r}"


@pytest.mark.parametrize("AgentCls", ALL_AGENT_CLASSES)
def test_agent_execute_is_coroutine(AgentCls):
    assert inspect.iscoroutinefunction(AgentCls._execute), \
        f"{AgentCls.__name__}._execute must be an async coroutine"


def test_agent_names_are_unique():
    """No two agents may share the same .name — task_logs filter by it."""
    names = [cls.name for cls in ALL_AGENT_CLASSES]
    assert len(names) == len(set(names)), \
        f"duplicate agent names: {[n for n in names if names.count(n) > 1]}"


# ============================================================
# Tool authorization is enforced
# ============================================================


@pytest.mark.parametrize("AgentCls", ALL_AGENT_CLASSES)
def test_unauthorized_tool_call_raises(AgentCls):
    """Calling _check_tool_authorized with a name NOT in tools raises."""
    agent = AgentCls.__new__(AgentCls)  # skip __init__ (no API key needed)
    agent.tools = AgentCls.tools
    with pytest.raises(ToolNotAuthorizedError) as exc:
        agent._check_tool_authorized("definitely_not_a_real_tool")
    assert AgentCls.name in str(exc.value) or "not authorized" in str(exc.value)


@pytest.mark.parametrize("AgentCls", [c for c in ALL_AGENT_CLASSES if c.tools])
def test_authorized_tool_call_does_not_raise(AgentCls):
    """For agents with at least one declared tool, calling _check_tool_authorized
    with that tool name returns silently."""
    agent = AgentCls.__new__(AgentCls)
    agent.tools = AgentCls.tools
    # Should not raise
    agent._check_tool_authorized(AgentCls.tools[0])


def test_guardrail_has_zero_tools():
    """GuardrailAgent is reasoning-only — keep it that way."""
    assert GuardrailAgent.tools == (), \
        "GuardrailAgent MUST NOT have any tools (it should not be able to mutate state)"


# ============================================================
# BaseAgent.run() lifecycle — error paths return AgentResult, never raise
# ============================================================


class _AlwaysFailsAgent(BaseAgent):
    name = "_AlwaysFailsAgent"
    persona = "test"
    goal = "test"
    tools = ()

    async def _execute(self, context):
        raise AgentExecutionError("intentional failure for test")


class _UnexpectedExplodeAgent(BaseAgent):
    name = "_UnexpectedExplodeAgent"
    persona = "test"
    goal = "test"
    tools = ()

    async def _execute(self, context):
        raise ValueError("not an AgentExecutionError")


@pytest.mark.asyncio
async def test_run_catches_agent_execution_error(db_session):
    agent = _AlwaysFailsAgent(anthropic_client=MagicMock())
    result = await agent.run(AgentContext(db=db_session))
    assert result.success is False
    assert "intentional failure" in result.error
    assert result.agent_name == "_AlwaysFailsAgent"
    assert result.duration_ms >= 0


@pytest.mark.asyncio
async def test_run_catches_unexpected_exception(db_session):
    """Unexpected errors are caught and reported with success=False — never raised."""
    agent = _UnexpectedExplodeAgent(anthropic_client=MagicMock())
    result = await agent.run(AgentContext(db=db_session))
    assert result.success is False
    assert "unexpected" in result.error.lower() or "ValueError" in result.error
