"""app/ui/approval_dialog.py — Desktop Approval Presentation Layer for JASPER v0.7.

This dialog presents pending ApprovalRequests to the user on the Qt GUI thread.
It does not execute tools, mutate permissions, or make authorization decisions itself.
It only captures the user's explicit decision and emits it associated with the exact gate ID.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from html import escape
from typing import Any

from PySide6.QtCore import Qt, QTimer, Signal, Slot
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.agents.contracts import ProposedAction
from app.core.approval import ApprovalRequest

_LOG = logging.getLogger("jasper.ui.approval_dialog")

DIALOG_STYLE = """
QDialog {
    background: #1c1c1c;
    color: #f1f1f1;
    font-family: "Segoe UI", sans-serif;
    font-size: 10pt;
}
QFrame#headerFrame {
    background: #252525;
    border-bottom: 1px solid #383838;
}
QLabel#titleLabel {
    color: #ffffff;
    font-size: 12pt;
    font-weight: 600;
}
QFrame#detailsFrame {
    background: #222222;
    border: 1px solid #333333;
    border-radius: 8px;
}
QLabel#actionName {
    color: #ffffff;
    font-size: 11pt;
    font-weight: 600;
}
QLabel#riskBadge {
    border-radius: 4px;
    padding: 3px 8px;
    font-weight: 600;
    font-size: 8pt;
}
QLabel#expiryLabel {
    color: #ffb74d;
    font-size: 9pt;
    font-weight: 500;
}
QPushButton#denyButton {
    background: #333333;
    color: #ffffff;
    border: 1px solid #484848;
    border-radius: 6px;
    padding: 8px 22px;
    font-weight: 600;
    min-width: 80px;
}
QPushButton#denyButton:hover {
    background: #444444;
}
QPushButton#allowButton {
    background: #1976d2;
    color: #ffffff;
    border: none;
    border-radius: 6px;
    padding: 8px 22px;
    font-weight: 600;
    min-width: 80px;
}
QPushButton#allowButton:hover {
    background: #2196f3;
}
QPushButton#allowButton:disabled {
    background: #2b3844;
    color: #607282;
}
"""


SENSITIVE_KEY_SUBSTRINGS = (
    "token",
    "secret",
    "password",
    "passwd",
    "pwd",
    "key",
    "credential",
    "auth",
    "private",
)

MAX_STRING_LENGTH = 100
MAX_COLLECTION_ITEMS = 10
MAX_NESTING_DEPTH = 3
MAX_FORMATTED_VALUE_LENGTH = 200

# Regex patterns for defense-in-depth value redaction under generic keys
_BEARER_PATTERN = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9_\-\.]{8,}")
_BASIC_PATTERN = re.compile(r"(?i)\bBasic\s+[A-Za-z0-9+/=]{8,}")
_TOKEN_PREFIX_PATTERN = re.compile(
    r"\b(sk-[a-zA-Z0-9_\-]{16,}|gh[pousr]_[a-zA-Z0-9]{20,}|github_pat_[a-zA-Z0-9_]{20,}|AKIA[0-9A-Z]{16})\b"
)
_PEM_PRIVATE_KEY_PATTERN = re.compile(
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?(?:-----END [A-Z ]*PRIVATE KEY-----|$)"
)
_ASSIGNMENT_PATTERN = re.compile(
    r"(?i)\b((?:api[_-]?key|token|secret|password|passwd|pwd|credential|auth)[_-]?(?:key|token|secret)?\s*[:=]\s*)(['\"]?)([^\s&'\";,]+)\2"
)


def _is_sensitive_key(key: Any) -> bool:
    """Return True if key name contains sensitive substrings."""
    try:
        k_str = str(key).lower()
    except Exception:
        return True
    return any(sub in k_str for sub in SENSITIVE_KEY_SUBSTRINGS)


def _redact_value_patterns(text: str) -> str:
    """Apply defense-in-depth redaction for obvious token/secret patterns in strings.

    Note: This is heuristic and covers common structured patterns (Bearer, Basic,
    known API prefixes, assignment patterns, private keys). It does not claim
    to detect all arbitrary unstructured secrets.
    """
    if not text:
        return text

    # Redact PEM private keys
    text = _PEM_PRIVATE_KEY_PATTERN.sub("[REDACTED_PRIVATE_KEY]", text)

    # Redact Bearer and Basic headers
    text = _BEARER_PATTERN.sub("Bearer [REDACTED]", text)
    text = _BASIC_PATTERN.sub("Basic [REDACTED]", text)

    # Redact known API key prefixes
    text = _TOKEN_PREFIX_PATTERN.sub("[REDACTED]", text)

    # Redact embedded key=val assignments
    text = _ASSIGNMENT_PATTERN.sub(r"\g<1>[REDACTED]", text)

    return text


def _sanitize_value(
    val: Any,
    depth: int = 0,
    max_depth: int = MAX_NESTING_DEPTH,
    seen: set[int] | None = None,
    is_top_level: bool = False,
) -> str:
    """Recursively sanitize an argument value to a bounded string representation."""
    if seen is None:
        seen = set()

    # Cyclic reference guard
    val_id = id(val)
    if isinstance(val, (dict, list, tuple, set)):
        if val_id in seen:
            return "[CIRCULAR_REF]"
        seen = seen | {val_id}

    # Bounded nesting depth
    if depth >= max_depth:
        if isinstance(val, dict):
            return "{...}"
        if isinstance(val, (list, tuple, set)):
            return "[...]"

    # Handle string values
    if isinstance(val, str):
        cleaned = _redact_value_patterns(val)
        if len(cleaned) > MAX_STRING_LENGTH:
            cleaned = cleaned[: MAX_STRING_LENGTH - 3] + "..."
        return cleaned if is_top_level else repr(cleaned)

    # Handle primitive scalars
    if isinstance(val, (int, float, bool)) or val is None:
        return str(val)

    # Handle byte strings
    if isinstance(val, (bytes, bytearray)):
        return f"[bytes: {len(val)} bytes]"

    # Handle nested dictionaries
    if isinstance(val, dict):
        parts: list[str] = []
        for i, (k, v) in enumerate(val.items()):
            if i >= MAX_COLLECTION_ITEMS:
                parts.append(f"... (+{len(val) - MAX_COLLECTION_ITEMS} more)")
                break
            try:
                k_str = str(k)
            except Exception:
                k_str = "[unknown_key]"

            if _is_sensitive_key(k_str):
                v_repr = "[REDACTED]"
            else:
                v_repr = _sanitize_value(v, depth + 1, max_depth, seen, is_top_level=False)

            parts.append(f"{k_str!r}: {v_repr}")

        formatted = "{" + ", ".join(parts) + "}"
        if len(formatted) > MAX_FORMATTED_VALUE_LENGTH:
            formatted = formatted[: MAX_FORMATTED_VALUE_LENGTH - 3] + "..."
        return formatted

    # Handle lists, tuples, sets
    if isinstance(val, (list, tuple, set)):
        is_tuple = isinstance(val, tuple)
        is_set = isinstance(val, set)
        items: list[str] = []
        val_list = list(val)
        for i, item in enumerate(val_list):
            if i >= MAX_COLLECTION_ITEMS:
                items.append(f"... (+{len(val_list) - MAX_COLLECTION_ITEMS} more)")
                break
            items.append(_sanitize_value(item, depth + 1, max_depth, seen, is_top_level=False))

        open_bracket, close_bracket = ("(", ")") if is_tuple else ("{", "}") if is_set else ("[", "]")
        formatted = open_bracket + ", ".join(items) + close_bracket
        if len(formatted) > MAX_FORMATTED_VALUE_LENGTH:
            formatted = formatted[: MAX_FORMATTED_VALUE_LENGTH - 3] + "..."
        return formatted

    # Safe placeholder for unknown or complex types
    try:
        type_name = type(val).__name__
    except Exception:
        type_name = "Unknown"
    return f"[{type_name}]"


def sanitize_arguments(arguments: dict[str, Any] | Any) -> dict[str, str]:
    """Return bounded, sanitized key-value representations of tool arguments.

    Redacts credentials/keys/tokens and limits string length to prevent sensitive
    data exposure or dialog clutter.

    Policy:
    - Redacts values whose top-level keys appear sensitive.
    - Recursively sanitizes nested dictionaries and lists.
    - Replaces unknown/complex objects with safe type placeholders.
    - Applies defense-in-depth redaction for obvious token/secret patterns in strings.
    - Bounds nesting depth, collection size, and string length.
    - Note: Value-based pattern redaction covers common credential formats (Bearer tokens,
      Basic auth, known API prefixes, assignment patterns, private keys). It is a
      defense-in-depth heuristic and does not guarantee detection of arbitrary
      unstructured secrets under generic keys.
    """
    if not isinstance(arguments, dict):
        return {}

    sanitized: dict[str, str] = {}
    for k, v in arguments.items():
        try:
            k_str = str(k)
        except Exception:
            k_str = "[unknown_key]"

        if _is_sensitive_key(k_str):
            sanitized[k_str] = "[REDACTED]"
            continue

        sanitized[k_str] = _sanitize_value(v, depth=0, is_top_level=True)

    return sanitized


class ApprovalDialog(QDialog):
    """User authorization dialog for a pending ApprovalRequest.

    Lifecycle invariants:
    - Emits `decision_made(gate_id, granted)` with the exact gate ID.
    - Default button is Deny; closing, cancelling, or pressing Esc resolves granted=False.
    - Expired requests disable Allow and fail closed.
    - A decision can be emitted at most once per dialog.
    """

    decision_made = Signal(str, bool)  # gate_id, granted

    def __init__(self, request: ApprovalRequest, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.request = request
        self.gate_id = request.gate_id
        self._resolved = False
        self._expired = False
        self._decision: bool | None = None

        self.setWindowTitle("Action Approval Required — JASPER")
        self.setMinimumWidth(480)
        self.setMaximumWidth(580)
        self.setStyleSheet(DIALOG_STYLE)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)

        self._build_ui()
        self._init_timer()

    @property
    def is_resolved(self) -> bool:
        return self._resolved

    @property
    def is_expired(self) -> bool:
        return self._expired

    @property
    def decision(self) -> bool | None:
        return self._decision

    def _build_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Header Frame
        header = QFrame(self, objectName="headerFrame")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(20, 16, 20, 16)
        title = QLabel("Action Requires Your Approval", header, objectName="titleLabel")
        header_layout.addWidget(title)
        header_layout.addStretch(1)

        # Risk badge
        action = self.request.action
        risk_str = (getattr(action.scope, "risk", "HIGH") or "HIGH").upper()
        self.risk_badge = QLabel(f"RISK: {risk_str}", header, objectName="riskBadge")
        if risk_str in {"HIGH", "WRITE", "EXEC", "SYSTEM"}:
            self.risk_badge.setStyleSheet("background: #d32f2f; color: #ffffff;")
        elif risk_str in {"NETWORK", "WEB"}:
            self.risk_badge.setStyleSheet("background: #f57c00; color: #ffffff;")
        elif risk_str in {"READ", "LOW"}:
            self.risk_badge.setStyleSheet("background: #388e3c; color: #ffffff;")
        else:
            self.risk_badge.setStyleSheet("background: #616161; color: #ffffff;")
        header_layout.addWidget(self.risk_badge)
        main_layout.addWidget(header)

        # Content Frame
        content_widget = QWidget(self)
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(20, 18, 20, 18)
        content_layout.setSpacing(14)

        # Action Details Card
        card = QFrame(content_widget, objectName="detailsFrame")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(14, 12, 14, 12)
        card_layout.setSpacing(8)

        self.action_label = QLabel(f"Tool: <b>{escape(action.tool_name)}</b>", card, objectName="actionName")
        card_layout.addWidget(self.action_label)

        operation = getattr(action.scope, "operation", action.tool_name)
        card_layout.addWidget(QLabel(f"Operation: {escape(operation)}", card))

        resource = getattr(action.scope, "resource_scope", "")
        if resource:
            card_layout.addWidget(QLabel(f"Target Resource: <code>{escape(resource)}</code>", card))

        if action.rationale:
            card_layout.addWidget(QLabel(f"Justification: {escape(action.rationale)}", card))

        # Sanitized arguments (bounded)
        if action.arguments and isinstance(action.arguments, dict):
            sanitized = sanitize_arguments(action.arguments)
            args_summary = ", ".join(f"<b>{escape(str(k))}</b>: {escape(str(v))}" for k, v in sanitized.items())
            card_layout.addWidget(QLabel(f"Parameters: {args_summary}", card))

        content_layout.addWidget(card)

        # Expiry countdown
        self.expiry_label = QLabel(self._calc_expiry_text(), content_widget, objectName="expiryLabel")
        content_layout.addWidget(self.expiry_label)

        # Button Bar
        btn_bar = QHBoxLayout()
        btn_bar.setContentsMargins(0, 8, 0, 0)
        btn_bar.setSpacing(12)
        btn_bar.addStretch(1)

        self.deny_btn = QPushButton("Deny", content_widget, objectName="denyButton")
        self.deny_btn.setDefault(True)
        self.deny_btn.clicked.connect(self._on_deny)
        btn_bar.addWidget(self.deny_btn)

        self.allow_btn = QPushButton("Allow", content_widget, objectName="allowButton")
        self.allow_btn.clicked.connect(self._on_allow)
        btn_bar.addWidget(self.allow_btn)

        content_layout.addLayout(btn_bar)
        main_layout.addWidget(content_widget)

    def _init_timer(self) -> None:
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._update_expiry)
        self._timer.start()

    def _calc_expiry_text(self) -> str:
        now = datetime.now(timezone.utc)
        remaining = int((self.request.expires_at - now).total_seconds())
        if remaining <= 0:
            return "Expired"
        return f"Expires in: {remaining}s"

    def _update_expiry(self) -> None:
        now = datetime.now(timezone.utc)
        remaining = int((self.request.expires_at - now).total_seconds())
        if remaining <= 0:
            self.handle_expired()
        else:
            self.expiry_label.setText(f"Expires in: {remaining}s")

    @Slot()
    def _on_allow(self) -> None:
        if self._resolved or self._expired:
            return
        self._resolved = True
        self._decision = True
        self._timer.stop()
        self.decision_made.emit(self.gate_id, True)
        self.accept()

    @Slot()
    def _on_deny(self) -> None:
        if self._resolved:
            return
        self._resolved = True
        self._decision = False
        self._timer.stop()
        self.decision_made.emit(self.gate_id, False)
        self.reject()

    def reject(self) -> None:
        """Called on Esc or explicit reject. Fails closed with decision=False."""
        if not self._resolved:
            self._resolved = True
            self._decision = False
            self._timer.stop()
            self.decision_made.emit(self.gate_id, False)
        super().reject()

    def closeEvent(self, event: QCloseEvent) -> None:
        """Called when dialog is closed via title bar X. Fails closed."""
        if not self._resolved:
            self._resolved = True
            self._decision = False
            self._timer.stop()
            self.decision_made.emit(self.gate_id, False)
        super().closeEvent(event)

    def handle_cancelled(self) -> None:
        """Called when the active request task was cancelled externally."""
        self._timer.stop()
        if not self._resolved:
            self._resolved = True
            self._decision = False
        super().reject()

    def handle_expired(self) -> None:
        """Called when the request expires."""
        self._expired = True
        self._timer.stop()
        self.allow_btn.setEnabled(False)
        self.expiry_label.setText("Expired (Decision Closed)")
        if not self._resolved:
            self._resolved = True
            self._decision = False
            self.decision_made.emit(self.gate_id, False)
        super().reject()
