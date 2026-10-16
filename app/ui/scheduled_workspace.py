"""app/ui/scheduled_workspace.py -- Real Scheduled tasks workspace with background interval timers and suggestions."""

from __future__ import annotations

import logging
from typing import Any

from PySide6.QtCore import Qt, QTimer, Signal, Slot
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

_LOG = logging.getLogger("jasper.ui.scheduled_workspace")


class ScheduledWorkspace(QWidget):
    """Workspace for creating, scheduling, and automatically running background interval tasks."""

    task_triggered = Signal(str, str)  # (task_name, prompt)

    TASK_SUGGESTIONS = [
        {
            "id": "desktop_error_watcher",
            "title": "Desktop Error Watcher",
            "schedule": "Every 5 mins",
            "interval_sec": 300,
            "description": "Periodically captures your desktop in the background and alerts you if a crash, compiler error, or warning modal appears.",
            "icon": "👁️",
            "prompt": "/screen check all monitors for error dialogs, compilation errors, or crashed processes.",
            "suggestion_tip": "Best for coding and gaming sessions where you want background notification of errors.",
        },
        {
            "id": "test_suite_monitor",
            "title": "Codebase Health & Test Monitor",
            "schedule": "Every 30 mins",
            "interval_sec": 1800,
            "description": "Runs regression tests in the background to ensure your recent edits haven't introduced regressions.",
            "icon": "🧪",
            "prompt": "Run pytest on the test suite and verify all test suites are green.",
            "suggestion_tip": "Great during active development to keep test health green without manual checks.",
        },
        {
            "id": "morning_git_brief",
            "title": "Daily Standup & Git Brief",
            "schedule": "Daily at 9:00 AM",
            "interval_sec": 86400,
            "description": "Summarizes current git branch status, uncommitted files, and upcoming roadmap milestones.",
            "icon": "📋",
            "prompt": "Summarize my current git branch, uncommitted files, and next roadmap milestones.",
            "suggestion_tip": "Start your day with an instant high-level overview of where your work stands.",
        },
        {
            "id": "system_resource_watcher",
            "title": "System & GPU VRAM Monitor",
            "schedule": "Every 15 mins",
            "interval_sec": 900,
            "description": "Checks GPU VRAM, system RAM, and Ollama server responsiveness to prevent out-of-memory lockups.",
            "icon": "⚡",
            "prompt": "Check GPU VRAM, available RAM, and Ollama server responsiveness.",
            "suggestion_tip": "Helpful when running local 14B models or heavy local multi-agent workloads.",
        },
    ]

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("scheduledWorkspace")
        self._timers: dict[str, QTimer] = {}
        self._schedules: list[dict[str, Any]] = []
        self._suggestion_cards: list[QFrame] = []
        self._schedule_rows: list[QFrame] = []
        self._build_ui()
        self._sync_timers()

    def _build_ui(self) -> None:
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(32, 28, 32, 28)
        root_layout.setSpacing(20)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("background: transparent; border: none;")

        container = QWidget()
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(22)

        # --- Header Section ---
        header_layout = QVBoxLayout()
        header_layout.setSpacing(6)

        title = QLabel("Scheduled Tasks & Automated Monitors")
        title.setObjectName("scheduledTitle")
        title.setStyleSheet("font-size: 24pt; font-weight: 700; color: #ffffff;")
        header_layout.addWidget(title)

        subtitle = QLabel("Automate background routines — periodically monitor desktop errors, check code health, or run daily standups.")
        subtitle.setObjectName("scheduledSubtitle")
        subtitle.setStyleSheet("font-size: 11pt; color: #a1a1aa;")
        header_layout.addWidget(subtitle)
        container_layout.addLayout(header_layout)

        # --- What is this for? Explainer Banner ---
        explainer = QFrame()
        explainer.setStyleSheet("background: #1c1c1f; border: 1px solid #2e2e34; border-radius: 12px; padding: 12px 16px;")
        exp_layout = QHBoxLayout(explainer)
        exp_layout.setContentsMargins(12, 10, 12, 10)
        exp_layout.setSpacing(12)

        bulb = QLabel("💡")
        bulb.setStyleSheet("font-size: 16pt;")
        exp_layout.addWidget(bulb)

        exp_text = QLabel(
            "<b>What are Scheduled Tasks for?</b> Active schedules run real background timers. "
            "When active, JASPER automatically checks your desktop for errors, monitors system health, "
            "or executes recurring agent workflows in the background without needing you to type commands repeatedly."
        )
        exp_text.setStyleSheet("color: #d4d4d8; font-size: 9.5pt; line-height: 1.4;")
        exp_text.setWordWrap(True)
        exp_layout.addWidget(exp_text, 1)
        container_layout.addWidget(explainer)

        # --- Search Bar & Create Button ---
        search_row = QHBoxLayout()
        search_row.setSpacing(12)

        self.search_input = QLineEdit()
        self.search_input.setObjectName("scheduledSearch")
        self.search_input.setPlaceholderText("🔍  Search scheduled tasks...")
        self.search_input.setStyleSheet(
            "QLineEdit {"
            "  background: #212124;"
            "  border: 1px solid #333338;"
            "  border-radius: 10px;"
            "  color: #f4f4f5;"
            "  font-size: 10.5pt;"
            "  padding: 10px 14px;"
            "}"
            "QLineEdit:focus { border: 1px solid #8ee6a1; }"
        )
        self.search_input.textChanged.connect(self._filter_tasks)
        search_row.addWidget(self.search_input, 1)

        self.btn_new_task = QPushButton("+ New schedule")
        self.btn_new_task.setObjectName("btnNewSchedule")
        self.btn_new_task.setStyleSheet(
            "QPushButton {"
            "  background: #ffffff;"
            "  color: #09090b;"
            "  font-weight: 700;"
            "  border-radius: 10px;"
            "  padding: 10px 18px;"
            "  font-size: 10pt;"
            "  border: none;"
            "}"
            "QPushButton:hover { background: #e4e4e7; }"
        )
        self.btn_new_task.clicked.connect(self._open_new_schedule_dialog)
        search_row.addWidget(self.btn_new_task)
        container_layout.addLayout(search_row)

        # --- Active Schedules Section ---
        active_header_layout = QHBoxLayout()
        active_header = QLabel("Active Schedules")
        active_header.setStyleSheet("font-size: 13pt; font-weight: 600; color: #e4e4e7; margin-top: 8px;")
        active_header_layout.addWidget(active_header)
        active_header_layout.addStretch(1)

        self.count_label = QLabel(f"{len(self._schedules)} tasks configured")
        self.count_label.setStyleSheet("color: #71717a; font-size: 9.5pt;")
        active_header_layout.addWidget(self.count_label)
        container_layout.addLayout(active_header_layout)

        self.schedules_container = QVBoxLayout()
        self.schedules_container.setSpacing(10)
        self._refresh_schedule_rows()
        container_layout.addLayout(self.schedules_container)

        # --- Suggestions Section ---
        sugg_header = QLabel("Suggested Scheduled Tasks")
        sugg_header.setStyleSheet("font-size: 13pt; font-weight: 600; color: #e4e4e7; margin-top: 14px;")
        container_layout.addWidget(sugg_header)

        self.suggestions_container = QVBoxLayout()
        self.suggestions_container.setSpacing(10)
        for item in self.TASK_SUGGESTIONS:
            card = self._create_suggestion_card(item)
            self._suggestion_cards.append(card)
            self.suggestions_container.addWidget(card)
        container_layout.addLayout(self.suggestions_container)

        container_layout.addStretch(1)
        scroll.setWidget(container)
        root_layout.addWidget(scroll)

    def _create_suggestion_card(self, item: dict[str, Any]) -> QFrame:
        card = QFrame()
        card.setProperty("card_id", item["id"])
        card.setProperty("card_text", f"{item['title']} {item['schedule']} {item['description']}".lower())
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
        layout.setSpacing(16)

        icon_badge = QLabel(item["icon"])
        icon_badge.setFixedSize(38, 38)
        icon_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_badge.setStyleSheet("background: #27272e; border-radius: 10px; font-size: 16pt;")
        layout.addWidget(icon_badge)

        text_layout = QVBoxLayout()
        text_layout.setSpacing(3)

        title_row = QHBoxLayout()
        title_row.setSpacing(8)
        title_lbl = QLabel(item["title"])
        title_lbl.setStyleSheet("font-size: 11pt; font-weight: 600; color: #f4f4f5;")
        title_row.addWidget(title_lbl)

        sched_lbl = QLabel(item["schedule"])
        sched_lbl.setStyleSheet("font-size: 9.5pt; color: #8ee6a1; font-weight: 500;")
        title_row.addWidget(sched_lbl)
        title_row.addStretch(1)
        text_layout.addLayout(title_row)

        desc_lbl = QLabel(item["description"])
        desc_lbl.setStyleSheet("font-size: 9pt; color: #a1a1aa;")
        desc_lbl.setWordWrap(True)
        text_layout.addWidget(desc_lbl)

        tip_lbl = QLabel(f"Tip: {item.get('suggestion_tip', '')}")
        tip_lbl.setStyleSheet("font-size: 8.5pt; color: #71717a; font-style: italic;")
        text_layout.addWidget(tip_lbl)

        layout.addLayout(text_layout, 1)

        # Actions
        btn_add = QPushButton("+ Add Schedule")
        btn_add.setStyleSheet(
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
        btn_add.clicked.connect(lambda _, it=item: self._add_suggestion_as_schedule(it))
        layout.addWidget(btn_add)

        return card

    def _refresh_schedule_rows(self) -> None:
        while self.schedules_container.count() > 0:
            item = self.schedules_container.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        self._schedule_rows.clear()

        if not self._schedules:
            empty_frame = QFrame()
            empty_frame.setStyleSheet(
                "QFrame {"
                "  background: #19191c;"
                "  border: 1px dashed #333338;"
                "  border-radius: 10px;"
                "  padding: 18px;"
                "}"
            )
            e_layout = QVBoxLayout(empty_frame)
            e_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            e_lbl = QLabel("No active schedules configured")
            e_lbl.setStyleSheet("font-size: 10.5pt; font-weight: 600; color: #a1a1aa;")
            e_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            e_sub = QLabel("You have no background tasks running. Click '+ New schedule' above or '+ Add Schedule' from suggestions below to add one manually.")
            e_sub.setStyleSheet("font-size: 9pt; color: #71717a;")
            e_sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
            e_layout.addWidget(e_lbl)
            e_layout.addWidget(e_sub)
            self.schedules_container.addWidget(empty_frame)
        else:
            for sched in self._schedules:
                row = self._create_schedule_row(sched)
                self._schedule_rows.append(row)
                self.schedules_container.addWidget(row)

        self.count_label.setText(f"{len(self._schedules)} tasks configured")

    def _create_schedule_row(self, sched: dict[str, Any]) -> QFrame:
        row = QFrame()
        row.setProperty("sched_id", sched["id"])
        row.setProperty("row_text", f"{sched['title']} {sched['schedule']} {sched.get('prompt', '')}".lower())
        row.setStyleSheet(
            "QFrame {"
            "  background: #1c1c1f;"
            "  border: 1px solid #2e2e34;"
            "  border-radius: 10px;"
            "  padding: 10px 14px;"
            "}"
        )
        layout = QHBoxLayout(row)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(14)

        icon_lbl = QLabel(sched.get("icon", "⏱"))
        icon_lbl.setStyleSheet("font-size: 15pt;")
        layout.addWidget(icon_lbl)

        info_layout = QVBoxLayout()
        info_layout.setSpacing(2)
        title_lbl = QLabel(sched["title"])
        title_lbl.setStyleSheet("font-size: 10.5pt; font-weight: 600; color: #f4f4f5;")
        info_layout.addWidget(title_lbl)

        sched_detail = QLabel(f"Interval: <b>{sched['schedule']}</b> • Action: \"{sched.get('prompt', '')[:50]}...\"")
        sched_detail.setStyleSheet("font-size: 8.5pt; color: #a1a1aa;")
        info_layout.addWidget(sched_detail)
        layout.addLayout(info_layout, 1)

        # Status badge
        is_active = sched.get("status") == "Active"
        status_badge = QLabel("● ACTIVE (ARMED)" if is_active else "○ PAUSED")
        status_badge.setStyleSheet(
            f"font-size: 8pt; font-weight: 700; color: {'#8ee6a1' if is_active else '#71717a'};"
            f"background: {'#193522' if is_active else '#27272a'}; padding: 4px 10px; border-radius: 6px;"
        )
        layout.addWidget(status_badge)

        # Run Now button
        btn_run = QPushButton("▶ Run Now")
        btn_run.setStyleSheet(
            "QPushButton {"
            "  background: #27272a;"
            "  color: #f4f4f5;"
            "  border: 1px solid #3f3f46;"
            "  border-radius: 6px;"
            "  padding: 6px 12px;"
            "  font-size: 8.5pt;"
            "  font-weight: 600;"
            "}"
            "QPushButton:hover { background: #3f3f46; }"
        )
        btn_run.clicked.connect(lambda _, s=sched: self._run_schedule_now(s))
        layout.addWidget(btn_run)

        # Toggle button
        btn_toggle = QPushButton("Pause" if is_active else "Resume")
        btn_toggle.setStyleSheet(
            "QPushButton {"
            "  background: transparent;"
            "  color: #d4d4d8;"
            "  border: 1px solid #3f3f46;"
            "  border-radius: 6px;"
            "  padding: 6px 12px;"
            "  font-size: 8.5pt;"
            "}"
            "QPushButton:hover { color: #ffffff; border: 1px solid #71717a; }"
        )
        btn_toggle.clicked.connect(lambda _, s=sched: self._toggle_schedule(s))
        layout.addWidget(btn_toggle)

        # Delete button
        btn_del = QPushButton("✕")
        btn_del.setFixedSize(26, 26)
        btn_del.setStyleSheet(
            "QPushButton { background: transparent; color: #71717a; border: none; font-size: 10pt; }"
            "QPushButton:hover { color: #ef4444; }"
        )
        btn_del.clicked.connect(lambda _, s=sched: self._delete_schedule(s))
        layout.addWidget(btn_del)

        return row

    @Slot(str)
    def _filter_tasks(self, query: str) -> None:
        q = query.strip().lower()
        for card in self._suggestion_cards:
            text = card.property("card_text") or ""
            card.setVisible(q in text if q else True)

        for row in self._schedule_rows:
            text = row.property("row_text") or ""
            row.setVisible(q in text if q else True)

    def _sync_timers(self) -> None:
        """Arm or disarm actual background QTimers for active schedules."""
        for sched in self._schedules:
            sid = sched["id"]
            if sched.get("status") == "Active":
                if sid not in self._timers:
                    timer = QTimer(self)
                    sec = sched.get("interval_sec", 300)
                    timer.setInterval(sec * 1000)
                    timer.timeout.connect(lambda s=sched: self._on_timer_fire(s))
                    timer.start()
                    self._timers[sid] = timer
            else:
                if sid in self._timers:
                    self._timers[sid].stop()
                    del self._timers[sid]

    def _on_timer_fire(self, sched: dict[str, Any]) -> None:
        _LOG.info("Background scheduled task fired: %s", sched["title"])
        self.task_triggered.emit(sched["title"], sched.get("prompt", ""))

    def _add_suggestion_as_schedule(self, item: dict[str, Any]) -> None:
        if any(s["title"] == item["title"] for s in self._schedules):
            QMessageBox.information(self, "Scheduled tasks", f"'{item['title']}' is already in your active schedule list.")
            return

        new_sched = {
            "id": f"{item['id']}_{len(self._schedules)}",
            "title": item["title"],
            "schedule": item["schedule"],
            "interval_sec": item.get("interval_sec", 300),
            "prompt": item["prompt"],
            "status": "Active",
            "icon": item["icon"],
        }
        self._schedules.append(new_sched)
        self._refresh_schedule_rows()
        self._sync_timers()

    def _run_schedule_now(self, sched: dict[str, Any]) -> None:
        self.task_triggered.emit(sched["title"], sched.get("prompt", ""))

    def _toggle_schedule(self, sched: dict[str, Any]) -> None:
        sched["status"] = "Paused" if sched.get("status") == "Active" else "Active"
        self._refresh_schedule_rows()
        self._sync_timers()

    def _delete_schedule(self, sched: dict[str, Any]) -> None:
        sid = sched["id"]
        if sid in self._timers:
            self._timers[sid].stop()
            del self._timers[sid]
        self._schedules = [s for s in self._schedules if s["id"] != sid]
        self._refresh_schedule_rows()

    def _open_new_schedule_dialog(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("Create Scheduled Task")
        dialog.setFixedWidth(440)
        dialog.setStyleSheet("background: #1c1c1f; color: #f4f4f5;")

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        lbl = QLabel("New Background Schedule")
        lbl.setStyleSheet("font-size: 13pt; font-weight: 700; color: #ffffff;")
        layout.addWidget(lbl)

        layout.addWidget(QLabel("Task Name:"))
        name_input = QLineEdit()
        name_input.setPlaceholderText("e.g. Test Health Monitor, Daily Standup")
        name_input.setStyleSheet("background: #27272a; border: 1px solid #3f3f46; border-radius: 6px; padding: 7px; color: #fff;")
        layout.addWidget(name_input)

        layout.addWidget(QLabel("Schedule Label (e.g. Every 10 mins):"))
        interval_input = QLineEdit()
        interval_input.setText("Every 10 mins")
        interval_input.setStyleSheet("background: #27272a; border: 1px solid #3f3f46; border-radius: 6px; padding: 7px; color: #fff;")
        layout.addWidget(interval_input)

        layout.addWidget(QLabel("Prompt instruction to run:"))
        prompt_input = QLineEdit()
        prompt_input.setPlaceholderText("e.g. /screen check active tasks and alert on errors")
        prompt_input.setStyleSheet("background: #27272a; border: 1px solid #3f3f46; border-radius: 6px; padding: 7px; color: #fff;")
        layout.addWidget(prompt_input)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.setStyleSheet("QPushButton { background: #3f3f46; color: white; border-radius: 6px; padding: 6px 14px; }")
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        if dialog.exec() == QDialog.DialogCode.Accepted:
            title = name_input.text().strip() or "Custom Task"
            sched = interval_input.text().strip() or "Manual"
            p = prompt_input.text().strip() or title
            self._schedules.append({
                "id": f"custom_{len(self._schedules)}",
                "title": title,
                "schedule": sched,
                "interval_sec": 600,
                "prompt": p,
                "status": "Active",
                "icon": "⏱",
            })
            self._refresh_schedule_rows()
            self._sync_timers()
