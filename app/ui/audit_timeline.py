"""app/ui/audit_timeline.py -- Interactive Approval & Audit Timeline Drawer for JASPER.

Provides an inspectable, real-time safety audit ledger displaying tool calls,
permission checks, approval decisions, and agent turns.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.core.audit import get_recent_audit_records

_LOG = logging.getLogger("jasper.ui.audit_timeline")


class AuditTimelineDrawer(QWidget):
    """Slide-out drawer displaying structured audit events and approval histories."""

    drawer_closed = Signal()

    FILTER_ALL = "all"
    FILTER_TOOLS = "tools"
    FILTER_APPROVALS = "approvals"
    FILTER_SECURITY = "security"
    FILTER_TURNS = "turns"

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("auditTimelineDrawer")
        self.setFixedWidth(380)
        self._events: list[dict[str, Any]] = []
        self._active_filter = self.FILTER_ALL
        self._search_query = ""
        self._build_ui()

        # Load any existing audit records
        existing = get_recent_audit_records(limit=100)
        for ev in reversed(existing):
            self._events.append(ev)
        self._refresh_timeline()

    def _build_ui(self) -> None:
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(14, 14, 14, 14)
        root_layout.setSpacing(10)

        # Drawer container styling
        self.setStyleSheet(
            "QWidget#auditTimelineDrawer {"
            "  background-color: #18181b;"
            "  border-left: 1px solid #27272a;"
            "}"
        )

        # --- Top Header ---
        header = QHBoxLayout()
        header.setSpacing(8)

        icon_title = QLabel("🛡️")
        icon_title.setStyleSheet("font-size: 14pt;")
        header.addWidget(icon_title)

        title_col = QVBoxLayout()
        title_col.setSpacing(1)
        title = QLabel("Audit & Safety Timeline")
        title.setStyleSheet("font-size: 11pt; font-weight: 700; color: #ffffff;")
        title_col.addWidget(title)

        self.subtitle = QLabel("0 events recorded")
        self.subtitle.setStyleSheet("font-size: 8.5pt; color: #a1a1aa;")
        title_col.addWidget(self.subtitle)
        header.addLayout(title_col, 1)

        self.btn_close = QPushButton("✕")
        self.btn_close.setFixedSize(26, 26)
        self.btn_close.setStyleSheet(
            "QPushButton {"
            "  background: transparent;"
            "  color: #71717a;"
            "  border-radius: 6px;"
            "  font-size: 11pt;"
            "  font-weight: bold;"
            "}"
            "QPushButton:hover { background: #27272a; color: #ffffff; }"
        )
        self.btn_close.clicked.connect(self._on_close_clicked)
        header.addWidget(self.btn_close)
        root_layout.addLayout(header)

        # --- Metrics Row ---
        metrics_row = QHBoxLayout()
        metrics_row.setSpacing(6)

        self.badge_total = self._create_metric_chip("Total", "0", "#27272a", "#d4d4d8")
        self.badge_tools = self._create_metric_chip("Tools", "0", "#172554", "#60a5fa")
        self.badge_approved = self._create_metric_chip("Approved", "0", "#052e16", "#4ade80")
        self.badge_denied = self._create_metric_chip("Denied", "0", "#450a0a", "#f87171")

        metrics_row.addWidget(self.badge_total)
        metrics_row.addWidget(self.badge_tools)
        metrics_row.addWidget(self.badge_approved)
        metrics_row.addWidget(self.badge_denied)
        root_layout.addLayout(metrics_row)

        # --- Filter Chips ---
        filters_row = QHBoxLayout()
        filters_row.setSpacing(4)
        self.filter_buttons: dict[str, QPushButton] = {}

        filter_specs = [
            ("All", self.FILTER_ALL),
            ("Tools", self.FILTER_TOOLS),
            ("Approvals", self.FILTER_APPROVALS),
            ("Security", self.FILTER_SECURITY),
            ("Turns", self.FILTER_TURNS),
        ]
        for label, key in filter_specs:
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setChecked(key == self.FILTER_ALL)
            btn.setStyleSheet(
                "QPushButton {"
                "  background: #202024;"
                "  color: #a1a1aa;"
                "  border: 1px solid #2e2e34;"
                "  border-radius: 6px;"
                "  padding: 4px 8px;"
                "  font-size: 8.5pt;"
                "  font-weight: 600;"
                "}"
                "QPushButton:checked {"
                "  background: #27272a;"
                "  color: #8ee6a1;"
                "  border: 1px solid #3f3f46;"
                "}"
                "QPushButton:hover { background: #27272a; }"
            )
            btn.clicked.connect(lambda _, k=key: self._set_filter(k))
            self.filter_buttons[key] = btn
            filters_row.addWidget(btn)

        root_layout.addLayout(filters_row)

        # --- Search Filter ---
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Filter actions, files, or tools...")
        self.search_input.setStyleSheet(
            "QLineEdit {"
            "  background: #202024;"
            "  border: 1px solid #2e2e34;"
            "  border-radius: 6px;"
            "  color: #ffffff;"
            "  padding: 5px 8px;"
            "  font-size: 8.5pt;"
            "}"
            "QLineEdit:focus { border: 1px solid #8ee6a1; }"
        )
        self.search_input.textChanged.connect(self._on_search_changed)
        root_layout.addWidget(self.search_input)

        # --- Scroll Area for Timeline Cards ---
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setStyleSheet("background: transparent; border: none;")

        self.cards_container = QWidget()
        self.cards_layout = QVBoxLayout(self.cards_container)
        self.cards_layout.setContentsMargins(0, 0, 0, 0)
        self.cards_layout.setSpacing(6)
        self.cards_layout.addStretch(1)

        self.scroll_area.setWidget(self.cards_container)
        root_layout.addWidget(self.scroll_area, 1)

        # --- Bottom Action Bar ---
        bottom_bar = QHBoxLayout()
        bottom_bar.setSpacing(6)

        self.btn_export = QPushButton("💾 Export...")
        self.btn_export.setStyleSheet(
            "QPushButton {"
            "  background: #27272a;"
            "  color: #d4d4d8;"
            "  border: 1px solid #3f3f46;"
            "  border-radius: 6px;"
            "  padding: 5px 12px;"
            "  font-size: 8.5pt;"
            "  font-weight: 600;"
            "}"
            "QPushButton:hover { background: #3f3f46; color: #ffffff; }"
        )
        self.btn_export.clicked.connect(self._on_export_clicked)
        bottom_bar.addWidget(self.btn_export)

        self.btn_clear = QPushButton("🗑️ Clear")
        self.btn_clear.setStyleSheet(
            "QPushButton {"
            "  background: #27272a;"
            "  color: #d4d4d8;"
            "  border: 1px solid #3f3f46;"
            "  border-radius: 6px;"
            "  padding: 5px 12px;"
            "  font-size: 8.5pt;"
            "  font-weight: 600;"
            "}"
            "QPushButton:hover { background: #3f3f46; color: #ffffff; }"
        )
        self.btn_clear.clicked.connect(self.clear_timeline)
        bottom_bar.addWidget(self.btn_clear)
        bottom_bar.addStretch(1)

        root_layout.addLayout(bottom_bar)

    def _create_metric_chip(self, label: str, value: str, bg: str, fg: str) -> QFrame:
        chip = QFrame()
        chip.setStyleSheet(f"background: {bg}; border-radius: 6px; padding: 4px 6px;")
        l = QVBoxLayout(chip)
        l.setContentsMargins(4, 2, 4, 2)
        l.setSpacing(0)
        l.setAlignment(Qt.AlignmentFlag.AlignCenter)

        val_lbl = QLabel(value)
        val_lbl.setObjectName(f"metric_{label.lower()}")
        val_lbl.setStyleSheet(f"font-size: 10pt; font-weight: 700; color: {fg};")
        val_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        l.addWidget(val_lbl)

        txt_lbl = QLabel(label)
        txt_lbl.setStyleSheet("font-size: 7pt; font-weight: 600; color: #a1a1aa;")
        txt_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        l.addWidget(txt_lbl)

        return chip

    @Slot()
    def _on_close_clicked(self) -> None:
        self.hide()
        self.drawer_closed.emit()

    @Slot(str)
    def _set_filter(self, filter_key: str) -> None:
        self._active_filter = filter_key
        for k, btn in self.filter_buttons.items():
            btn.setChecked(k == filter_key)
        self._refresh_timeline()

    @Slot(str)
    def _on_search_changed(self, text: str) -> None:
        self._search_query = text.strip().lower()
        self._refresh_timeline()

    @Slot(dict)
    def add_event(self, event: dict[str, Any]) -> None:
        """Add one incoming audit record and refresh UI."""
        self._events.append(event)
        self._update_metrics()
        # If event matches current filter, append directly or refresh
        if self._matches_filter(event):
            self._insert_card(event, at_top=True)

    def set_events(self, events: list[dict[str, Any]]) -> None:
        """Replace all events."""
        self._events = list(events)
        self._update_metrics()
        self._refresh_timeline()

    def clear_timeline(self) -> None:
        """Clear recorded events from UI."""
        self._events.clear()
        self._update_metrics()
        self._refresh_timeline()

    def _update_metrics(self) -> None:
        total = len(self._events)
        tools = sum(1 for e in self._events if "tool" in e.get("event", ""))
        approved = sum(1 for e in self._events if e.get("event") == "approval_granted" or e.get("user_approved") is True)
        denied = sum(1 for e in self._events if e.get("event") == "approval_denied" or e.get("user_approved") is False or "denied" in e.get("event", ""))

        self.subtitle.setText(f"{total} events recorded")

        lbl_tot = self.badge_total.findChild(QLabel, "metric_total")
        if lbl_tot:
            lbl_tot.setText(str(total))
        lbl_tls = self.badge_tools.findChild(QLabel, "metric_tools")
        if lbl_tls:
            lbl_tls.setText(str(tools))
        lbl_app = self.badge_approved.findChild(QLabel, "metric_approved")
        if lbl_app:
            lbl_app.setText(str(approved))
        lbl_den = self.badge_denied.findChild(QLabel, "metric_denied")
        if lbl_den:
            lbl_den.setText(str(denied))

    def _matches_filter(self, ev: dict[str, Any]) -> bool:
        event_name = str(ev.get("event", "")).lower()

        # Category filter
        if self._active_filter == self.FILTER_TOOLS:
            if "tool" not in event_name:
                return False
        elif self._active_filter == self.FILTER_APPROVALS:
            if "approval" not in event_name:
                return False
        elif self._active_filter == self.FILTER_SECURITY:
            if not any(k in event_name for k in ("scope", "permission", "budget", "halted")):
                return False
        elif self._active_filter == self.FILTER_TURNS:
            if not any(k in event_name for k in ("planner", "executor", "disagreement")):
                return False

        # Search query filter
        if self._search_query:
            searchable = (
                f"{event_name} {ev.get('tool_name', '')} {ev.get('operation', '')} "
                f"{ev.get('resource', '')} {ev.get('actor', '')} {ev.get('detail', '')} "
                f"{ev.get('status', '')}"
            ).lower()
            if self._search_query not in searchable:
                return False

        return True

    def _refresh_timeline(self) -> None:
        # Clear existing cards
        while self.cards_layout.count() > 1:
            item = self.cards_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        matching = [e for e in self._events if self._matches_filter(e)]

        if not matching:
            empty_lbl = QLabel("No matching audit events.")
            empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty_lbl.setStyleSheet("color: #71717a; font-size: 9pt; padding: 24px;")
            self.cards_layout.insertWidget(0, empty_lbl)
            return

        # Display newest at top
        for ev in reversed(matching):
            self._insert_card(ev, at_top=False)

    def _insert_card(self, ev: dict[str, Any], at_top: bool = False) -> None:
        card = self._create_event_card(ev)
        if at_top:
            self.cards_layout.insertWidget(0, card)
        else:
            idx = max(0, self.cards_layout.count() - 1)
            self.cards_layout.insertWidget(idx, card)

    def _create_event_card(self, ev: dict[str, Any]) -> QFrame:
        card = QFrame()
        card.setStyleSheet(
            "QFrame {"
            "  background: #1f1f23;"
            "  border: 1px solid #2e2e34;"
            "  border-radius: 8px;"
            "  padding: 8px 10px;"
            "}"
            "QFrame:hover {"
            "  background: #25252a;"
            "  border: 1px solid #3f3f46;"
            "}"
        )
        l = QVBoxLayout(card)
        l.setContentsMargins(8, 6, 8, 6)
        l.setSpacing(4)

        # Top row: Event type badge + Timestamp
        top_row = QHBoxLayout()
        top_row.setSpacing(6)

        event_name = str(ev.get("event", "event")).upper()
        badge_bg, badge_fg = self._get_badge_colors(event_name, ev.get("status", "SUCCESS"))

        badge = QLabel(event_name.replace("_", " "))
        badge.setStyleSheet(
            f"background: {badge_bg}; color: {badge_fg}; font-size: 7.5pt; font-weight: 700; "
            "padding: 2px 6px; border-radius: 4px;"
        )
        top_row.addWidget(badge)

        actor = ev.get("actor", "")
        if actor:
            actor_lbl = QLabel(f"by {actor}")
            actor_lbl.setStyleSheet("font-size: 7.5pt; color: #71717a;")
            top_row.addWidget(actor_lbl)

        top_row.addStretch(1)

        raw_ts = ev.get("timestamp", "")
        time_str = ""
        if raw_ts:
            try:
                dt = datetime.fromisoformat(raw_ts)
                time_str = dt.strftime("%H:%M:%S")
            except Exception:
                time_str = raw_ts[:8]
        ts_lbl = QLabel(time_str)
        ts_lbl.setStyleSheet("font-size: 8pt; color: #71717a; font-family: monospace;")
        top_row.addWidget(ts_lbl)
        l.addLayout(top_row)

        # Content row: tool name or resource or operation
        tool_name = ev.get("tool_name", "")
        resource = ev.get("resource", "")
        operation = ev.get("operation", "")
        detail = ev.get("detail", "")

        main_text = ""
        if tool_name:
            main_text = f"Tool: <b>{tool_name}</b>"
            if resource:
                main_text += f" <span style='color:#a1a1aa;'>({resource})</span>"
        elif operation:
            main_text = f"Op: <b>{operation}</b>"
            if resource:
                main_text += f" <span style='color:#a1a1aa;'>({resource})</span>"
        elif detail:
            main_text = detail[:100]
        else:
            main_text = f"Action: {event_name.lower()}"

        text_lbl = QLabel(main_text)
        text_lbl.setStyleSheet("font-size: 8.5pt; color: #e4e4e7;")
        text_lbl.setWordWrap(True)
        l.addWidget(text_lbl)

        # Detail block (expandable / viewable)
        details_frame = QFrame()
        details_frame.setStyleSheet("background: #141416; border-radius: 4px; padding: 6px;")
        details_frame.hide()
        dl = QVBoxLayout(details_frame)
        dl.setContentsMargins(4, 4, 4, 4)
        dl.setSpacing(2)

        dump = json.dumps(ev, indent=2, ensure_ascii=False)
        payload_lbl = QLabel(dump)
        payload_lbl.setStyleSheet("font-family: Consolas, monospace; font-size: 7.5pt; color: #a1a1aa;")
        payload_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        payload_lbl.setWordWrap(True)
        dl.addWidget(payload_lbl)
        l.addWidget(details_frame)

        # Toggle button
        btn_details = QPushButton("Inspect Payload ▾")
        btn_details.setStyleSheet(
            "QPushButton {"
            "  background: transparent;"
            "  color: #71717a;"
            "  border: none;"
            "  font-size: 7.5pt;"
            "  text-align: left;"
            "}"
            "QPushButton:hover { color: #8ee6a1; }"
        )

        def _toggle():
            if details_frame.isVisible():
                details_frame.hide()
                btn_details.setText("Inspect Payload ▾")
            else:
                details_frame.show()
                btn_details.setText("Hide Payload ▴")

        btn_details.clicked.connect(_toggle)
        l.addWidget(btn_details)

        return card

    @staticmethod
    def _get_badge_colors(event: str, status: str) -> tuple[str, str]:
        upper_ev = event.upper()
        if "GRANTED" in upper_ev or status.upper() == "SUCCESS" and "SUCCESS" in upper_ev:
            return "#052e16", "#4ade80"  # Dark green, bright green
        elif "DENIED" in upper_ev or "FAILED" in upper_ev or status.upper() == "FAILED":
            return "#450a0a", "#f87171"  # Dark red, bright red
        elif "REQUESTED" in upper_ev:
            return "#451a03", "#fbbf24"  # Dark amber, bright amber
        elif "TOOL" in upper_ev:
            return "#172554", "#60a5fa"  # Dark blue, bright blue
        elif "PLANNER" in upper_ev or "EXECUTOR" in upper_ev:
            return "#2e1065", "#c084fc"  # Dark purple, bright purple
        else:
            return "#27272a", "#d4d4d8"  # Dark gray, light gray

    @Slot()
    def _on_export_clicked(self) -> None:
        """Export recorded events to a user-selected JSON file."""
        try:
            filename, _ = QFileDialog.getSaveFileName(
                self,
                "Export Audit Ledger",
                f"jasper_audit_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                "JSON Files (*.json)",
            )
            if not filename:
                return
            with open(filename, "w", encoding="utf-8") as f:
                json.dump(self._events, f, indent=2, ensure_ascii=False)
            _LOG.info("Exported %d audit records to %s", len(self._events), filename)
        except Exception as exc:
            _LOG.warning("Failed to export audit ledger: %s", exc)
