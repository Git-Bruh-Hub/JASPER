from app.core.orchestrator import (
    _format_system_fact_answer,
    _requires_system_grounding,
    _requires_system_observation,
)


def test_direct_hardware_questions_require_observation():
    assert _requires_system_observation("What CPU am I using?")
    assert _requires_system_observation("How much RAM and storage do I have?")
    assert _requires_system_observation("What model is currently loaded in Ollama, and how much VRAM is it using?")
    assert not _requires_system_observation("Explain what RAM does.")


def test_hardware_explanations_require_live_grounding():
    assert _requires_system_grounding("Explain my CPU in detail.")
    assert _requires_system_grounding("Tell me about my GPU.")
    assert _requires_system_grounding("Describe my PC RAM specifications.")
    assert not _requires_system_grounding("Explain what a CPU does.")
    assert not _requires_system_grounding("What CPU should I buy for gaming?")


def test_hardware_answer_uses_observed_values_only():
    info = {
        "cpu": "AMD Ryzen 5 5600X 6-Core Processor",
        "ram_total_gb": 31.91,
        "ram_available_gb": 20.5,
        "ram_used_percent": 35.8,
        "gpu": [{"name": "NVIDIA GeForce RTX 3060", "vram_total_gb": 12.0}],
        "storage": [{"path": "C:\\", "total_gb": 931.5, "free_gb": 500.0, "used_gb": 431.5}],
        "ollama": {"available": True, "models": [{"name": "qwen3:14b", "vram_gb": 9.85}]},
    }
    combined = _format_system_fact_answer("What CPU, GPU, RAM, and storage am I using?", info)
    assert "AMD Ryzen 5 5600X" in combined
    assert "RTX 3060" in combined
    assert "31.91 GB" in combined
    assert "931.5 GB" in combined
    assert "qwen3:14b" in _format_system_fact_answer("What model is currently loaded in Ollama?", info)


def test_combined_hardware_question_requires_observation():
    assert _requires_system_observation(
        "Tell me my CPU, GPU, VRAM, RAM, storage, and currently loaded Ollama model."
    )
    assert _requires_system_observation("What are my PC specs?")
    assert _requires_system_observation("Show me my system information.")
    assert not _requires_system_observation("How much RAM should a gaming PC have?")
    assert not _requires_system_observation("What GPU is good for 1440p gaming?")
