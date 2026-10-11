"""Unit tests for multi-key SSH injection (runtime.utils.inject_ssh_key).

inject_ssh_key targets /root/.ssh, so tests pass an explicit tmp dir;
pwd/os.getuid are stubbed for non-POSIX platforms.
"""
import os
import sys
import types

import pytest

from runtime.utils import inject_ssh_key

KEY_A = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIA1 dev-a"
KEY_B = "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQ2 dev-b"
KEY_C = "ecdsa-sha2-nistp256 AAAAE2VjZHNhLXNoYTItbmlzdHAyNTYAAAAIbmlzdHAyNTYAAABBB3 dev-c"


@pytest.fixture(autouse=True)
def _posix_stubs(monkeypatch):
    pwd_stub = types.ModuleType("pwd")
    pwd_stub.getpwuid = lambda uid: types.SimpleNamespace(pw_name="root")
    monkeypatch.setitem(sys.modules, "pwd", pwd_stub)
    monkeypatch.setattr(os, "getuid", lambda: 0, raising=False)
    for var in ("PUBKEYS", "PUBKEY"):
        monkeypatch.delenv(var, raising=False)


def test_multi_key_install_skips_blanks_dupes_and_junk(tmp_path, monkeypatch):
    monkeypatch.setenv("PUBKEYS", f"{KEY_A}\n\n{KEY_B}\nnot-a-key\n{KEY_A}\n")
    assert inject_ssh_key(ssh_dir=str(tmp_path)) is True
    content = (tmp_path / "authorized_keys").read_text()
    assert KEY_A in content and KEY_B in content
    assert "not-a-key" not in content
    assert content.count(KEY_A) == 1


def test_idempotent_reinstall(tmp_path, monkeypatch):
    monkeypatch.setenv("PUBKEYS", KEY_A)
    assert inject_ssh_key(ssh_dir=str(tmp_path)) is True
    assert inject_ssh_key(ssh_dir=str(tmp_path)) is True
    assert (tmp_path / "authorized_keys").read_text().count(KEY_A) == 1


def test_legacy_single_pubkey_still_works(tmp_path, monkeypatch):
    monkeypatch.setenv("PUBKEY", KEY_C)
    assert inject_ssh_key(ssh_dir=str(tmp_path)) is True
    assert KEY_C in (tmp_path / "authorized_keys").read_text()


def test_pubkeys_preferred_over_pubkey(tmp_path, monkeypatch):
    monkeypatch.setenv("PUBKEYS", KEY_A)
    monkeypatch.setenv("PUBKEY", KEY_B)
    assert inject_ssh_key(ssh_dir=str(tmp_path)) is True
    content = (tmp_path / "authorized_keys").read_text()
    assert KEY_A in content and KEY_B not in content


def test_empty_returns_false(tmp_path):
    assert inject_ssh_key(ssh_dir=str(tmp_path)) is False


def test_only_junk_returns_false(tmp_path, monkeypatch):
    monkeypatch.setenv("PUBKEYS", "hello\nworld\n")
    assert inject_ssh_key(ssh_dir=str(tmp_path)) is False
    assert not (tmp_path / "authorized_keys").exists()
