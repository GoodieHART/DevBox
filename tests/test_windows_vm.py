"""Unit tests for windows_vm.py — mocks Sandbox.create, no cloud calls."""

from __future__ import annotations

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
