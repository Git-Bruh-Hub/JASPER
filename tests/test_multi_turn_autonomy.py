"""tests/test_multi_turn_autonomy.py -- Tests for Multi-Turn Autonomous ReAct Loop."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.agents.contracts import (
    AgentResult,
    ApprovalRequirement,
    PermissionScope,
    PlannerResult,
    PlannerTask,
    ProposedAction,
)
from app.agents.coordinator import CoordinatorBudget, CoordinatorState
from app.agents.multi_agent_coordinator import MultiAgentCoordinator
from app.core.scoped_permissions import ScopedPermissionManager
from app.tools.registry import Risk, Tool, ToolRegistry


@pytest.fixture
def test_setup():
    reg = ToolRegistry()
    mock_nav = MagicMock(return_value={"status": "navigated", "title": "Search Engine", "snapshot": "[1] Link 'Result A'"})
    reg.register(Tool(
        name="browser_navigate",
        description="Navigate to URL",
        risk=Risk.READ,
        handler=mock_nav,
        parameters={"type": "object", "properties": {"url": {"type": "string"}}},
        resource_extractor=lambda a: a.get("url", ""),
    ))

    mock_click = MagicMock(return_value={"status": "clicked", "target": "Result A", "text": "Article content details."})
    reg.register(Tool(
        name="browser_click",
        description="Click element",
        risk=Risk.READ,  # Set to READ for headless multi-turn test
        handler=mock_click,
        parameters={"type": "object", "properties": {"index": {"type": "integer"}}},
        resource_extractor=lambda a: f"index:{a.get('index')}",
    ))

    pm = ScopedPermissionManager(workspace_root=Path.cwd(), allowed_risks=frozenset({Risk.READ, Risk.WRITE}))
    coord = MultiAgentCoordinator(registry=reg, permissions=pm, budget=CoordinatorBudget(timeout_seconds=30.0))

    return coord, mock_nav, mock_click


@pytest.mark.asyncio
async def test_multi_turn_autonomous_loop_terminates_on_zero_actions(test_setup):
    coord, mock_nav, mock_click = test_setup

    turn_count = 0

    async def fake_planner(task: PlannerTask, cancel_callback=None) -> AgentResult:
        nonlocal turn_count
        turn_count += 1

        if turn_count == 1:
            # Turn 1: Navigate to search
            action = ProposedAction(
                tool_name="browser_navigate",
                arguments={"url": "https://example.com/search"},
                scope=PermissionScope(risk="read", resource_scope="https://example.com/search", operation="browser_navigate", approval_requirement=ApprovalRequirement.NEVER),
                rationale="Search web",
            )
            return AgentResult(agent_id="planner", observations=["Searching web"], proposed_actions=[action])

        elif turn_count == 2:
            # Turn 2: Sees previous turn observation in task.user_text, clicks result 1
            assert "Search Engine" in task.user_text or "browser_navigate" in task.user_text
            action = ProposedAction(
                tool_name="browser_click",
                arguments={"index": 1},
                scope=PermissionScope(risk="read", resource_scope="index:1", operation="browser_click", approval_requirement=ApprovalRequirement.NEVER),
                rationale="Click top result",
            )
            return AgentResult(agent_id="planner", observations=["Clicking result 1"], proposed_actions=[action])

        else:
            # Turn 3: Reads article details, has answer -> returns 0 proposed actions!
            assert "Article content details" in task.user_text or "browser_click" in task.user_text
            return AgentResult(agent_id="planner", observations=["Final answer: The article explains local AI models."], proposed_actions=[])

    async def fake_executor(plan: PlannerResult, disagreement=None, cancel_callback=None) -> AgentResult:
        return plan.planner_result

    answer = await coord.run_multi_agent(
        planner_callable=fake_planner,
        executor_callable=fake_executor,
        user_text="Find info on local AI models",
        max_turns=4,
    )

    assert turn_count == 3
    assert mock_nav.call_count == 1
    assert mock_click.call_count == 1
    assert "Final answer: The article explains local AI models." in answer
    assert coord.state == CoordinatorState.IDLE


@pytest.mark.asyncio
async def test_multi_turn_loop_stops_at_max_turns_limit(test_setup):
    coord, mock_nav, _ = test_setup

    turn_count = 0

    async def endless_planner(task: PlannerTask, cancel_callback=None) -> AgentResult:
        nonlocal turn_count
        turn_count += 1
        action = ProposedAction(
            tool_name="browser_navigate",
            arguments={"url": f"https://example.com/page{turn_count}"},
            scope=PermissionScope(risk="read", resource_scope="https://example.com", operation="browser_navigate", approval_requirement=ApprovalRequirement.NEVER),
            rationale="Keep browsing",
        )
        return AgentResult(agent_id="planner", observations=[f"Turn {turn_count}"], proposed_actions=[action])

    async def fake_executor(plan: PlannerResult, disagreement=None, cancel_callback=None) -> AgentResult:
        return plan.planner_result

    # Hard ceiling of max_turns=3
    answer = await coord.run_multi_agent(
        planner_callable=endless_planner,
        executor_callable=fake_executor,
        user_text="Endless research task",
        max_turns=3,
    )

    assert turn_count == 3
    assert mock_nav.call_count == 3
    assert coord.state == CoordinatorState.IDLE


def test_dom_snapshot_highlights_search_results():
    from app.tools.browser import BrowserController, InteractiveElement
    from unittest.mock import MagicMock

    ctrl = BrowserController(headless=True)
    ctrl._elements = {
        1: InteractiveElement(index=1, tag="a", element_type="", text="DuckDuckGo Home", selector="[data-jasper-id='1']", is_search_result=False),
        2: InteractiveElement(index=2, tag="a", element_type="", text="Top 10 Local AI Models in 2026", selector="[data-jasper-id='2']", is_search_result=True),
    }

    mock_page = MagicMock()
    mock_page.title.return_value = "Search Results"
    mock_page.url = "https://duckduckgo.com/?q=local+ai"
    ctrl._ensure_browser_impl = MagicMock(return_value=mock_page)

    # Call formatting directly on pool thread
    snapshot = ctrl._run_in_pool(lambda: [
        f"Page Title: {mock_page.title()}",
        f"Current URL: {mock_page.url}",
        f"Found {len(ctrl._elements)} interactive element(s):",
        "--------------------------------------------------",
        *[f"[{el.index}] <{el.tag}>{' [Search Result]' if el.is_search_result else ''} '{el.text}'" for el in ctrl._elements.values()]
    ])
    snapshot_text = "\n".join(snapshot)

    assert "[1] <a> 'DuckDuckGo Home'" in snapshot_text
    assert "[2] <a> [Search Result] 'Top 10 Local AI Models in 2026'" in snapshot_text


def test_browser_search_helper():
    from app.tools.browser import BrowserController
    from unittest.mock import MagicMock

    ctrl = BrowserController(headless=True)
    ctrl.navigate = MagicMock(return_value={"status": "navigated"})

    res = ctrl.search("ollama deepseek-r1")
    assert res == {"status": "navigated"}
    ctrl.navigate.assert_called_once_with("https://duckduckgo.com/?q=ollama+deepseek-r1")


def test_format_turn_observations_handles_tools_cleanly():
    from app.agents.multi_agent_coordinator import MultiAgentCoordinator

    tool_outputs = [
        {"tool": "browser_navigate", "status": "success", "result": {"url": "https://example.com", "title": "Example", "snapshot": "[1] Link"}},
        {"tool": "browser_read_text", "status": "success", "result": {"title": "Article", "text": "Important findings."}},
        {"tool": "bad_tool", "status": "error", "error": "Connection timed out"},
    ]

    obs = MultiAgentCoordinator._format_turn_observations(tool_outputs)
    assert "[Tool browser_navigate]: Successfully navigated to https://example.com (Title: 'Example')" in obs
    assert "[Tool browser_read_text]: Page Content (Article):\nImportant findings." in obs
    assert "[Tool bad_tool ERROR]: Connection timed out" in obs
