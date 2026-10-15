import asyncio
import pytest
from unittest.mock import AsyncMock, patch

from app.agents.engine import CognitiveEngine
from app.agents.router import CognitiveMode
from app.models.base import ModelProvider

@pytest.mark.asyncio
async def test_cancellation_halts_simple():
    """SIMPLE: cancellation stops generation."""
    cancel_flag = False

    async def fake_run_model(messages, system_prompt, use_tools, mode, user_text, on_chunk=None, cancel_callback=None):
        if cancel_callback and cancel_callback():
            raise asyncio.CancelledError()
        return "Simple response"
    
    engine = CognitiveEngine(fake_run_model)
    cancel_flag = True
    with pytest.raises(asyncio.CancelledError):
        await engine.run(CognitiveMode.SIMPLE, [], "test", cancel_callback=lambda: cancel_flag)

@pytest.mark.asyncio
async def test_cancellation_during_planner_halts_collaborative():
    """COLLABORATIVE: cancellation during Planner prevents Finalizer."""
    cancel_flag = False
    calls = []

    async def fake_run_model(messages, system_prompt, use_tools, mode, user_text, on_chunk=None, cancel_callback=None):
        nonlocal cancel_flag
        calls.append("called")
        if "PLANNER" in system_prompt:
            cancel_flag = True
            return "Plan"
        if cancel_callback and cancel_callback():
            raise asyncio.CancelledError()
        return "Final output"
    
    engine = CognitiveEngine(fake_run_model)
    with pytest.raises(asyncio.CancelledError):
        await engine.run(CognitiveMode.COLLABORATIVE, [], "test", cancel_callback=lambda: cancel_flag)
    
    assert len(calls) == 1

@pytest.mark.asyncio
async def test_cancellation_during_planner_halts_deep():
    """DEEP: cancellation during Planner prevents Analyst/Critic/Finalizer."""
    cancel_flag = False
    calls = []

    async def fake_run_model(messages, system_prompt, use_tools, mode, user_text, on_chunk=None, cancel_callback=None):
        nonlocal cancel_flag
        calls.append("called")
        if "PLANNER" in system_prompt:
            cancel_flag = True
            return "Plan"
        if cancel_callback and cancel_callback():
            raise asyncio.CancelledError()
        return "Output"
    
    engine = CognitiveEngine(fake_run_model)
    with pytest.raises(asyncio.CancelledError):
        await engine.run(CognitiveMode.DEEP, [], "test", cancel_callback=lambda: cancel_flag)
    
    assert len(calls) == 1

@pytest.mark.asyncio
async def test_cancellation_during_analyst_halts_deep():
    """DEEP: cancellation during Analyst prevents Critic/Finalizer."""
    cancel_flag = False
    calls = []

    async def fake_run_model(messages, system_prompt, use_tools, mode, user_text, on_chunk=None, cancel_callback=None):
        nonlocal cancel_flag
        calls.append("called")
        if "ANALYST" in system_prompt:
            cancel_flag = True
            return "Analyst"
        if cancel_callback and cancel_callback():
            raise asyncio.CancelledError()
        return "Output"
    
    engine = CognitiveEngine(fake_run_model)
    with pytest.raises(asyncio.CancelledError):
        await engine.run(CognitiveMode.DEEP, [], "test", cancel_callback=lambda: cancel_flag)
    
    assert len(calls) == 2

@pytest.mark.asyncio
async def test_cancellation_during_critic_halts_deep():
    """DEEP: cancellation during Critic prevents Finalizer."""
    cancel_flag = False
    calls = []

    async def fake_run_model(messages, system_prompt, use_tools, mode, user_text, on_chunk=None, cancel_callback=None):
        nonlocal cancel_flag
        calls.append("called")
        if "CRITIC" in system_prompt:
            cancel_flag = True
            return "Critic"
        if cancel_callback and cancel_callback():
            raise asyncio.CancelledError()
        return "Output"
    
    engine = CognitiveEngine(fake_run_model)
    with pytest.raises(asyncio.CancelledError):
        await engine.run(CognitiveMode.DEEP, [], "test", cancel_callback=lambda: cancel_flag)
    
    assert len(calls) == 3
