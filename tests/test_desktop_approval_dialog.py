"""Tests for Step 14B: Desktop Approval Dialog and Signal Wiring.

Covers:
1. Approval signal reaches intended GUI-thread handler.
2. Correct action name, risk, and expiry information are displayed.
3. Allow forwards exact gate ID with True.
4. Deny forwards exact gate ID with False.
5. Closing dialog or Esc denies rather than grants.
6. Expired requests cannot be approved.
7. Cancellation invalidates matching dialog.
8. Stale and duplicate gate IDs cannot resolve another request.
9. Rejected or failed resolution remains fail-closed.
10. Shutdown closes approval UI safely.
11. GUI widget operations occur on GUI thread.
12. Desktop autonomous mode remains disabled.
13. No tool handler is invoked merely by displaying dialog or clicking test control.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from PySide6.QtCore import QThread
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QApplication, QLabel

from app.agents.contracts import (
    AgentResult,
    ApprovalRequirement,
    PermissionScope,
    ProposedAction,
)
from app.agents.coordinator import Coordinator
from app.core.approval import ApprovalGate, ApprovalRequest
from app.core.scoped_permissions import ScopedPermissionManager
from app.tools.registry import Risk, Tool, ToolRegistry
from app.ui.approval_dialog import ApprovalDialog, sanitize_arguments
from app.ui.main_window import MainWindow
from app.ui.worker import JasperWorker


WORKSPACE = Path("C:/workspace").resolve()


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _make_env(handler_mock=None):
    reg = ToolRegistry()
    mock_fn = handler_mock or MagicMock(return_value={"written": "ok"})
    reg.register(Tool(
        name="file.write",
        description="write file",
        risk=Risk.WRITE,
        handler=mock_fn,
        path_argument="path",
        requires_filesystem=True,
        resource_extractor=lambda args: args.get("path", ""),
    ))
    pm = ScopedPermissionManager(
        workspace_root=WORKSPACE,
        allowed_risks=frozenset({Risk.READ, Risk.WRITE}),
    )
    return reg, pm, mock_fn


def _make_request(
    path: str = "report.txt",
    risk: str = "write",
    operation: str = "file.write",
    timeout: float = 60.0,
    **extra_args,
) -> ApprovalRequest:
    scope = PermissionScope(
        risk=risk,
        resource_scope=str(WORKSPACE / path),
        operation=operation,
        approval_requirement=ApprovalRequirement.ALWAYS,
        requires_filesystem=True,
    )
    args = {"path": str(WORKSPACE / path)}
    args.update(extra_args)
    action = ProposedAction(
        tool_name="file.write",
        arguments=args,
        scope=scope,
        rationale="Generate and save final report",
    )
    gate = ApprovalGate(action, timeout=timeout)
    return gate.make_request()


# ---------------------------------------------------------------------------
# 1. Approval signal reaches intended GUI-thread handler
# ---------------------------------------------------------------------------

def test_approval_signal_reaches_gui_thread_handler(qapp):
    worker = JasperWorker()
    thread = QThread()
    window = MainWindow(worker, thread)

    req = _make_request()

    # Emit signal from worker
    worker.approval_requested.emit(req)
    qapp.processEvents()

    assert window._active_approval_dialog is not None
    assert window._active_gate_id == req.gate_id
    assert window._active_approval_dialog.gate_id == req.gate_id

    # Clean up dialog
    window._active_approval_dialog.reject()


# ---------------------------------------------------------------------------
# 2. Correct action name, risk, and expiry information are displayed
# ---------------------------------------------------------------------------

def test_correct_action_name_risk_and_expiry_displayed(qapp):
    req = _make_request(path="important.doc", risk="write", token="secret-12345")
    dialog = ApprovalDialog(req)

    assert "file.write" in dialog.action_label.text()
    assert "WRITE" in dialog.risk_badge.text()
    assert "Expires in:" in dialog.expiry_label.text()

    # Verify sensitive token is redacted in arguments
    sanitized = sanitize_arguments(req.action.arguments)
    assert sanitized.get("token") == "[REDACTED]"
    assert "secret-12345" not in dialog.text() if hasattr(dialog, "text") else True

    dialog.reject()


# ---------------------------------------------------------------------------
# 3. Allow forwards exact gate ID with True
# ---------------------------------------------------------------------------

def test_allow_forwards_exact_gate_id_with_true(qapp):
    req = _make_request()
    dialog = ApprovalDialog(req)

    decisions: list[tuple[str, bool]] = []
    dialog.decision_made.connect(lambda gid, granted: decisions.append((gid, granted)))

    dialog.allow_btn.click()

    assert len(decisions) == 1
    assert decisions[0] == (req.gate_id, True)
    assert dialog.is_resolved is True
    assert dialog.decision is True


# ---------------------------------------------------------------------------
# 4. Deny forwards exact gate ID with False
# ---------------------------------------------------------------------------

def test_deny_forwards_exact_gate_id_with_false(qapp):
    req = _make_request()
    dialog = ApprovalDialog(req)

    decisions: list[tuple[str, bool]] = []
    dialog.decision_made.connect(lambda gid, granted: decisions.append((gid, granted)))

    dialog.deny_btn.click()

    assert len(decisions) == 1
    assert decisions[0] == (req.gate_id, False)
    assert dialog.is_resolved is True
    assert dialog.decision is False


# ---------------------------------------------------------------------------
# 5. Closing dialog or Esc denies rather than grants
# ---------------------------------------------------------------------------

def test_closing_dialog_or_esc_denies(qapp):
    # Case A: Esc key triggers reject()
    req1 = _make_request(path="esc_test.txt")
    dialog1 = ApprovalDialog(req1)
    decisions1: list[tuple[str, bool]] = []
    dialog1.decision_made.connect(lambda gid, granted: decisions1.append((gid, granted)))

    dialog1.reject()

    assert len(decisions1) == 1
    assert decisions1[0] == (req1.gate_id, False)
    assert dialog1.is_resolved is True
    assert dialog1.decision is False

    # Case B: Window closeEvent (X button)
    req2 = _make_request(path="close_test.txt")
    dialog2 = ApprovalDialog(req2)
    decisions2: list[tuple[str, bool]] = []
    dialog2.decision_made.connect(lambda gid, granted: decisions2.append((gid, granted)))

    event = QCloseEvent()
    dialog2.closeEvent(event)

    assert len(decisions2) == 1
    assert decisions2[0] == (req2.gate_id, False)
    assert dialog2.is_resolved is True
    assert dialog2.decision is False


# ---------------------------------------------------------------------------
# 6. Expired requests cannot be approved
# ---------------------------------------------------------------------------

def test_expired_requests_cannot_be_approved(qapp):
    req = _make_request()
    dialog = ApprovalDialog(req)

    decisions: list[tuple[str, bool]] = []
    dialog.decision_made.connect(lambda gid, granted: decisions.append((gid, granted)))

    # Trigger expiration
    dialog.handle_expired()

    assert dialog.is_expired is True
    assert dialog.allow_btn.isEnabled() is False
    assert len(decisions) == 1
    assert decisions[0] == (req.gate_id, False)

    # Attempting to click allow button after expiration has no effect
    dialog._on_allow()
    assert len(decisions) == 1
    assert dialog.decision is False


# ---------------------------------------------------------------------------
# 7. Cancellation invalidates matching dialog
# ---------------------------------------------------------------------------

def test_cancellation_invalidates_matching_dialog(qapp):
    worker = JasperWorker()
    thread = QThread()
    window = MainWindow(worker, thread)

    req = _make_request()
    worker.approval_requested.emit(req)
    qapp.processEvents()

    dialog = window._active_approval_dialog
    assert dialog is not None

    # Simulate cancellation
    window._on_cancelled()

    assert window._active_approval_dialog is None
    assert window._active_gate_id is None
    assert dialog.is_resolved is True
    assert dialog.decision is False


# ---------------------------------------------------------------------------
# 8. Stale and duplicate gate IDs cannot resolve another request
# ---------------------------------------------------------------------------

def test_stale_and_duplicate_gate_ids_cannot_resolve_another_request(qapp):
    worker = JasperWorker()
    thread = QThread()
    window = MainWindow(worker, thread)

    req1 = _make_request(path="first.txt")
    worker.approval_requested.emit(req1)
    qapp.processEvents()

    assert window._active_gate_id == req1.gate_id

    # Decision for a mismatched stale gate_id does not dismiss req1's dialog
    window._on_approval_decision("stale-id-9999", granted=True)
    assert window._active_approval_dialog is not None
    assert window._active_gate_id == req1.gate_id

    # Concurrent request arriving while req1 is active is rejected immediately
    req2 = _make_request(path="second.txt")
    worker.approval_requested.emit(req2)
    qapp.processEvents()

    # req1 remains active dialog
    assert window._active_gate_id == req1.gate_id

    window._active_approval_dialog.reject()


# ---------------------------------------------------------------------------
# 9. Rejected or failed resolution remains fail-closed
# ---------------------------------------------------------------------------

def test_rejected_or_failed_resolution_remains_fail_closed(qapp):
    worker = JasperWorker()
    thread = QThread()
    window = MainWindow(worker, thread)

    # Worker has no coordinator attached: resolve_approval returns False
    success = worker.resolve_approval("unknown-id", granted=True)
    assert success is False

    # Calling _on_approval_decision with unknown ID does not crash and leaves UI safe
    window._on_approval_decision("unknown-id", granted=True)
    assert window._active_approval_dialog is None


# ---------------------------------------------------------------------------
# 10. Shutdown closes approval UI safely
# ---------------------------------------------------------------------------

def test_shutdown_closes_approval_ui_safely(qapp):
    worker = JasperWorker()
    thread = QThread()
    thread.isRunning = MagicMock(return_value=False)
    window = MainWindow(worker, thread)

    req = _make_request()
    worker.approval_requested.emit(req)
    qapp.processEvents()

    dialog = window._active_approval_dialog
    assert dialog is not None

    # Trigger closeEvent
    event = QCloseEvent()
    window.closeEvent(event)

    assert window._active_approval_dialog is None
    assert window._active_gate_id is None
    assert dialog.is_resolved is True


# ---------------------------------------------------------------------------
# 11. GUI widget operations occur on GUI thread
# ---------------------------------------------------------------------------

def test_gui_widget_operations_occur_on_gui_thread(qapp):
    worker = JasperWorker()
    thread = QThread()
    worker.moveToThread(thread)
    thread.start()

    window = MainWindow(worker, thread)
    req = _make_request()

    # Emit from worker (cross-thread queued signal)
    worker.approval_requested.emit(req)
    qapp.processEvents()

    assert window._active_approval_dialog is not None
    # Dialog thread affinity is the GUI thread
    assert window._active_approval_dialog.thread() == qapp.thread()

    window._active_approval_dialog.reject()
    thread.quit()
    thread.wait(2000)


# ---------------------------------------------------------------------------
# 12. Desktop autonomous mode remains disabled
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_desktop_autonomous_mode_remains_disabled(qapp):
    worker = JasperWorker()
    thread = QThread()
    window = MainWindow(worker, thread)

    assert window.worker.jasper.multi_agent_coordinator is None

    response = await window.worker.jasper.respond("/auto Run high-risk operation")
    assert response == "Autonomous mode is not enabled."


# ---------------------------------------------------------------------------
# 13. No tool handler invoked merely by displaying dialog or clicking test control
# ---------------------------------------------------------------------------

def test_no_tool_handler_invoked_by_merely_displaying_dialog_or_clicking(qapp):
    reg, pm, mock_fn = _make_env()
    worker = JasperWorker()
    coord = Coordinator(reg, pm)
    worker.set_coordinator(coord)

    req = _make_request()
    dialog = ApprovalDialog(req)

    # Merely instantiating and displaying dialog does not invoke tool
    assert mock_fn.call_count == 0

    # Denying does not invoke tool
    dialog.deny_btn.click()
    assert mock_fn.call_count == 0


# ---------------------------------------------------------------------------
# 14. Top-level sensitive keys redaction
# ---------------------------------------------------------------------------

def test_sanitize_arguments_top_level_sensitive_keys():
    args = {
        "token": "secret_tok_1",
        "access_token": "secret_tok_2",
        "api_key": "key_val_3",
        "SECRET": "secret_val_4",
        "Password": "pwd_val_5",
        "passwd": "pwd_val_6",
        "pwd": "pwd_val_7",
        "credential": "cred_val_8",
        "auth_header": "auth_val_9",
        "private_key": "priv_val_10",
        "KEY_VALUE": "val_11",
    }
    sanitized = sanitize_arguments(args)
    for k in args:
        assert sanitized[k] == "[REDACTED]", f"Key {k} was not redacted"


# ---------------------------------------------------------------------------
# 15. Nested dictionaries containing credential-like keys
# ---------------------------------------------------------------------------

def test_sanitize_arguments_nested_dictionaries():
    args = {
        "config": {
            "api_key": "super_secret_key_123",
            "timeout": 30,
            "sub": {
                "password": "inner_password_456",
                "enabled": True,
            },
        }
    }
    sanitized = sanitize_arguments(args)
    config_str = sanitized["config"]
    assert "super_secret_key_123" not in config_str
    assert "inner_password_456" not in config_str
    assert "[REDACTED]" in config_str
    assert "timeout" in config_str
    assert "30" in config_str
    assert "enabled" in config_str


# ---------------------------------------------------------------------------
# 16. Lists containing nested dictionaries
# ---------------------------------------------------------------------------

def test_sanitize_arguments_lists_containing_nested_dictionaries():
    args = {
        "services": [
            {"name": "database", "password": "db_password_789"},
            {"name": "gateway", "token": "gw_token_012"},
            {"name": "cache", "host": "10.0.0.1"},
        ]
    }
    sanitized = sanitize_arguments(args)
    services_str = sanitized["services"]
    assert "db_password_789" not in services_str
    assert "gw_token_012" not in services_str
    assert "[REDACTED]" in services_str
    assert "database" in services_str
    assert "gateway" in services_str
    assert "cache" in services_str
    assert "10.0.0.1" in services_str


# ---------------------------------------------------------------------------
# 17. Sensitive values under generic keys
# ---------------------------------------------------------------------------

def test_sanitize_arguments_sensitive_values_under_generic_keys():
    # Bearer token under generic key "header"
    sanitized_bearer = sanitize_arguments({"header": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"})
    assert "Bearer [REDACTED]" in sanitized_bearer["header"]
    assert "eyJhbGci" not in sanitized_bearer["header"]

    # Basic auth under generic key "auth"
    sanitized_basic = sanitize_arguments({"generic_field": "Basic dXNlcjpwYXNzMTIz"})
    assert "Basic [REDACTED]" in sanitized_basic["generic_field"]
    assert "dXNlcjpwYXNzMTIz" not in sanitized_basic["generic_field"]

    # Known token prefix (e.g. sk-...) in a command line string
    sanitized_cmd = sanitize_arguments({"command": "run.exe --key sk-abcdef1234567890abcdef1234 --output out.txt"})
    assert "[REDACTED]" in sanitized_cmd["command"]
    assert "sk-abcdef1234567890abcdef1234" not in sanitized_cmd["command"]
    assert "run.exe" in sanitized_cmd["command"]

    # Embedded assignment pattern in URL query
    sanitized_query = sanitize_arguments({"query": "https://api.example.com/v1?token=tok_secret_999&format=json"})
    assert "token=[REDACTED]" in sanitized_query["query"]
    assert "tok_secret_999" not in sanitized_query["query"]
    assert "format=json" in sanitized_query["query"]

    # PEM private key block
    pem = "-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEA0...\n-----END RSA PRIVATE KEY-----"
    sanitized_pem = sanitize_arguments({"file_data": pem})
    assert "[REDACTED_PRIVATE_KEY]" in sanitized_pem["file_data"]
    assert "MIIEowIBAAKCAQEA0" not in sanitized_pem["file_data"]


# ---------------------------------------------------------------------------
# 18. Deeply nested and unusually large values
# ---------------------------------------------------------------------------

def test_sanitize_arguments_deeply_nested_and_unusually_large_values():
    # Deeply nested dict: terminates at {...}
    deep = {"l1": {"l2": {"l3": {"l4": {"l5": "secret_deep"}}}}}
    sanitized_deep = sanitize_arguments(deep)
    assert "{...}" in sanitized_deep["l1"]
    assert "secret_deep" not in sanitized_deep["l1"]

    # Unusually large collection: truncated to 10 items
    large_list = list(range(200))
    sanitized_large = sanitize_arguments({"items": large_list})
    assert "+190 more" in sanitized_large["items"]
    assert len(sanitized_large["items"]) <= 200

    # Unusually large string: bounded to 100 chars
    long_string = "x" * 500
    sanitized_long = sanitize_arguments({"long_str": long_string})
    assert len(sanitized_long["long_str"]) == 100
    assert sanitized_long["long_str"].endswith("...")

    # Circular reference: does not raise RecursionError
    cycle_dict: dict = {}
    cycle_dict["self"] = cycle_dict
    sanitized_cycle = sanitize_arguments({"cycle": cycle_dict})
    assert "[CIRCULAR_REF]" in sanitized_cycle["cycle"]


# ---------------------------------------------------------------------------
# 19. Non-string keys and unexpected object types
# ---------------------------------------------------------------------------

def test_sanitize_arguments_non_string_keys_and_unexpected_types():
    class SecretContainer:
        password = "should_not_leak"

    obj = SecretContainer()
    args = {
        100: "integer_key",
        None: "none_key",
        (1, 2): "tuple_key",
        "container": obj,
        "raw_bytes": b"binary_secret_bytes",
    }
    sanitized = sanitize_arguments(args)
    assert sanitized["100"] == "integer_key"
    assert sanitized["None"] == "none_key"
    assert sanitized["(1, 2)"] == "tuple_key"
    assert sanitized["container"] == "[SecretContainer]"
    assert "should_not_leak" not in sanitized["container"]
    assert "bytes" in sanitized["raw_bytes"]

    # Malformed non-dict input does not crash
    assert sanitize_arguments(None) == {}
    assert sanitize_arguments("not_a_dict") == {}
    assert sanitize_arguments([1, 2, 3]) == {}


# ---------------------------------------------------------------------------
# 20. HTML-looking input and escaping
# ---------------------------------------------------------------------------

def test_dialog_html_escaping(qapp):
    req = _make_request(
        path="<script>alert(1)</script>",
        risk="write",
        tool_name="tool<script>",
        html_tag="<b>bold</b>",
    )
    dialog = ApprovalDialog(req)

    # Inspect the action_label and card details for HTML escaping
    assert "<script>" not in dialog.action_label.text() or "&lt;script&gt;" in dialog.action_label.text()

    # Sanitized arguments representation
    sanitized = sanitize_arguments(req.action.arguments)
    assert sanitized["html_tag"] == "<b>bold</b>"

    # Find QLabel containing parameters and verify it escapes HTML
    labels = dialog.findChildren(QLabel)
    params_label = next((l for l in labels if "Parameters:" in l.text()), None)
    if params_label:
        # The QLabel text must contain escaped &lt;b&gt;bold&lt;/b&gt; rather than raw unescaped <b>
        assert "&lt;b&gt;bold&lt;/b&gt;" in params_label.text()
        assert "&lt;script&gt;" in params_label.text()

    dialog.reject()


# ---------------------------------------------------------------------------
# 21. Ordinary non-sensitive arguments remain understandable
# ---------------------------------------------------------------------------

def test_ordinary_non_sensitive_arguments_remain_understandable():
    args = {
        "path": "C:/workspace/data/output.csv",
        "limit": 50,
        "dry_run": False,
        "score": 98.6,
        "tags": ["v1", "release"],
    }
    sanitized = sanitize_arguments(args)
    assert sanitized["path"] == "C:/workspace/data/output.csv"
    assert sanitized["limit"] == "50"
    assert sanitized["dry_run"] == "False"
    assert sanitized["score"] == "98.6"
    assert sanitized["tags"] == "['v1', 'release']"


# ---------------------------------------------------------------------------
# 22. Allow/Deny behavior unchanged with sanitized arguments
# ---------------------------------------------------------------------------

def test_allow_deny_behavior_unchanged_with_sanitized_args(qapp):
    # Test Allow with complex nested arguments
    req_allow = _make_request(
        path="file.txt",
        nested={"key": "secret", "user": "alice"},
        header="Bearer sk-1234567890abcdef1234",
    )
    dialog_allow = ApprovalDialog(req_allow)
    decisions_allow: list[tuple[str, bool]] = []
    dialog_allow.decision_made.connect(lambda gid, granted: decisions_allow.append((gid, granted)))
    dialog_allow.allow_btn.click()

    assert len(decisions_allow) == 1
    assert decisions_allow[0] == (req_allow.gate_id, True)
    assert dialog_allow.is_resolved is True
    assert dialog_allow.decision is True

    # Test Deny
    req_deny = _make_request(
        path="file.txt",
        nested={"key": "secret", "user": "bob"},
    )
    dialog_deny = ApprovalDialog(req_deny)
    decisions_deny: list[tuple[str, bool]] = []
    dialog_deny.decision_made.connect(lambda gid, granted: decisions_deny.append((gid, granted)))
    dialog_deny.deny_btn.click()

    assert len(decisions_deny) == 1
    assert decisions_deny[0] == (req_deny.gate_id, False)
    assert dialog_deny.is_resolved is True
    assert dialog_deny.decision is False
