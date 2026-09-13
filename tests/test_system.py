from app.tools.system import get_system_info


def test_system_info_has_hardware_fields():
    info = get_system_info()
    assert isinstance(info, dict)
    assert info["cpu"]
    assert isinstance(info["ram_total_gb"], (int, float))
    assert info["ram_total_gb"] > 0
    assert "ram_available_gb" in info
    assert "gpu" in info
    assert isinstance(info["gpu"], list)
    assert "storage" in info
    assert isinstance(info["storage"], list)
    assert "system_drive" in info
    assert "ollama" in info
    assert "available" in info["ollama"]


def test_storage_volumes_have_ground_truth_capacity_fields():
    info = get_system_info()
    for drive in info["storage"]:
        assert drive["total_gb"] > 0
        assert drive["used_gb"] >= 0
        assert drive["free_gb"] >= 0
        assert drive["used_gb"] + drive["free_gb"] <= drive["total_gb"] + 0.1
