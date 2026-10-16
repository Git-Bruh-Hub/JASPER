"""app/ui/tasks_workspace.py -- Autonomous agent execution workspace."""

from __future__ import annotations

import logging
from typing import Any

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

_LOG = logging.getLogger("jasper.ui.tasks_workspace")


class TasksWorkspace(QWidget):
    """Workspace for planning, launching, and monitoring autonomous agent tasks."""

    task_started = Signal(str)  # Emits goal string to run in orchestrator/worker

    TASK_SUGGESTIONS = [
        {
            "title": "Desktop & System Health Audit",
            "goal": "Inspect my screen, check running apps, review system memory and GPU VRAM, and report any errors.",
            "icon": "🖥️",
            "badge": "Vision + System",
            "desc": "Uses desktop vision and system inspection tools to audit background tasks and errors.",
        },
        {
            "title": "Run Regression Test Suite",
            "goal": "Run pytest on the test suite, analyze any failures, and summarize test health.",
            "icon": "🧪",
            "badge": "QA & Testing",
            "desc": "Executes local test suite in the virtualenv and reports exact pass/fail counts.",
        },
        {
            "title": "Web Research & Summarize",
            "goal": "Search the web for the latest PySide6 UI best practices and summarize actionable tips.",
            "icon": "🌐",
            "badge": "Web Search",
            "desc": "Searches DuckDuckGo and reads key documentation autonomously.",
        },
        {
            "title": "Codebase Security & Lint Audit",
            "goal": "Scan recent code changes for safety invariants, unhandled exceptions, and clean up temporary files.",
            "icon": "🛡️",
            "badge": "Security",
            "desc": "Reviews working-tree diff and checks for security-sensitive boundaries.",
        },
    ]

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("tasksWorkspace")
        self._active_task_goal: str | None = None
        self._execution_steps: list[dict[str, str]] = []
        self._build_ui()

    def _build_ui(self) -> None:
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(32, 28, 32, 28)
        root_layout.setSpacing(20)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("background: transparent; border: none;")

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(22)

        # --- Header ---
        header_layout = QVBoxLayout()
        header_layout.setSpacing(6)

        title = QLabel("Autonomous Tasks")
        title.setStyleSheet("font-size: 24pt; font-weight: 700; color: #ffffff;")
        header_layout.addWidget(title)

        subtitle = QLabel("Delegate complex, multi-step goals to JASPER's autonomous agent engine")
        subtitle.setStyleSheet("font-size: 11pt; color: #a1a1aa;")
        header_layout.addWidget(subtitle)
        layout.addLayout(header_layout)

        # --- Goal Launcher Card ---
        launcher_card = QFrame()
        launcher_card.setStyleSheet(
            "QFrame {"
            "  background: #1c1c1f;"
            "  border: 1px solid #2e2e34;"
            "  border-radius: 14px;"
            "  padding: 16px;"
            "}"
        )
        launcher_layout = QVBoxLayout(launcher_card)
        launcher_layout.setSpacing(12)

        launcher_title = QLabel("Launch Autonomous Execution")
        launcher_title.setStyleSheet("font-size: 12pt; font-weight: 600; color: #f4f4f5;")
        launcher_layout.addWidget(launcher_title)

        input_row = QHBoxLayout()
        input_row.setSpacing(10)

        self.input_goal = QLineEdit()
        self.input_goal.setObjectName("inputTaskGoal")
        self.input_goal.setPlaceholderText("Describe your goal (e.g. 'Audit active desktop apps and summarize screen')...")
        self.input_goal.setStyleSheet(
            "QLineEdit {"
            "  background: #27272a;"
            "  border: 1px solid #3f3f46;"
            "  border-radius: 10px;"
            "  color: #ffffff;"
            "  font-size: 10.5pt;"
            "  padding: 10px 14px;"
            "}"
            "QLineEdit:focus { border: 1px solid #8ee6a1; }"
        )
        self.input_goal.returnPressed.connect(self._on_launch_clicked)
        input_row.addWidget(self.input_goal, 1)

        self.btn_launch = QPushButton("⚡ Run Task")
        self.btn_launch.setStyleSheet(
            "QPushButton {"
            "  background: #ffffff;"
            "  color: #09090b;"
            "  font-weight: 700;"
            "  border-radius: 10px;"
            "  padding: 10px 20px;"
            "  font-size: 10pt;"
            "  border: none;"
            "}"
            "QPushButton:hover { background: #e4e4e7; }"
        )
        self.btn_launch.clicked.connect(self._on_launch_clicked)
        input_row.addWidget(self.btn_launch)
        launcher_layout.addLayout(input_row)

        hint = QLabel("💡 Autonomous tasks can take screenshots, query tools, run commands, and request approval when necessary.")
        hint.setStyleSheet("font-size: 9pt; color: #71717a;")
        launcher_layout.addWidget(hint)
        layout.addWidget(launcher_card)

        # --- Active Execution Monitor ---
        self.monitor_card = QFrame()
        self.monitor_card.setStyleSheet(
            "QFrame {"
            "  background: #1c1c1f;"
            "  border: 1px solid #2e2e34;"
            "  border-radius: 14px;"
            "  padding: 16px;"
            "}"
        )
        monitor_layout = QVBoxLayout(self.monitor_card)
        monitor_layout.setSpacing(12)

        m_header = QHBoxLayout()
        m_title = QLabel("Current Agent Status")
        m_title.setStyleSheet("font-size: 12pt; font-weight: 600; color: #f4f4f5;")
        m_header.addWidget(m_title)
        m_header.addStretch(1)

        self.status_badge = QLabel("● STANDBY")
        self.status_badge.setStyleSheet(
            "background: #193522; color: #8ee6a1; font-size: 8pt; font-weight: 700; padding: 4px 10px; border-radius: 6px;"
        )
        m_header.addWidget(self.status_badge)
        monitor_layout.addLayout(m_header)

        self.current_goal_lbl = QLabel("No active autonomous task running. Select a suggestion below or enter a goal above.")
        self.current_goal_lbl.setStyleSheet("font-size: 10pt; color: #a1a1aa;")
        self.current_goal_lbl.setWordWrap(True)
        monitor_layout.addWidget(self.current_goal_lbl)

        # Step timeline container
        self.timeline_layout = QVBoxLayout()
        self.timeline_layout.setSpacing(6)
        monitor_layout.addLayout(self.timeline_layout)

        layout.addWidget(self.monitor_card)

        # --- Task Suggestions Section ---
        sugg_header = QLabel("Task Suggestions")
        sugg_header.setStyleSheet("font-size: 13pt; font-weight: 600; color: #e4e4e7; margin-top: 6px;")
        layout.addWidget(sugg_header)

        for sugg in self.TASK_SUGGESTIONS:
            card = self._create_suggestion_card(sugg)
            layout.addWidget(card)

        layout.addStretch(1)
        scroll.setWidget(container)
        root_layout.addWidget(scroll)

    def _create_suggestion_card(self, item: dict[str, Any]) -> QFrame:
        card = QFrame()
        card.setStyleSheet(
            "QFrame {"
            "  background: #1c1c1f;"
            "  border: 1px solid #2e2e34;"
            "  border-radius: 12px;"
            "  padding: 12px 16px;"
            "}"
            "QFrame:hover {"
            "  background: #242428;"
            "  border: 1px solid #3f3f46;"
            "}"
        )
        layout = QHBoxLayout(card)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(14)

        icon_lbl = QLabel(item["icon"])
        icon_lbl.setFixedSize(36, 36)
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_lbl.setStyleSheet("background: #27272e; border-radius: 10px; font-size: 15pt;")
        layout.addWidget(icon_lbl)

        info = QVBoxLayout()
        info.setSpacing(3)

        title_row = QHBoxLayout()
        title_row.setSpacing(8)
        t_lbl = QLabel(item["title"])
        t_lbl.setStyleSheet("font-size: 11pt; font-weight: 600; color: #ffffff;")
        title_row.addWidget(t_lbl)

        b_lbl = QLabel(item["badge"])
        b_lbl.setStyleSheet(
            "background: #27272e; color: #8ee6a1; font-size: 8pt; font-weight: 600; padding: 2px 6px; border-radius: 4px;"
        )
        title_row.addWidget(b_lbl)
        title_row.addStretch(1)
        info.addLayout(title_row)

        desc_lbl = QLabel(item["desc"])
        desc_lbl.setStyleSheet("font-size: 9pt; color: #a1a1aa;")
        desc_lbl.setWordWrap(True)
        info.addWidget(desc_lbl)

        goal_hint = QLabel(f"Goal: \"{item['goal']}\"")
        goal_hint.setStyleSheet("font-size: 8.5pt; color: #71717a; font-style: italic;")
        info.addWidget(goal_hint)
        layout.addLayout(info, 1)

        btn_run = QPushButton("⚡ Run")
        btn_run.setStyleSheet(
            "QPushButton {"
            "  background: #27272e;"
            "  color: #ffffff;"
            "  border: 1px solid #3f3f48;"
            "  border-radius: 8px;"
            "  padding: 7px 16px;"
            "  font-size: 9pt;"
            "  font-weight: 600;"
            "}"
            "QPushButton:hover { background: #3f3f48; }"
        )
        btn_run.clicked.connect(lambda _, it=item: self._launch_suggestion(it))
        layout.addWidget(btn_run)

        return card

    def _on_launch_clicked(self) -> None:
        goal = self.input_goal.text().strip()
        if not goal:
            return
        self.input_goal.clear()
        self._start_task(goal)

    def _launch_suggestion(self, item: dict[str, Any]) -> None:
        self._start_task(item["goal"])

    def _start_task(self, goal: str) -> None:
        self._active_task_goal = goal
        self.status_badge.setText("● EXECUTING")
        self.status_badge.setStyleSheet(
            "background: #1e293b; color: #60a5fa; font-size: 8pt; font-weight: 700; padding: 4px 10px; border-radius: 6px;"
        )
        self.current_goal_lbl.setText(f"Active Goal: {goal}")

        # Add initial timeline step
        self._clear_timeline()
        self._add_timeline_step("Initiating goal", "Delegating task to agent orchestrator...")
        self.task_started.emit(goal)

    def _clear_timeline(self) -> None:
        while self.timeline_layout.count() > 0:
            child = self.timeline_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

    def _add_timeline_step(self, title: str, detail: str) -> None:
        step_frame = QFrame()
        step_frame.setStyleSheet("background: #242428; border-radius: 6px; padding: 6px 10px;")
        l = QHBoxLayout(step_frame)
        l.setContentsMargins(6, 4, 6, 4)
        l.setSpacing(8)

        bullet = QLabel("✓")
        bullet.setStyleSheet("color: #8ee6a1; font-weight: bold;")
        l.addWidget(bullet)

        text = QLabel(f"<b>{title}:</b> {detail}")
        text.setStyleSheet("color: #d4d4d8; font-size: 9pt;")
        l.addWidget(text, 1)

        self.timeline_layout.addWidget(step_frame)

    @Slot()
    def task_completed(self) -> None:
        """Call when orchestrator signals task completion."""
        self.status_badge.setText("● COMPLETED")
        self.status_badge.setStyleSheet(
            "background: #193522; color: #8ee6a1; font-size: 8pt; font-weight: 700; padding: 4px 10px; border-radius: 6px;"
        )
        self._add_timeline_step("Execution Finished", "All planned actions resolved.")
