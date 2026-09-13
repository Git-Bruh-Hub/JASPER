import asyncio
import logging
from app.core.logging_setup import setup_logging
from app.core.orchestrator import Orchestrator
from app.core.permissions import PermissionManager
from app.memory.sqlite_memory import SQLiteMemory
from app.tools.registry import ToolRegistry, Tool, Risk
from app.tools.system import get_system_info
from app.tools.filesystem import list_directory, read_text_file


def build_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(Tool(
        "get_system_info",
        "Read detailed non-sensitive local system information such as operating system, CPU, GPU, RAM, storage, and local Ollama model state.",
        Risk.READ,
        get_system_info,
        parameters={
            "type": "object",
            "properties": {},
        },
    ))
    registry.register(Tool(
        "list_directory",
        "List entries in a directory without modifying anything.",
        Risk.READ,
        list_directory,
        parameters={
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Directory path to inspect, for example C:\\Users\\Name\\Downloads.",
                }
            },
            "required": ["path"],
        },
    ))
    registry.register(Tool(
        "read_text_file",
        "Read a small allowlisted text file without modifying it.",
        Risk.READ,
        read_text_file,
        parameters={
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to a small allowlisted text file.",
                }
            },
            "required": ["path"],
        },
    ))
    return registry


async def main():
    setup_logging()
    log = logging.getLogger("jasper")
    jasper = Orchestrator(build_registry(), PermissionManager(), SQLiteMemory())
    print("JASPER v0.2.4")
    print("Tool calling enabled (read-only). Ground-truth system facts added. Type 'exit' to quit.\n")
    while True:
        try:
            user_text = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not user_text:
            continue
        if user_text.lower() in {"exit", "quit"}:
            break
        try:
            answer = await jasper.respond(user_text)
            print(f"JASPER: {answer}\n")
        except Exception as exc:
            log.exception("Request failed")
            print(f"JASPER: I couldn't complete that request: {exc}\n")


if __name__ == "__main__":
    asyncio.run(main())
