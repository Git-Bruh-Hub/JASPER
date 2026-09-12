from app.tools.system import get_system_info


def test_system_info_has_hardware_fields():
    info = get_system_info()
    assert isinstance(info, dict)
    assert info["cpu"]
    assert "ram_total_gb" in info
    assert "ram_available_gb" in info
    assert "gpu" in info
    assert isinstance(info["gpu"], list)
    assert "system_drive" in info
    assert "ollama" in info
    assert "available" in info["ollama"]
