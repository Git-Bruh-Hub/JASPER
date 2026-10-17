import sqlite3
import pytest
from app.memory.sqlite_memory import SQLiteMemory


def test_session_creation_and_listing(tmp_path):
    db_file = tmp_path / "test_sessions.db"
    memory = SQLiteMemory(db_file)

    session1 = memory.create_session("First Topic")
    assert session1["title"] == "First Topic"
    assert session1["id"] is not None

    session2 = memory.create_session("Second Topic")
    sessions = memory.list_sessions()
    assert len(sessions) == 2
    # Newest session should appear first
    assert sessions[0]["id"] == session2["id"]
    assert sessions[1]["id"] == session1["id"]


def test_session_pinning_and_ordering(tmp_path):
    db_file = tmp_path / "test_pinning.db"
    memory = SQLiteMemory(db_file)

    session1 = memory.create_session("First Topic")
    session2 = memory.create_session("Second Topic")

    # Pin session1
    updated = memory.update_session(session1["id"], is_pinned=True)
    assert updated is True

    sessions = memory.list_sessions()
    # Pinned session1 must come first even though session2 was created later
    assert sessions[0]["id"] == session1["id"]
    assert sessions[0]["is_pinned"] == 1
    assert sessions[1]["id"] == session2["id"]
    assert sessions[1]["is_pinned"] == 0


def test_session_context_isolation(tmp_path):
    db_file = tmp_path / "test_isolation.db"
    memory = SQLiteMemory(db_file)

    session_a = memory.create_session("Coding Work")["id"]
    session_b = memory.create_session("Email Summary")["id"]

    memory.add("user", "Write a python function", session_id=session_a)
    memory.add("assistant", "def foo(): pass", session_id=session_a)

    memory.add("user", "Summarize 7-Eleven promo", session_id=session_b)
    memory.add("assistant", "20% discount on coffee", session_id=session_b)

    # Session A messages must contain only Python coding
    recent_a = memory.recent(10, session_id=session_a)
    assert len(recent_a) == 2
    assert recent_a[0] == ("user", "Write a python function")
    assert recent_a[1] == ("assistant", "def foo(): pass")

    # Session B messages must contain only 7-Eleven promo
    recent_b = memory.recent(10, session_id=session_b)
    assert len(recent_b) == 2
    assert recent_b[0] == ("user", "Summarize 7-Eleven promo")
    assert recent_b[1] == ("assistant", "20% discount on coffee")

    # session_messages returns in chronological order
    all_b = memory.session_messages(session_b)
    assert all_b == [
        ("user", "Summarize 7-Eleven promo"),
        ("assistant", "20% discount on coffee"),
    ]


def test_session_rename_and_delete(tmp_path):
    db_file = tmp_path / "test_crud.db"
    memory = SQLiteMemory(db_file)

    session = memory.create_session("Draft")["id"]
    memory.add("user", "Hello", session_id=session)

    # Rename
    memory.update_session(session, title="Renamed Topic")
    fetched = memory.get_session(session)
    assert fetched["title"] == "Renamed Topic"

    # Delete
    deleted = memory.delete_session(session)
    assert deleted is True
    assert memory.get_session(session) is None
    assert memory.session_messages(session) == []


def test_non_destructive_legacy_migration(tmp_path):
    db_file = tmp_path / "legacy_migration.db"

    # Create a pre-migration database with legacy events table (no session_id column)
    conn = sqlite3.connect(db_file)
    conn.execute(
        """
        CREATE TABLE events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL
        )
        """
    )
    conn.execute("INSERT INTO events (timestamp, role, content) VALUES ('2026-10-15T00:00:00Z', 'user', 'Legacy message 1')")
    conn.execute("INSERT INTO events (timestamp, role, content) VALUES ('2026-10-15T00:00:01Z', 'assistant', 'Legacy answer 1')")
    conn.commit()
    conn.close()

    # Now initialize SQLiteMemory with this legacy database
    memory = SQLiteMemory(db_file)

    # Legacy session must have been created automatically
    sessions = memory.list_sessions()
    assert len(sessions) == 1
    legacy_session = sessions[0]
    assert legacy_session["id"] == "legacy_history"
    assert legacy_session["title"] == "Previous History"

    # The existing 2 events must be assigned to legacy_history
    legacy_msgs = memory.session_messages("legacy_history")
    assert len(legacy_msgs) == 2
    assert legacy_msgs[0] == ("user", "Legacy message 1")
    assert legacy_msgs[1] == ("assistant", "Legacy answer 1")


