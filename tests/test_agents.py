"""Tests for JASPER v0.6 Adaptive Multi-Agent Cognition.

Covers:
- CognitiveRouter scoring & boundary behaviour
- CognitiveEngine workflow sequencing, context propagation, streaming, failures
- Orchestrator integration (model selection, single routing, system prompt augmentation)
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.agents.router import CognitiveRouter, CognitiveMode
from app.agents.engine import CognitiveEngine


# ===================================================================
# 1. CognitiveRouter — SIMPLE boundary
# ===================================================================


class TestRouterSimple:
    """Normal questions must remain SIMPLE."""

    router = CognitiveRouter()

    @pytest.mark.parametrize("text", [
        "hello",
        "what is the time?",
        "What is RAM?",
        "What does code mean?",
        "What is a CPU?",
        "How are you?",
        "What is a plan?",
        "Explain this concept.",
        "Tell me about Python.",
        "What time is it?",
        "Who invented the telephone?",
        "How do I boil an egg?",
        "Is it going to rain?",
    ])
    def test_simple_questions(self, text: str):
        assert self.router.route(text) == CognitiveMode.SIMPLE


# ===================================================================
# 2. CognitiveRouter — COLLABORATIVE boundary
# ===================================================================


class TestRouterCollaborative:
    """Moderate analytical requests should be COLLABORATIVE."""

    router = CognitiveRouter()

    @pytest.mark.parametrize("text", [
        "Compare Ryzen 5 5600X and Ryzen 7 5700X and tell me which is better for gaming.",
        "Analyze this error and explain what caused it: IndexError at line 42 in parser.py",
        "Plan a trip to Paris with these constraints: budget under 2000, must see Louvre and Eiffel Tower",
        "Help me debug this Python program that crashes when processing large files",
        "Evaluate the pros and cons of using SQLite vs PostgreSQL for my project",
        "Investigate why my application is running slowly and diagnose the bottleneck",
        "Analyze this.",
        "Compare these two.",
        "Debug my code.",
        "Plan my trip.",
        "Design a database."
    ])
    def test_collaborative_requests(self, text: str):
        result = self.router.route(text)
        assert result == CognitiveMode.COLLABORATIVE, \
            f"Expected COLLABORATIVE for: {text!r}, got {result}"


# ===================================================================
# 3. CognitiveRouter — DEEP boundary
# ===================================================================


class TestRouterDeep:
    """Complex multi-objective requests should be DEEP."""

    router = CognitiveRouter()

    @pytest.mark.parametrize("text", [
        "Give me a comprehensive step-by-step analysis of this codebase architecture",
        "Provide a thorough in-depth comparison of React versus Vue including performance benchmarks, ecosystem maturity, and developer experience trade-offs",
        "Design a detailed plan for migrating our monolith to microservices. First analyze the current dependencies, then evaluate containerization options, compare Kubernetes vs Docker Swarm, and finally outline a phased migration roadmap.",
    ])
    def test_deep_requests(self, text: str):
        assert self.router.route(text) == CognitiveMode.DEEP


# ===================================================================
# 4. CognitiveRouter — false positive resistance
# ===================================================================


class TestRouterNoFalsePositives:
    """Single occurrences of task words in simple questions must NOT
    accidentally escalate the cognitive mode."""

    router = CognitiveRouter()

    @pytest.mark.parametrize("text", [
        "What does analyze mean?",
        "What is a plan?",
        "Explain what code is.",
        "What is design?",
        "What does debug mean?",
        "What is research?",
        "Define research."
    ])
    def test_simple_word_usage_stays_simple(self, text: str):
        assert self.router.route(text) == CognitiveMode.SIMPLE

    def test_routing_is_deterministic(self):
        """Same input must always produce the same output."""
        text = "Compare these two architectures in depth"
        results = [self.router.route(text) for _ in range(50)]
        assert len(set(results)) == 1


# ===================================================================
# 5. CognitiveEngine — SIMPLE workflow
# ===================================================================


@pytest.mark.asyncio
async def test_engine_simple():
    """SIMPLE: single model call with tools and streaming."""
    async def fake_run_model(messages, system_prompt, use_tools, mode, user_text, on_chunk=None, cancel_callback=None):
        assert mode == CognitiveMode.SIMPLE
        assert user_text == "hello"
        assert use_tools is True
        assert system_prompt is None
        return "simple answer"

    engine = CognitiveEngine(fake_run_model)
    answer = await engine.run(CognitiveMode.SIMPLE, [], "hello")
    assert answer == "simple answer"


# ===================================================================
# 6. CognitiveEngine — COLLABORATIVE workflow
# ===================================================================


@pytest.mark.asyncio
async def test_engine_collaborative_sequencing_and_streaming():
    """COLLABORATIVE: Planner → Finalizer. Only Finalizer gets on_chunk."""
    calls = []

    async def fake_run_model(messages, system_prompt, use_tools, mode, user_text, on_chunk=None, cancel_callback=None):
        assert mode == CognitiveMode.COLLABORATIVE
        assert user_text == "test task"

        if "PLANNER" in str(system_prompt):
            assert on_chunk is None, "Planner must NOT receive on_chunk"
            assert use_tools is False
            calls.append("planner")
            return "step 1; step 2"
        if "FINALIZER" in str(system_prompt):
            assert on_chunk is not None, "Finalizer must receive on_chunk"
            assert use_tools is True
            # Planner output must reach Finalizer
            user_msg = next(m["content"] for m in messages if m["role"] == "user")
            assert "step 1; step 2" in user_msg
            calls.append("finalizer")
            return "final collaborative answer"
        return "unexpected"

    engine = CognitiveEngine(fake_run_model)
    answer = await engine.run(
        CognitiveMode.COLLABORATIVE, [], "test task",
        on_chunk=lambda s: None,
    )
    assert calls == ["planner", "finalizer"]
    assert answer == "final collaborative answer"


# ===================================================================
# 7. CognitiveEngine — DEEP workflow
# ===================================================================


@pytest.mark.asyncio
async def test_engine_deep_sequencing_and_context():
    """DEEP: Planner → Analyst → Critic → Finalizer with correct context propagation."""
    calls = []

    async def fake_run_model(messages, system_prompt, use_tools, mode, user_text, on_chunk=None, cancel_callback=None):
        assert mode == CognitiveMode.DEEP
        assert user_text == "deep task"
        user_msg = next(m["content"] for m in messages if m["role"] == "user")
        roles = [m["role"] for m in messages]
        assert "assistant" not in roles, "Historical assistant messages must not leak"

        if "PLANNER" in str(system_prompt):
            assert on_chunk is None
            assert use_tools is False
            assert "analyst output" not in user_msg.lower()
            assert "critic output" not in user_msg.lower()
            calls.append("planner")
            return "plan output"

        if "ANALYST" in str(system_prompt):
            assert on_chunk is None
            assert use_tools is True
            assert "plan output" in user_msg
            assert "critic output" not in user_msg.lower()
            calls.append("analyst")
            return "evidence output"

        if "CRITIC" in str(system_prompt):
            assert on_chunk is None
            assert use_tools is False
            assert "plan output" in user_msg
            assert "evidence output" in user_msg
            calls.append("critic")
            return "critique output"

        if "FINALIZER" in str(system_prompt):
            assert on_chunk is not None
            assert use_tools is False
            assert "plan output" in user_msg
            assert "evidence output" in user_msg
            assert "critique output" in user_msg
            calls.append("finalizer")
            return "deep answer"

        return "unexpected"

    engine = CognitiveEngine(fake_run_model)
    answer = await engine.run(
        CognitiveMode.DEEP, [], "deep task",
        on_chunk=lambda s: None,
    )
    assert calls == ["planner", "analyst", "critic", "finalizer"]
    assert answer == "deep answer"


# ===================================================================
# 8. CognitiveEngine — failure propagation
# ===================================================================


@pytest.mark.asyncio
async def test_planner_failure_halts_deep():
    """If Planner raises, subsequent stages must NOT run."""
    calls = []

    async def fake_run_model(messages, system_prompt, use_tools, mode, user_text, on_chunk=None, cancel_callback=None):
        if "PLANNER" in str(system_prompt):
            calls.append("planner")
            raise RuntimeError("Planner failed")
        calls.append("should not run")
        return "x"

    engine = CognitiveEngine(fake_run_model)
    with pytest.raises(RuntimeError, match="Planner failed"):
        await engine.run(CognitiveMode.DEEP, [], "test")
    assert calls == ["planner"]


@pytest.mark.asyncio
async def test_analyst_failure_halts_deep():
    """If Analyst raises, Critic and Finalizer must NOT run."""
    calls = []

    async def fake_run_model(messages, system_prompt, use_tools, mode, user_text, on_chunk=None, cancel_callback=None):
        if "PLANNER" in str(system_prompt):
            calls.append("planner")
            return "plan"
        if "ANALYST" in str(system_prompt):
            calls.append("analyst")
            raise RuntimeError("Analyst failed")
        calls.append("should not run")
        return "x"

    engine = CognitiveEngine(fake_run_model)
    with pytest.raises(RuntimeError, match="Analyst failed"):
        await engine.run(CognitiveMode.DEEP, [], "test")
    assert calls == ["planner", "analyst"]


@pytest.mark.asyncio
async def test_critic_failure_halts_deep():
    """If Critic raises, Finalizer must NOT run."""
    calls = []

    async def fake_run_model(messages, system_prompt, use_tools, mode, user_text, on_chunk=None, cancel_callback=None):
        if "PLANNER" in str(system_prompt):
            calls.append("planner")
            return "plan"
        if "ANALYST" in str(system_prompt):
            calls.append("analyst")
            return "evidence"
        if "CRITIC" in str(system_prompt):
            calls.append("critic")
            raise RuntimeError("Critic failed")
        calls.append("should not run")
        return "x"

    engine = CognitiveEngine(fake_run_model)
    with pytest.raises(RuntimeError, match="Critic failed"):
        await engine.run(CognitiveMode.DEEP, [], "test")
    assert calls == ["planner", "analyst", "critic"]


# ===================================================================
# 9. CognitiveEngine — context boundary: only system msgs propagated
# ===================================================================


@pytest.mark.asyncio
async def test_engine_passes_only_system_context_to_internal_stages():
    """Internal stages (non-SIMPLE) should receive only system-role context,
    not raw conversation history."""
    context = [
        {"role": "system", "content": "CORE JASPER PROMPT"},
        {"role": "user", "content": "old user message"},
        {"role": "assistant", "content": "old assistant reply"},
        {"role": "system", "content": "VISION OBS"},
    ]

    async def fake_run_model(messages, system_prompt, use_tools, mode, user_text, on_chunk=None, cancel_callback=None):
        # Every stage should only see the two system messages + one user msg
        roles = [m["role"] for m in messages]
        assert "assistant" not in roles, "Old conversation should not leak"
        system_msgs = [m for m in messages if m["role"] == "system"]
        assert len(system_msgs) == 2
        return "stage output"

    engine = CognitiveEngine(fake_run_model)
    await engine.run(CognitiveMode.COLLABORATIVE, context, "new task")


# ===================================================================
# 10. Orchestrator integration — model selection
# ===================================================================


@pytest.mark.asyncio
async def test_orchestrator_simple_uses_fast_model():
    """SIMPLE requests should use JASPER_FAST_MODEL."""
    from app.core.orchestrator import Orchestrator
    from app.core.config import JASPER_FAST_MODEL

    used_models = []

    class StubProvider:
        async def chat(self, messages, *, model, tools, max_output_tokens, cancel_callback=None):
            used_models.append(model)
            return {"message": {"role": "assistant", "content": "ok"}}

    class StubModels:
        local = StubProvider()
        def provider_for(self, mode):
            from app.core.config import JASPER_MODEL, JASPER_FAST_MODEL
            if mode in (CognitiveMode.DEEP, CognitiveMode.COLLABORATIVE):
                return self.local, JASPER_MODEL
            return self.local, JASPER_FAST_MODEL

    class StubMemory:
        def add(self, role, content): pass
        def recent(self, n): return []

    class StubMemoryManager:
        def parse_command(self, t): return None
        def context_for(self, t): return None

    orchestrator = Orchestrator(registry=MagicMock(), permissions=MagicMock(), memory=StubMemory())
    orchestrator.models = StubModels()
    orchestrator.memory_manager = StubMemoryManager()
    orchestrator._tool_schemas = lambda text: []

    # "hello" is SIMPLE
    await orchestrator.respond("hello")
    assert used_models[-1] == JASPER_FAST_MODEL


@pytest.mark.asyncio
async def test_orchestrator_collaborative_uses_main_model():
    """COLLABORATIVE requests should use JASPER_MODEL for all stages."""
    from app.core.orchestrator import Orchestrator
    from app.core.config import JASPER_MODEL

    used_models = []

    class StubProvider:
        async def chat(self, messages, *, model, tools, max_output_tokens, cancel_callback=None):
            used_models.append(model)
            return {"message": {"role": "assistant", "content": "ok"}}

    class StubModels:
        local = StubProvider()
        def provider_for(self, mode):
            from app.core.config import JASPER_MODEL, JASPER_FAST_MODEL
            if mode in (CognitiveMode.DEEP, CognitiveMode.COLLABORATIVE):
                return self.local, JASPER_MODEL
            return self.local, JASPER_FAST_MODEL

    class StubMemory:
        def add(self, role, content): pass
        def recent(self, n): return []

    class StubMemoryManager:
        def parse_command(self, t): return None
        def context_for(self, t): return None

    orchestrator = Orchestrator(registry=MagicMock(), permissions=MagicMock(), memory=StubMemory())
    orchestrator.models = StubModels()
    orchestrator.memory_manager = StubMemoryManager()
    orchestrator._tool_schemas = lambda text: []

    # Force COLLABORATIVE routing
    orchestrator.cognitive_router = CognitiveRouter()
    with patch.object(orchestrator.cognitive_router, "route", return_value=CognitiveMode.COLLABORATIVE):
        await orchestrator.respond("test")

    assert all(m == JASPER_MODEL for m in used_models), f"Expected all JASPER_MODEL, got {used_models}"
    assert len(used_models) == 2  # Planner + Finalizer


# ===================================================================
# 11. Orchestrator integration — single routing
# ===================================================================


@pytest.mark.asyncio
async def test_cognitive_router_called_once_per_respond():
    """CognitiveRouter.route() must be called exactly once per respond()."""
    from app.core.orchestrator import Orchestrator

    class StubProvider:
        async def chat(self, messages, *, model, tools, max_output_tokens, cancel_callback=None):
            return {"message": {"role": "assistant", "content": "ok"}}

    class StubModels:
        local = StubProvider()
        def provider_for(self, mode):
            return self.local, "test-model"

    class StubMemory:
        def add(self, role, content): pass
        def recent(self, n): return []

    class StubMemoryManager:
        def parse_command(self, t): return None
        def context_for(self, t): return None

    orchestrator = Orchestrator(registry=MagicMock(), permissions=MagicMock(), memory=StubMemory())
    orchestrator.models = StubModels()
    orchestrator.memory_manager = StubMemoryManager()
    orchestrator._tool_schemas = lambda text: []

    with patch.object(orchestrator.cognitive_router, "route", return_value=CognitiveMode.SIMPLE) as mock_route:
        await orchestrator.respond("hello")

    mock_route.assert_called_once_with("hello")


# ===================================================================
# 12. Orchestrator integration — system prompt augmentation
# ===================================================================


@pytest.mark.asyncio
async def test_run_model_loop_augments_system_prompt():
    """_run_model_loop must append the role prompt to the core JASPER prompt,
    not replace it."""
    from app.core.orchestrator import Orchestrator

    class DummyProvider:
        async def chat(self, messages, cancel_callback=None, **kwargs):
            return {"message": {"role": "assistant", "content": "dummy"}}

    class DummyModels:
        def __init__(self):
            self.provider = DummyProvider()
        def provider_for(self, mode):
            return self.provider, "dummy-model"

    orchestrator = Orchestrator(registry=None, permissions=None, memory=None, vision=None)
    orchestrator.models = DummyModels()
    orchestrator._tool_schemas = lambda text: []

    received_messages = []

    async def fake_chat(msgs, **kwargs):
        received_messages.append(list(msgs))
        return {"message": {"role": "assistant", "content": "ok"}}

    orchestrator.models.provider.chat = fake_chat

    # 1. system_prompt=None → core prompt untouched
    messages = [{"role": "system", "content": "CORE PROMPT"}]
    await orchestrator._run_model_loop(
        messages, system_prompt=None, use_tools=False,
        mode=CognitiveMode.SIMPLE, user_text="hello",
    )
    assert received_messages[-1][0]["content"] == "CORE PROMPT"

    # 2. system_prompt provided → core + role prompt combined
    await orchestrator._run_model_loop(
        messages, system_prompt="PLANNER INSTRUCTIONS", use_tools=False,
        mode=CognitiveMode.DEEP, user_text="hello",
    )
    assert received_messages[-1][0]["content"] == "CORE PROMPT\n\nPLANNER INSTRUCTIONS"


# ===================================================================
# 13. Streaming: only Finalizer receives on_chunk
# ===================================================================


@pytest.mark.asyncio
async def test_only_finalizer_streams_in_collaborative():
    """In COLLABORATIVE, only Finalizer's on_chunk must be non-None."""
    chunk_receivers = []

    async def fake_run_model(messages, system_prompt, use_tools, mode, user_text, on_chunk=None, cancel_callback=None):
        label = "planner" if "PLANNER" in str(system_prompt) else "finalizer"
        chunk_receivers.append((label, on_chunk is not None))
        return "output"

    engine = CognitiveEngine(fake_run_model)
    await engine.run(CognitiveMode.COLLABORATIVE, [], "test", on_chunk=lambda s: None)

    assert chunk_receivers == [("planner", False), ("finalizer", True)]


@pytest.mark.asyncio
async def test_only_finalizer_streams_in_deep():
    """In DEEP, only Finalizer's on_chunk must be non-None."""
    chunk_receivers = []

    async def fake_run_model(messages, system_prompt, use_tools, mode, user_text, on_chunk=None, cancel_callback=None):
        for role in ("PLANNER", "ANALYST", "CRITIC", "FINALIZER"):
            if role in str(system_prompt):
                chunk_receivers.append((role.lower(), on_chunk is not None))
                break
        return "output"

    engine = CognitiveEngine(fake_run_model)
    await engine.run(CognitiveMode.DEEP, [], "test", on_chunk=lambda s: None)

    assert chunk_receivers == [
        ("planner", False),
        ("analyst", False),
        ("critic", False),
        ("finalizer", True),
    ]
