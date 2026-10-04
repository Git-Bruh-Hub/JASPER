import asyncio
import pytest
from unittest.mock import Mock, AsyncMock, patch

from app.core.orchestrator import Orchestrator
from app.agents import CognitiveRouter, CognitiveMode
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
