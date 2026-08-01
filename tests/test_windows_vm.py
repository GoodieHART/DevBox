"""Unit tests for windows_vm.py — mocks Sandbox.create, no cloud calls."""

from __future__ import annotations

import base64
from pathlib import Path

import pytest

import windows_vm


class _AppRef:
    """Stand-in for the Modal app reference passed to create_windows_sandbox."""


def test_create_windows_sandbox_kwargs_exact(monkeypatch):
    """Given valid boot mode, Sandbox.create is called with EXACT config-driven kwargs."""
    created = {}
    fake_sandbox = object()

    def fake_create(**kwargs):
        created["kwargs"] = kwargs
        return fake_sandbox

    monkeypatch.setattr(windows_vm.modal.Sandbox, "create", staticmethod(fake_create))
    monkeypatch.setattr(windows_vm, "windows_vm_image", lambda: "fake-image")

    app_ref = _AppRef()
    result = windows_vm.create_windows_sandbox(app_ref, boot_mode="boot")

    assert result is fake_sandbox
    assert created["kwargs"] == {
        "app": app_ref,
        "image": "fake-image",
        "cpu": 4,
        "memory": 8192,
        "timeout": 7200,
        "region": None,
        "experimental_options": {"vm_runtime": True},
        "unencrypted_ports": [3389],
        "encrypted_ports": [6080, 8765],
        "volumes": {"/vol": windows_vm.WINDOWS_VOLUME},
    }


def test_create_windows_sandbox_rejects_unknown_boot_mode(monkeypatch):
    """Given an invalid boot_mode, create raises ValueError and never calls Sandbox.create."""
    called = False

    def fake_create(**kwargs):
        nonlocal called
        called = True
        return object()

    monkeypatch.setattr(windows_vm.modal.Sandbox, "create", staticmethod(fake_create))
    monkeypatch.setattr(windows_vm, "windows_vm_image", lambda: "fake-image")

    with pytest.raises(ValueError):
        windows_vm.create_windows_sandbox(_AppRef(), boot_mode="warp")

    assert called is False


def test_create_windows_sandbox_passes_region(monkeypatch):
    """Given a region, Sandbox.create receives it unchanged (None default otherwise)."""
    created = {}

    def fake_create(**kwargs):
        created["kwargs"] = kwargs
        return object()

    monkeypatch.setattr(windows_vm.modal.Sandbox, "create", staticmethod(fake_create))
    monkeypatch.setattr(windows_vm, "windows_vm_image", lambda: "fake-image")

    windows_vm.create_windows_sandbox(_AppRef(), boot_mode="install", region="aws-eu-west-1")
    assert created["kwargs"]["region"] == "aws-eu-west-1"

    created.clear()
    windows_vm.create_windows_sandbox(_AppRef())
    assert created["kwargs"]["region"] is None


def test_probe_kvm_returns_stdout_stripped():
    """Given a sandbox whose exec prints KVM_OK, probe_kvm returns 'KVM_OK'."""
    class _FakeProcess:
        stdout = type("_FakeStream", (), {"read": staticmethod(lambda: "KVM_OK\n")})()

    class _FakeSandbox:
        def __init__(self):
            self.exec_calls = []

        def exec(self, *args, **kwargs):
            self.exec_calls.append((args, kwargs))
            return _FakeProcess()

    sb = _FakeSandbox()

    assert windows_vm.probe_kvm(sb) == "KVM_OK"
    assert sb.exec_calls == [
        (("bash", "-c", "[ -e /dev/kvm ] && echo KVM_OK || echo KVM_MISSING"), {})
    ]


def test_probe_kvm_reports_missing():
    """Given a sandbox without /dev/kvm, probe_kvm returns 'KVM_MISSING'."""
    class _FakeProcess:
        stdout = type("_FakeStream", (), {"read": staticmethod(lambda: "KVM_MISSING\n")})()

    class _FakeSandbox:
        def exec(self, *args, **kwargs):
            return _FakeProcess()

    assert windows_vm.probe_kvm(_FakeSandbox()) == "KVM_MISSING"


# ---------------------------------------------------------------------------
# Runtime file upload + entrypoint start (todo 5 helpers)
# ---------------------------------------------------------------------------


def test_upload_runtime_files_writes_both_files_via_base64():
    """Given a sandbox, entrypoint.sh + rpc_server.py are uploaded base64-encoded."""
    calls = []

    class _FakeProcess:
        def wait(self):
            return None

    class _FakeSandbox:
        def exec(self, *args, **kwargs):
            calls.append((args, kwargs))
            return _FakeProcess()

    windows_vm.upload_runtime_files(_FakeSandbox())

    assert len(calls) == 3
    root = Path(windows_vm.__file__).resolve().parent
    entry_b64 = base64.b64encode((root / "entrypoint.sh").read_bytes()).decode()
    rpc_b64 = base64.b64encode((root / "rpc_server.py").read_bytes()).decode()

    writes = [c for c in calls if "base64 -d" in c[0][2]]
    assert len(writes) == 2
    commands = [c[0][2] for c in writes]
    assert any(entry_b64 in cmd and "/sandbox/entrypoint.sh" in cmd for cmd in commands)
    assert any(rpc_b64 in cmd and "/sandbox/rpc_server.py" in cmd for cmd in commands)

    chmod = [c for c in calls if "chmod +x" in c[0][2]]
    assert len(chmod) == 1


def test_start_entrypoint_passes_boot_mode_env():
    """Given boot_mode, the entrypoint exec carries the BOOT_MODE env var."""
    captured = {}
    handle = object()

    class _FakeSandbox:
        def exec(self, *args, **kwargs):
            captured["args"] = args
            captured["kwargs"] = kwargs
            return handle

    result = windows_vm.start_entrypoint(_FakeSandbox(), boot_mode="install")

    assert result is handle
    assert captured["args"] == ("bash", "/sandbox/entrypoint.sh")
    assert captured["kwargs"] == {"env": {"BOOT_MODE": "install"}}


def test_start_entrypoint_defaults_to_boot_mode():
    """Given no boot_mode, the entrypoint runs with BOOT_MODE=boot."""
    captured = {}

    class _FakeSandbox:
        def exec(self, *args, **kwargs):
            captured["kwargs"] = kwargs
            return object()

    windows_vm.start_entrypoint(_FakeSandbox())
    assert captured["kwargs"] == {"env": {"BOOT_MODE": "boot"}}


def test_start_entrypoint_rejects_unknown_mode():
    """Given an invalid boot_mode, start_entrypoint raises ValueError."""
    with pytest.raises(ValueError):
        windows_vm.start_entrypoint(object(), boot_mode="warp")
