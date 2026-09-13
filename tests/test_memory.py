from app.memory.memory_manager import MemoryManager
from app.memory.sqlite_memory import SQLiteMemory


def test_explicit_memory_lifecycle(tmp_path):
    store = SQLiteMemory(tmp_path / "test.db")
    manager = MemoryManager(store)

    command = manager.parse_command("Remember that my router is a Tenda TX3.")
    assert command is not None
    assert command.action == "remember"
    assert "Tenda TX3" in command.content

    assert "I'll remember" in manager.handle_command(command)
    matches = store.search_memories("router Tenda TX3")
    assert len(matches) == 1
    assert matches[0]["content"] == "my router is a Tenda TX3."
    assert matches[0]["category"] == "device"


def test_memory_context_is_grounded_in_saved_content(tmp_path):
    store = SQLiteMemory(tmp_path / "test.db")
    manager = MemoryManager(store)
    store.remember("I prefer concise answers.", category="preference")
    store.remember("My main project is JASPER.", category="project")

    context = manager.context_for("What answer style do I prefer?")
    assert "I prefer concise answers." in context
    assert "Do not invent or silently modify them." in context


def test_forget_command_removes_matching_memory(tmp_path):
    store = SQLiteMemory(tmp_path / "test.db")
    manager = MemoryManager(store)
    store.remember("My router is a Tenda TX3.")

    command = manager.parse_command("Forget my router Tenda TX3.")
    assert command is not None
    assert command.action == "forget"
    assert manager.handle_command(command).startswith("Forgot this memory")
    assert store.search_memories("router Tenda TX3") == []


def test_ambiguous_forget_never_deletes_multiple_memories(tmp_path):
    store = SQLiteMemory(tmp_path / "test.db")
    manager = MemoryManager(store)
    store.remember("My router is a Tenda TX3.")
    store.remember("My backup router is a TP-Link AX1800.")

    command = manager.parse_command("Forget my router.")
    assert command is not None
    answer = manager.handle_command(command)
    assert "multiple matching memories" in answer
    assert len(store.list_memories()) == 2


def test_memory_list_command(tmp_path):
    store = SQLiteMemory(tmp_path / "test.db")
    manager = MemoryManager(store)
    store.remember("My main project is JASPER.", category="project")

    command = manager.parse_command("What do you remember about me?")
    assert command is not None
    assert command.action == "list"
    answer = manager.handle_command(command)
    assert "My main project is JASPER." in answer
