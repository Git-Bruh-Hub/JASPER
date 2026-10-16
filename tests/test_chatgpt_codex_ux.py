"""tests/test_chatgpt_codex_ux.py -- Deterministic tests for ChatGPT & Codex UI/UX, Tasks, Scheduled Monitors, and Plugins & Skills."""

from __future__ import annotations

import os
from unittest.mock import MagicMock

import pytest
from PySide6.QtCore import QThread
from PySide6.QtWidgets import QApplication

from app.ui.main_window import MainWindow
from app.ui.plugins_workspace import PluginsWorkspace
from app.ui.scheduled_workspace import ScheduledWorkspace
from app.ui.settings_workspace import SettingsWorkspace
from app.ui.tasks_workspace import TasksWorkspace
from app.ui.worker import JasperWorker


@pytest.fixture(scope="session")
def qapp():
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_scheduled_workspace_ui_and_actions(qapp):
    widget = ScheduledWorkspace()
    assert widget.search_input is not None
    assert widget.search_input.placeholderText().startswith("🔍")
    assert len(widget._suggestion_cards) == 4
    assert len(widget._schedules) == 0

    # Add a schedule manually from suggestions
    first_sugg = widget.TASK_SUGGESTIONS[0]
    widget._add_suggestion_as_schedule(first_sugg)
    assert len(widget._schedules) == 1
    first_sched = widget._schedules[0]
    assert first_sched["title"] == first_sugg["title"]

    # Verify search filter
    widget.search_input.setText("brief")
    visible_cards = [c for c in widget._suggestion_cards if not c.isHidden()]
    assert len(visible_cards) >= 1
    widget.search_input.setText("")

    # Test Run Now trigger signal
    triggered = []
    widget.task_triggered.connect(lambda title, prompt: triggered.append((title, prompt)))
    widget._run_schedule_now(first_sched)
    assert len(triggered) == 1
    assert triggered[0][0] == first_sched["title"]

    # Test Toggle schedule
    orig_status = first_sched["status"]
    widget._toggle_schedule(first_sched)
    assert first_sched["status"] != orig_status
    widget._toggle_schedule(first_sched)
    assert first_sched["status"] == orig_status

    # Test Delete schedule
    widget._delete_schedule(first_sched)
    assert len(widget._schedules) == 0


def test_plugins_workspace_tabs_and_actions(qapp):
    widget = PluginsWorkspace()
    assert widget.title_lbl.text() == "Installed Tools & Plugins"
    assert widget.btn_tab_plugins.isChecked()
    assert not widget.btn_tab_skills.isChecked()
    assert len(widget._card_widgets) > 0

    # Switch to Skills tab
    widget._switch_tab("skills")
    assert widget.title_lbl.text() == "Installed Agent Skills"
    assert widget.btn_tab_skills.isChecked()
    assert not widget.btn_tab_plugins.isChecked()
    assert any("ui-ux-pro-max" in text for _, text in widget._card_widgets)

    # Search filtering in skills
    widget.search_input.setText("frontend")
    visible_skills = [w for w, _ in widget._card_widgets if not w.isHidden()]
    assert len(visible_skills) >= 1
    widget.search_input.setText("")

    # Switch back to Plugins tab
    widget._switch_tab("plugins")
    assert widget.title_lbl.text() == "Installed Tools & Plugins"

    # Test "Use in Chat" signal
    used = []
    widget.use_item_requested.connect(lambda name, prompt: used.append((name, prompt)))
    first_plugin = widget.REAL_PLUGINS[0]
    widget._on_use_clicked(first_plugin, first_plugin["prompt"])
    assert len(used) == 1
    assert used[0][0] == first_plugin["name"]


def test_tasks_workspace_ui_and_execution(qapp):
    widget = TasksWorkspace()
    assert len(widget.TASK_SUGGESTIONS) == 4
    assert widget.status_badge.text() == "● STANDBY"

    started = []
    widget.task_started.connect(lambda goal: started.append(goal))

    # Test running a suggestion
    sugg = widget.TASK_SUGGESTIONS[0]
    widget._launch_suggestion(sugg)
    assert len(started) == 1
    assert started[0] == sugg["goal"]
    assert "EXECUTING" in widget.status_badge.text()
    assert widget.timeline_layout.count() >= 1

    # Test completing task
    widget.task_completed()
    assert "COMPLETED" in widget.status_badge.text()


def test_main_window_original_jasper_layout(qapp):
    worker = MagicMock(spec=JasperWorker)
    thread = MagicMock(spec=QThread)
    window = MainWindow(worker, thread)

    # 1. Total 7 pages preserved
    assert window.page_stack.count() == 7

    # 2. Navigation items matching the original clean design
    assert len(window.NAV_ITEMS) == 7
    assert window.NAV_ITEMS[0][1] == "Chat"
    assert window.NAV_ITEMS[1][1] == "Tasks"
    assert window.NAV_ITEMS[2][1] == "Scheduled"
    assert window.NAV_ITEMS[3][1] == "Plugins"
    assert window.NAV_ITEMS[6][1] == "Settings"

    # 3. Workspaces stacked correctly
    assert isinstance(window.page_stack.widget(0), type(window.chat_page))
    assert isinstance(window.page_stack.widget(1), TasksWorkspace)
    assert isinstance(window.page_stack.widget(2), ScheduledWorkspace)
    assert isinstance(window.page_stack.widget(3), PluginsWorkspace)
    assert isinstance(window.page_stack.widget(6), SettingsWorkspace)

    # 4. Original Conversation browser directly visible
    assert hasattr(window, "conversation")
    assert not window.conversation.isHidden()

    # 5. Original single-line composer controls
    assert window.input.placeholderText() == "Ask JASPER..."
    assert hasattr(window, "screen_button")
    assert hasattr(window, "watch_button")
    assert hasattr(window, "attach_button")
    assert hasattr(window, "mic_button")
    assert hasattr(window, "send_button")
    assert window.send_button.text() == "Send"

    # 6. Switching to Tasks and Scheduled pages
    window._select_page(1)
    assert window.page_stack.currentIndex() == 1
    assert "Tasks" in window.workspace_hint.text()

    window._select_page(2)
    assert window.page_stack.currentIndex() == 2
    assert "Scheduled" in window.workspace_hint.text()

    # 7. Triggering task from scheduled workspace pre-fills and sends to chat
    window._on_scheduled_task_triggered("Test Brief", "Summarize today's goals")
    assert window.page_stack.currentIndex() == 0

    # 8. Triggering task from Tasks workspace pre-fills and sends to chat
    window._on_task_started("Audit system health")
    assert window.page_stack.currentIndex() == 0

    # 9. Triggering use from Plugins workspace pre-fills and sends to chat
    window._on_plugin_use_requested("Web Search", "Search for PySide6 tips")
    assert window.page_stack.currentIndex() == 0
