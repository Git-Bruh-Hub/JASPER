"""tests/test_response_sanitization.py -- Deterministic tests for response sanitization.

Verifies:
1. A normal answer with no thinking tags is untouched.
2. A response with a complete thinking block followed by a final answer has reasoning removed.
3. A stray closing tag (e.g. </think> prefix) is stripped.
4. An incomplete thinking block (<think> without closing) is stripped without leaking internal thoughts.
5. Ordinary answers containing similar text (the word "think", code blocks with <think>, prose discussing tags) are preserved.
6. Coordinator synthesis and adapters sanitize observations.
"""

import pytest
from unittest.mock import Mock, AsyncMock

from app.core.response import sanitize_thinking_tags
from app.agents.contracts import AgentResult, ProposedAction, PlannerTask, PlannerResult
from app.agents.coordinator import Coordinator
from app.agents.adapters import PlannerAdapter, ExecutorAdapter
from app.models.model_router import ModelRouter
from app.tools.registry import ToolRegistry


def test_normal_answer_with_no_thinking_tags():
    text = "The sum of 2 and 2 is 4."
    assert sanitize_thinking_tags(text) == "The sum of 2 and 2 is 4."


def test_response_with_complete_thinking_block_followed_by_final_answer():
    text = "<think>\nLet us calculate: 2 + 2 = 4.\n</think>\n\n4"
    assert sanitize_thinking_tags(text) == "4"

    text_no_newlines = "<think>quick thought</think>42"
    assert sanitize_thinking_tags(text_no_newlines) == "42"

    text_multiple = "<think>thought 1</think><think>thought 2</think>Result"
    assert sanitize_thinking_tags(text_multiple) == "Result"


def test_stray_closing_tag():
    # Smoke test artifact from Qwen3
    text_smoke = "</think>\n\n4"
    assert sanitize_thinking_tags(text_smoke) == "4"

    # Stray closing tag with leading whitespace
    text_whitespace = "   </think>   Hello world."
    assert sanitize_thinking_tags(text_whitespace) == "Hello world."

    # Sole closing tag
    text_only = "</think>"
    assert sanitize_thinking_tags(text_only) == ""

    # Trailing stray closing tag
    text_trailing = "Answer 42\n</think>"
    assert sanitize_thinking_tags(text_trailing) == "Answer 42"


def test_incomplete_thinking_block():
    # Model cutoff while thinking (no closing tag)
    text = "<think>\nAnalyzing the input parameters and planning internal steps..."
    assert sanitize_thinking_tags(text) == ""

    # Empty thinking block
    text_empty = "<think></think>Clean answer."
    assert sanitize_thinking_tags(text_empty) == "Clean answer."


def test_ordinary_answer_containing_similar_text_not_removed():
    # 1. Natural language prose using the word 'think'
    text_prose = "I think Paris is the capital of France, and we should think carefully."
    assert sanitize_thinking_tags(text_prose) == text_prose

    # 2. Prose discussing <think> tags without code blocks
    text_prose_tag = "The model uses <think> to begin its internal chain of thought."
    assert sanitize_thinking_tags(text_prose_tag) == text_prose_tag

    # 3. Prose discussing </think> tags
    text_prose_closing = "In custom XML schemas, the closing tag is </think>."
    assert sanitize_thinking_tags(text_prose_closing) == text_prose_closing

    # 4. Markdown fenced code blocks containing <think> tags
    text_code_block = (
        "Here is an example XML configuration:\n"
        "```xml\n"
        "<think>custom configuration content</think>\n"
        "```\n"
        "Please save this to your configuration file."
    )
    assert sanitize_thinking_tags(text_code_block) == text_code_block

    # 5. Inline code containing <think>
    text_inline = "You can wrap your text in `<think>` and `</think>` tags."
    assert sanitize_thinking_tags(text_inline) == text_inline


def test_coordinator_synthesise_answer_sanitizes_observations():
    res = AgentResult(
        agent_id="executor",
        observations=["</think>\n\n4"],
    )
    tool_outputs = []
    synthesised = Coordinator._synthesise_answer(res, tool_outputs)
    assert synthesised == "4"

    res_with_think = AgentResult(
        agent_id="executor",
        observations=["<think>internal thought</think>\n\nThe capital of France is Paris."],
    )
    synthesised2 = Coordinator._synthesise_answer(res_with_think, tool_outputs)
    assert synthesised2 == "The capital of France is Paris."


@pytest.mark.asyncio
async def test_adapters_sanitize_thinking_tags_in_observations():
    mock_provider = AsyncMock()
    mock_provider.chat.return_value = {
        "message": {
            "role": "assistant",
            "content": "</think>\n\nPlanned output",
        }
    }
    mock_models = Mock(spec=ModelRouter)
    mock_models.provider_for.return_value = (mock_provider, "mock_model")

    registry = ToolRegistry()
    planner_adapter = PlannerAdapter(mock_models, registry)
    task = PlannerTask(user_text="test")
    planner_result = await planner_adapter(task)
    assert planner_result.observations == ["Planned output"]

    executor_adapter = ExecutorAdapter(mock_models, registry)
    handoff = PlannerResult(task_id="t1", user_text="test", planner_result=planner_result)
    executor_result = await executor_adapter(handoff)
    assert executor_result.observations == ["Planned output"]
