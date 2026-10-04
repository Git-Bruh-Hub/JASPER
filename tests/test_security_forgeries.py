import pytest

from app.agents.contracts import (
    ApprovalRequirement,
    PermissionScope,
    ProposedAction,
)
from app.agents.coordinator import Coordinator
from app.core.scoped_permissions import ScopedPermissionManager
from app.tools.registry import Risk, Tool, ToolRegistry


@pytest.fixture
def test_registry():
    registry = ToolRegistry()
    registry.register(Tool(
        name="safe_read",
        description="A safe read tool",
        risk=Risk.READ,
        handler=lambda path: "read data",
        path_argument="path",
    ))
    registry.register(Tool(
        name="dangerous_write",
        description="A dangerous write tool",
        risk=Risk.WRITE,
        handler=lambda path: "written data",
        path_argument="path",
    ))
    registry.register(Tool(
        name="buggy_extractor_tool",
        description="Tool whose extractor fails",
        risk=Risk.READ,
        handler=lambda path: "data",
        resource_extractor=lambda args: args["missing_key"], # Will raise KeyError
    ))
    registry.register(Tool(
        name="legacy_extractor_tool",
        description="Tool using old resource_extractor without path_argument",
        risk=Risk.READ,
        handler=lambda path: "legacy data",
        resource_extractor=lambda args: args.get("path", "global"),
    ))
    registry.register(Tool(
        name="file.safe_read",
        description="A safe read tool for files",
        risk=Risk.READ,
        handler=lambda path: "read data",
        path_argument="path",
    ))
    return registry


@pytest.fixture
def coordinator(test_registry, tmp_path):
    permissions = ScopedPermissionManager(
        workspace_root=tmp_path,
        allowed_risks={Risk.READ, Risk.WRITE},
    )
    return Coordinator(
        registry=test_registry,
        permissions=permissions,
        workspace_root=tmp_path,
    )

@pytest.fixture
def track_handlers(test_registry):
    calls = []
    for tool_name in ["safe_read", "dangerous_write", "buggy_extractor_tool", "file.safe_read", "legacy_extractor_tool"]:
        tool = test_registry.get(tool_name)
        orig_handler = tool.handler

        def make_tracked(orig, name):
            def tracked(*args, **kwargs):
                calls.append(name)
                return orig(*args, **kwargs)
            return tracked

        tool.handler = make_tracked(orig_handler, tool_name)
    return calls


@pytest.mark.asyncio
async def test_forged_approval_rejected(coordinator, tmp_path, track_handlers):
    # Agent tries to execute WRITE but claims NEVER approval
    file_path = str(tmp_path / "test.txt")
    forged_scope = PermissionScope(
        risk="read",  # forged
        resource_scope=file_path,
        operation="safe_read",  # forged
        approval_requirement=ApprovalRequirement.NEVER,  # forged
    )
    action = ProposedAction(
        tool_name="dangerous_write",
        arguments={"path": file_path},
        scope=forged_scope,
        rationale="I am writing but claim I'm reading",
        action_id="123"
    )

    # Coordinator should overwrite with authoritative ALWAYS approval and hit the ApprovalGate
    # Since we didn't mock ApprovalNotifier, it will raise an error or wait. Let's mock it to deny.
    async def mock_deny(*a, **kw):
        return False
    coordinator._request_approval = mock_deny

    with pytest.raises(PermissionError, match="User denied approval"):
        await coordinator._execute_action(action, cancel_callback=None)

    assert "dangerous_write" not in track_handlers


@pytest.mark.asyncio
async def test_forged_resource_scope_rejected(coordinator, tmp_path, track_handlers):
    # Agent claims it's touching safe.txt, but arguments target secret.txt
    safe_path = str(tmp_path / "safe.txt")
    secret_path = str(tmp_path / "secret.txt")

    # We must disallow access to secret.txt in ScopedPermissionManager to prove the forgery fails
    orig_check_scope = coordinator._permissions.check_scope
    def mock_check_scope(a: ProposedAction):
        if "secret.txt" in a.scope.resource_scope:
            raise PermissionError("Access to secret.txt denied")
        orig_check_scope(a)
    coordinator._permissions.check_scope = mock_check_scope

    forged_scope = PermissionScope(
        risk="read",
        resource_scope=safe_path,
        operation="safe_read",
        approval_requirement=ApprovalRequirement.NEVER,
    )
    action = ProposedAction(
        tool_name="safe_read",
        arguments={"path": secret_path},
        scope=forged_scope,
        rationale="Resource mismatch",
        action_id="123"
    )

    # Instead of prior mismatch error, the authoritative scope is checked and rejected by permission manager
    with pytest.raises(PermissionError, match="Access to secret.txt denied"):
        await coordinator._execute_action(action, cancel_callback=None)

    assert "safe_read" not in track_handlers