@pytest.mark.asyncio
async def test_orchestrator_session_routing(tmp_path):
    from app.core.orchestrator import Orchestrator
    from app.tools.registry import ToolRegistry
    from app.core.permissions import PermissionManager

    db_file = tmp_path / "test_orch_session.db"
    memory = SQLiteMemory(db_file)
    registry = ToolRegistry()
    permissions = PermissionManager()
    orch = Orchestrator(registry, permissions, memory)

    session_x = memory.create_session("Session X")["id"]
    session_y = memory.create_session("Session Y")["id"]

    # Use memory command (which executes locally without Ollama) to test routing
    resp_x = await orch.respond("remember that user favorite editor is Neovim", session_id=session_x)
    assert "remember" in resp_x.lower()

    # Verify session X has the messages
    msgs_x = memory.session_messages(session_x)
    assert len(msgs_x) == 2
    assert msgs_x[0][0] == "user"
    assert "Neovim" in msgs_x[0][1]

    # Verify session Y has zero messages
    msgs_y = memory.session_messages(session_y)
    assert len(msgs_y) == 0


@pytest.fixture(scope="module")
def qapp():
    import os
    from PySide6.QtWidgets import QApplication
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_session_drawer_widget(qapp):
    from app.ui.session_drawer import SessionDrawer

    drawer = SessionDrawer()
    assert drawer.width() == 240
    assert not drawer.is_collapsed

    # Test collapse and expand
    drawer.toggle_collapse()
    assert drawer.is_collapsed
    assert drawer.width() == 44

    drawer.toggle_collapse()
    assert not drawer.is_collapsed
    assert drawer.width() == 240

    # Test setting sessions
    sessions_data = [
        {"id": "s1", "title": "Pinned Topic", "is_pinned": 1, "updated_at": "2026-10-18T00:00:00"},
        {"id": "s2", "title": "Normal Topic", "is_pinned": 0, "updated_at": "2026-10-18T00:00:00"},
    ]
    drawer.set_sessions(sessions_data, active_session_id="s1")
    assert drawer.active_session_id == "s1"
    assert "s1" in drawer._items
    assert "s2" in drawer._items
    assert drawer._items["s1"].is_pinned is True
    assert drawer._items["s2"].is_pinned is False

    # Test item selection signal
    selected = []
    drawer.session_selected.connect(lambda sid: selected.append(sid))
    drawer._items["s2"].click()
    assert selected == ["s2"]
    assert drawer.active_session_id == "s2"


def test_main_window_session_integration(qapp, tmp_path):
    from PySide6.QtCore import QThread
    from app.ui.main_window import MainWindow
    from app.ui.worker import JasperWorker

    db_path = tmp_path / "integration.db"
    worker = JasperWorker(coordinator=None)
    # Point memory to test db
    worker.jasper.memory = SQLiteMemory(db_path)
    thread = QThread()

    window = MainWindow(worker, thread)

    # Initial session should be auto-created
    assert window._active_session_id is not None
    initial_sid = window._active_session_id

    sessions = worker.jasper.memory.list_sessions()
    assert len(sessions) >= 1
    assert sessions[0]["id"] == initial_sid

    # Auto-titling test: send first prompt
    window.input.setText("How do I make pasta from scratch?")
    window._send_text()

    # Title of session should be updated from the prompt
    updated_sess = worker.jasper.memory.get_session(initial_sid)
    assert "How do I make pasta" in updated_sess["title"]

    # Test New Chat button
    window._on_new_chat_clicked()
    new_sid = window._active_session_id
    assert new_sid != initial_sid
    assert window._messages == []

    # Verify Chat History header stays at the exact same top position when open and closed
    y_open = window.session_drawer.dropdown_btn.mapTo(window, window.session_drawer.dropdown_btn.rect().topLeft()).y()
    window.session_drawer.toggle_collapse()
    qapp.processEvents()
    y_closed = window.session_drawer.dropdown_btn.mapTo(window, window.session_drawer.dropdown_btn.rect().topLeft()).y()
    assert y_open == y_closed
    window.session_drawer.toggle_collapse()
    qapp.processEvents()

    # Clean up window
    window.close()


