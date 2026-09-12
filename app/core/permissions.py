from app.tools.registry import Risk, Tool

class PermissionManager:
    """v0.1 allows only explicitly declared READ tools."""
    def allowed(self, tool: Tool) -> bool:
        return tool.risk == Risk.READ
    def check(self, tool: Tool) -> None:
        if not self.allowed(tool):
            raise PermissionError(f"Tool '{tool.name}' is not permitted by the v0.1 policy.")