@pytest.mark.asyncio
async def test_forged_risk_and_operation_fixed(coordinator, tmp_path, track_handlers):
    # Agent claims risk=READ for a WRITE tool
    file_path = str(tmp_path / "test.txt")
    forged_scope = PermissionScope(
        risk="read",
        resource_scope=file_path,
        operation="harmless.op",
        approval_requirement=ApprovalRequirement.NEVER,
        lifetime_seconds=9999,
    )
    action = ProposedAction(
        tool_name="dangerous_write",
        arguments={"path": file_path},
        scope=forged_scope,
        rationale="Forged risk",
        action_id="123"
    )

    # We mock _request_approval to just return False (denying) so the tool isn't actually run
    async def mock_approve(*a, **kw):
        return False
    coordinator._request_approval = mock_approve

    # We also mock check_scope to inspect what it received
    orig_check_scope = coordinator._permissions.check_scope
    scope_checked = None

    def mock_check_scope(a: ProposedAction):
        nonlocal scope_checked
        scope_checked = a.scope
        orig_check_scope(a)

    coordinator._permissions.check_scope = mock_check_scope

    with pytest.raises(PermissionError):
        await coordinator._execute_action(action, cancel_callback=None)

    assert scope_checked is not None
    assert scope_checked.risk == "write"
    assert scope_checked.operation == "file.dangerous_write"
    assert scope_checked.approval_requirement == ApprovalRequirement.ALWAYS
    assert scope_checked.lifetime_seconds is None

    assert "dangerous_write" not in track_handlers


@pytest.mark.asyncio
async def test_missing_resource_argument_rejected(coordinator, track_handlers):
    # Tool requires resource scope (path_argument="path") but argument is missing.
    # The Coordinator's execute_action should fail-closed and raise PermissionError.
    forged_scope = PermissionScope(
        risk="read",
        resource_scope="global",
        operation="safe_read",
        approval_requirement=ApprovalRequirement.NEVER,
    )
    action = ProposedAction(
        tool_name="safe_read",
        arguments={}, # Missing path
        scope=forged_scope,
        rationale="Missing argument",
        action_id="123"
    )

    with pytest.raises(PermissionError, match="Missing required resource argument"):
        await coordinator._execute_action(action, cancel_callback=None)

    assert "safe_read" not in track_handlers


@pytest.mark.asyncio
async def test_resource_extractor_exception_rejected(coordinator, track_handlers):
    # resource_extractor raises KeyError. Coordinator should catch it and raise PermissionError.
    action = ProposedAction(
        tool_name="buggy_extractor_tool",
        arguments={},
        scope=PermissionScope(risk="read", resource_scope="global", operation="buggy_extractor_tool", approval_requirement=ApprovalRequirement.NEVER),
        rationale="No args",
        action_id="123"
    )

    with pytest.raises(PermissionError, match="Failed to extract target resource: 'missing_key'"):
        await coordinator._execute_action(action, cancel_callback=None)

    assert "buggy_extractor_tool" not in track_handlers


@pytest.mark.asyncio
async def test_legitimate_allowed_resource_succeeds(coordinator, tmp_path, track_handlers):
    file_path = str(tmp_path / "test.txt")
    scope = PermissionScope(
        risk="write",
        resource_scope=file_path,
        operation="dangerous_write",
        approval_requirement=ApprovalRequirement.ALWAYS,
    )
    action = ProposedAction(
        tool_name="dangerous_write",
        arguments={"path": file_path},
        scope=scope,
        rationale="Legitimate write",
        action_id="123"
    )

    async def mock_approve(*a, **kw):
        return True
    coordinator._request_approval = mock_approve

    result = await coordinator._execute_action(action, cancel_callback=None)
    assert result["status"] == "success"
    assert result["result"] == '"written data"'
    assert "dangerous_write" in track_handlers


@pytest.mark.asyncio
async def test_non_canonical_path_is_canonicalised_and_succeeds(coordinator, tmp_path, track_handlers):
    # Tests that equivalent non-canonical path is canonicalized and succeeds.
    file_path = str(tmp_path / "test.txt")
    non_canonical_path = file_path + "/../test.txt"

    scope = PermissionScope(
        risk="read",
        resource_scope=non_canonical_path,  # Agent might declare the non-canonical path
        operation="file.safe_read",
        approval_requirement=ApprovalRequirement.NEVER,
    )
    action = ProposedAction(
        tool_name="file.safe_read",
        arguments={"path": non_canonical_path},
        scope=scope,
        rationale="Reading via non-canonical path",
        action_id="123"
    )

    orig_check_scope = coordinator._permissions.check_scope
    scope_checked = None
    def mock_check_scope(a: ProposedAction):
        nonlocal scope_checked
        scope_checked = a.scope
        orig_check_scope(a)
    coordinator._permissions.check_scope = mock_check_scope

    result = await coordinator._execute_action(action, cancel_callback=None)
    assert result["status"] == "success"

    # Assert canonicalization took place
    assert scope_checked is not None
    assert scope_checked.resource_scope == file_path
    assert "file.safe_read" in track_handlers


@pytest.mark.asyncio
async def test_legacy_resource_extractor_succeeds(coordinator, tmp_path, track_handlers):
    file_path = str(tmp_path / "legacy.txt")
    scope = PermissionScope(
        risk="read",
        resource_scope=file_path,
        operation="legacy_extractor_tool",
        approval_requirement=ApprovalRequirement.NEVER,
    )
    action = ProposedAction(
        tool_name="legacy_extractor_tool",
        arguments={"path": file_path},
        scope=scope,
        rationale="Legacy extract",
        action_id="123"
    )

    # _execute_action will extract the resource, check scope, and execute it
    result = await coordinator._execute_action(action, cancel_callback=None)
    assert result["status"] == "success"
    assert result["result"] == '"legacy data"'
    assert "legacy_extractor_tool" in track_handlers
