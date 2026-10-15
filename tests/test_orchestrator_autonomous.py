import asyncio
import pytest
from unittest.mock import Mock, AsyncMock, patch

from app.core.orchestrator import Orchestrator
from app.agents import CognitiveRouter, CognitiveMode
from app.agents.coordinator import CoordinatorState
from app.agents.multi_agent_coordinator import MultiAgentCoordinator
from app.tools.registry import ToolRegistry
from app.core.permissions import PermissionManager
from app.memory.sqlite_memory import SQLiteMemory


@pytest.fixture
def mock_registry():
    return ToolRegistry()


@pytest.fixture
def mock_permissions():
    return PermissionManager()


@pytest.fixture
def mock_memory():
    return SQLiteMemory()


@pytest.mark.asyncio
async def test_orchestrator_routes_to_multi_agent_coordinator(mock_registry, mock_permissions, mock_memory):
    # Setup mocks
    multi_agent_coordinator = AsyncMock(spec=MultiAgentCoordinator)
    multi_agent_coordinator.run_multi_agent.return_value = "Hive mind complete."

    orchestrator = Orchestrator(
        registry=mock_registry,
        permissions=mock_permissions,
        memory=mock_memory,
        multi_agent_coordinator=multi_agent_coordinator
    )
    
    # Mock CognitiveRouter to return AUTONOMOUS
    orchestrator.cognitive_router = Mock(spec=CognitiveRouter)
    orchestrator.cognitive_router.route.return_value = CognitiveMode.AUTONOMOUS
    
    # Mock emit_local_response so it doesn't break
    orchestrator._emit_local_response = AsyncMock()
    
    answer = await orchestrator.respond("/auto Do something autonomously")
    
    assert answer == "Hive mind complete."
    multi_agent_coordinator.run_multi_agent.assert_called_once()
    kwargs = multi_agent_coordinator.run_multi_agent.call_args.kwargs
    assert kwargs["user_text"] == "Do something autonomously"
    
    assert "assistant" in [m[0] for m in orchestrator.memory.recent()]


@pytest.mark.asyncio
async def test_orchestrator_autonomous_mode_disabled(mock_registry, mock_permissions, mock_memory):
    # No multi_agent_coordinator injected
    orchestrator = Orchestrator(
        registry=mock_registry,
        permissions=mock_permissions,
        memory=mock_memory,
        multi_agent_coordinator=None
    )
    
    orchestrator.cognitive_router = Mock(spec=CognitiveRouter)
    orchestrator.cognitive_router.route.return_value = CognitiveMode.AUTONOMOUS
    
    answer = await orchestrator.respond("/auto Do something autonomously")
    
    assert answer == "Autonomous mode is not enabled."


@pytest.mark.asyncio
async def test_orchestrator_reset_coordinator_recovers_error_state():
    mock_coord = Mock(spec=MultiAgentCoordinator)
    mock_coord.state = CoordinatorState.ERROR
    mock_coord.reset = Mock()

    orch = Orchestrator(
        registry=ToolRegistry(),
        permissions=PermissionManager(),
        memory=SQLiteMemory(),
        multi_agent_coordinator=mock_coord,
    )

    orch.reset_coordinator()
    mock_coord.reset.assert_called_once()

    # When in IDLE, reset should NOT be called
    mock_coord.reset.reset_mock()
    mock_coord.state = CoordinatorState.IDLE
    orch.reset_coordinator()
    mock_coord.reset.assert_not_called()

    # When None, reset_coordinator is a safe no-op
    orch_none = Orchestrator(
        registry=ToolRegistry(),
        permissions=PermissionManager(),
        memory=SQLiteMemory(),
        multi_agent_coordinator=None,
    )
    orch_none.reset_coordinator()


@pytest.mark.asyncio
async def test_orchestrator_multi_turn_failure_recovery_allows_next_turn(mock_registry, mock_permissions, mock_memory):
    mock_coord = AsyncMock(spec=MultiAgentCoordinator)
    # Turn 1: raises ValueError, sets state to ERROR
    async def fail_run(*args, **kwargs):
        mock_coord.state = CoordinatorState.ERROR
        raise ValueError("Planner proposed unregistered tool")
    mock_coord.run_multi_agent.side_effect = fail_run
    mock_coord.state = CoordinatorState.IDLE

    def do_reset():
        mock_coord.state = CoordinatorState.IDLE
    mock_coord.reset.side_effect = do_reset

    orchestrator = Orchestrator(
        registry=mock_registry,
        permissions=mock_permissions,
        memory=mock_memory,
        multi_agent_coordinator=mock_coord,
    )
    orchestrator.cognitive_router = Mock(spec=CognitiveRouter)
    orchestrator.cognitive_router.route.return_value = CognitiveMode.AUTONOMOUS
    orchestrator._emit_local_response = AsyncMock()

    # Turn 1 fails
    with pytest.raises(ValueError, match="Planner proposed unregistered tool"):
        await orchestrator.respond("/auto bad plan")

    assert mock_coord.state == CoordinatorState.ERROR

    # Caller invokes reset_coordinator()
    orchestrator.reset_coordinator()
    assert mock_coord.state == CoordinatorState.IDLE

    # Turn 2 succeeds on same instance
    mock_coord.run_multi_agent.side_effect = None
    mock_coord.run_multi_agent.return_value = "Recovered response."

    answer = await orchestrator.respond("/auto good plan")
    assert answer == "Recovered response."
    assert mock_coord.state == CoordinatorState.IDLE
