from app.tools.registry import ToolRegistry, Tool, Risk

def test_registry():
    registry = ToolRegistry()
    registry.register(Tool("x", "test", Risk.READ, lambda: 1))
    assert registry.get("x").risk == Risk.READ
