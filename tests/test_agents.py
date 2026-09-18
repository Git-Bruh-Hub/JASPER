import pytest
from unittest.mock import AsyncMock, patch

from app.agents.router import CognitiveRouter, CognitiveMode
from app.agents.engine import CognitiveEngine
from app.core.orchestrator import Orchestrator

def test_cognitive_router_simple():
    router = CognitiveRouter()
    assert router.route("hello") == CognitiveMode.SIMPLE
    assert router.route("what is the time?") == CognitiveMode.SIMPLE

def test_cognitive_router_collaborative():
    router = CognitiveRouter()
    assert router.route("analyze this file") == CognitiveMode.COLLABORATIVE
    assert router.route("plan a trip to paris") == CognitiveMode.COLLABORATIVE

def test_cognitive_router_deep():
    router = CognitiveRouter()
    assert router.route("give me a deep dive on quantum physics") == CognitiveMode.DEEP
    assert router.route("comprehensive step by step tutorial") == CognitiveMode.DEEP
    assert router.route("a" * 600) == CognitiveMode.DEEP

@pytest.mark.asyncio
async def test_engine_simple():
    async def fake_run_model(messages, system_prompt, use_tools, mode, user_text, on_chunk=None):
        assert mode == CognitiveMode.SIMPLE
        assert user_text == "test"
        return "simple answer"
        
    engine = CognitiveEngine(fake_run_model)
    answer = await engine.run(CognitiveMode.SIMPLE, [], "test")
    assert answer == "simple answer"

@pytest.mark.asyncio
async def test_engine_collaborative():
    calls = []
    async def fake_run_model(messages, system_prompt, use_tools, mode, user_text, on_chunk=None):
        assert mode == CognitiveMode.COLLABORATIVE
        assert user_text == "test"
        role = "planner" if not use_tools else "finalizer"
        calls.append(role)
        if role == "planner":
            assert on_chunk is None
            return "plan text"
        if role == "finalizer":
            assert on_chunk is not None
            # check plan text reached finalizer
            assert any("plan text" in str(m.get("content")) for m in messages)
            return "finalizer result"
        return "unknown"
        
    engine = CognitiveEngine(fake_run_model)
    def dummy_chunk(s): pass
    answer = await engine.run(CognitiveMode.COLLABORATIVE, [], "test", on_chunk=dummy_chunk)
    assert calls == ["planner", "finalizer"]
    assert answer == "finalizer result"

@pytest.mark.asyncio
async def test_engine_deep():
    calls = []
    async def fake_run_model(messages, system_prompt, use_tools, mode, user_text, on_chunk=None):
        assert mode == CognitiveMode.DEEP
        assert user_text == "test"
        
        if "PLANNER" in str(system_prompt):
            assert on_chunk is None
            calls.append("planner")
            return "plan text"
        elif "ANALYST" in str(system_prompt):
            assert on_chunk is None
            assert any("plan text" in str(m.get("content")) for m in messages)
            calls.append("analyst")
            return "evidence text"
        elif "CRITIC" in str(system_prompt):
            assert on_chunk is None
            assert any("plan text" in str(m.get("content")) for m in messages)
            assert any("evidence text" in str(m.get("content")) for m in messages)
            calls.append("critic")
            return "critique text"
        elif "FINALIZER" in str(system_prompt):
            assert on_chunk is not None
            assert any("plan text" in str(m.get("content")) for m in messages)
            assert any("evidence text" in str(m.get("content")) for m in messages)
            assert any("critique text" in str(m.get("content")) for m in messages)
            calls.append("finalizer")
            return "final answer"
        return "unknown"
        
    engine = CognitiveEngine(fake_run_model)
    def dummy_chunk(s): pass
    answer = await engine.run(CognitiveMode.DEEP, [], "test", on_chunk=dummy_chunk)
    assert calls == ["planner", "analyst", "critic", "finalizer"]
    assert answer == "final answer"

@pytest.mark.asyncio
async def test_engine_failure_halts_execution():
    calls = []
    async def fake_run_model(messages, system_prompt, use_tools, mode, user_text, on_chunk=None):
        if "PLANNER" in str(system_prompt):
            calls.append("planner")
            raise RuntimeError("Planner failed")
        calls.append("should not run")
        return "result"

    engine = CognitiveEngine(fake_run_model)
    with pytest.raises(RuntimeError, match="Planner failed"):
        await engine.run(CognitiveMode.DEEP, [], "test")
    
    assert calls == ["planner"]

@pytest.mark.asyncio
async def test_run_model_loop_augments_system_prompt():
    from app.core.orchestrator import Orchestrator, SYSTEM_PROMPT
    from app.agents.router import CognitiveMode
    
    class DummyProvider:
        async def chat(self, messages, **kwargs):
            return {"message": {"role": "assistant", "content": "dummy"}}
            
    class DummyModels:
        def __init__(self):
            self.provider = DummyProvider()
        def provider_for(self, mode):
            return self.provider, "dummy-model"

    orchestrator = Orchestrator(registry=None, permissions=None, memory=None, vision=None)
    orchestrator.models = DummyModels()
    orchestrator._tool_schemas = lambda text: []
    
    # 1. Test SIMPLE mode (system_prompt=None)
    messages = [{"role": "system", "content": "CORE PROMPT"}]
    # We patch provider.chat to verify the messages
    provider = orchestrator.models.provider_for(CognitiveMode.SIMPLE)[0]
    
    received_messages = []
    async def fake_chat(msgs, **kwargs):
        received_messages.append(msgs)
        return {"message": {"role": "assistant", "content": "simple"}}
        
    provider.chat = fake_chat
    
    await orchestrator._run_model_loop(messages, system_prompt=None, use_tools=False, mode=CognitiveMode.SIMPLE, user_text="hello")
    assert len(received_messages) == 1
    assert received_messages[0][0]["content"] == "CORE PROMPT"
    
    # 2. Test Agent mode (system_prompt provided)
    received_messages.clear()
    await orchestrator._run_model_loop(messages, system_prompt="PLANNER INSTRUCTIONS", use_tools=False, mode=CognitiveMode.DEEP, user_text="hello")
    assert len(received_messages) == 1
    # Check that it combined them
    assert received_messages[0][0]["content"] == "CORE PROMPT\n\nPLANNER INSTRUCTIONS"

