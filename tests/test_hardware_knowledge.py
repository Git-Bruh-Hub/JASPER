from app.knowledge.hardware import get_cpu_profile, render_cpu_explanation


def test_ryzen_5600x_profile_is_verified_and_complete():
    profile = get_cpu_profile("AMD Ryzen 5 5600X 6-Core Processor")
    assert profile is not None
    assert profile["cores"] == 6
    assert profile["threads"] == 12
    assert profile["threading"] == "AMD SMT (Simultaneous Multithreading)"
    assert profile["base_clock_ghz"] == 3.7
    assert profile["max_boost_clock_ghz"] == 4.6
    assert profile["l2_cache_mb"] == 3
    assert profile["l3_cache_mb"] == 32
    assert profile["tdp_w"] == 65
    assert profile["socket"] == "AM4"


def test_cpu_explanation_uses_verified_facts_not_live_ram_state():
    info = {
        "cpu": "AMD Ryzen 5 5600X 6-Core Processor",
        "ram_total_gb": 31.91,
        "ram_used_percent": 48.6,
    }
    answer = render_cpu_explanation("Explain what my CPU does.", info)
    assert answer is not None
    assert "3.7 GHz" in answer
    assert "4.6 GHz" in answer
    assert "AMD SMT" in answer
    assert "Hyper-Threading" in answer
    assert "48.6%" not in answer
    assert "RAM usage" not in answer


def test_detailed_cpu_explanation_has_valid_markdown_table():
    info = {"cpu": "AMD Ryzen 5 5600X 6-Core Processor"}
    answer = render_cpu_explanation("Explain my CPU in detail.", info)
    assert answer is not None
    assert "| Specification | Value |" in answer
    assert "| Base Clock | 3.7 GHz |" in answer
    assert "| Maximum Boost | Up to 4.6 GHz |" in answer
    assert "| Threading | AMD SMT |" in answer
    assert "| RAM Usage |" not in answer


def test_bm_cpu_explanation_is_supported():
    info = {"cpu": "AMD Ryzen 5 5600X 6-Core Processor"}
    answer = render_cpu_explanation("Terangkan apa fungsi CPU saya dalam Bahasa Melayu.", info)
    assert answer is not None
    assert "CPU anda ialah" in answer
    assert "AMD SMT" in answer
