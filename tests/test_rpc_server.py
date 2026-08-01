"""Unit tests for rpc_server.py — state machine + HTTP endpoints.

No network and no sandbox: the server is a real ThreadingHTTPServer bound to
127.0.0.1:0 (loopback only); QEMU is faked by monkeypatching qemu_running /
hmp_send / take_screenshot.
"""

from __future__ import annotations

import base64
import json
import threading
import urllib.error
import urllib.request

import pytest

import rpc_server


@pytest.fixture(autouse=True)
def _clean_state(monkeypatch):
    """Reset the state machine globals before every test."""
    monkeypatch.setattr(rpc_server, "_marked", False)
    monkeypatch.setattr(rpc_server, "_BOOT_MODE", "boot")


def _open(req: urllib.request.Request) -> tuple[int, bytes]:
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


class _Server:
    def __init__(self):
        self.httpd = rpc_server.build_server("127.0.0.1", 0)
        self.base = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def get(self, path: str) -> tuple[int, bytes]:
        return _open(urllib.request.Request(self.base + path))

    def post(
        self,
        path: str,
        data: bytes | None = None,
        content_type: str = "application/json",
    ) -> tuple[int, bytes]:
        req = urllib.request.Request(
            self.base + path,
            data=data,
            headers={"Content-Type": content_type},
            method="POST",
        )
        return _open(req)

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()


@pytest.fixture
def srv():
    server = _Server()
    try:
        yield server
    finally:
        server.close()


# ---------------------------------------------------------------------------
# State machine (direct function calls, no HTTP)
# ---------------------------------------------------------------------------


def test_status_boot_mode_running_when_qemu_alive(monkeypatch):
    """Given boot mode with the fake QEMU alive, status is 'running'."""
    monkeypatch.setattr(rpc_server, "qemu_running", lambda: True)
    assert rpc_server.compute_status() == "running"


def test_status_boot_mode_stopped_when_qemu_gone(monkeypatch):
    """Given boot mode with QEMU not running, status is 'stopped'."""
    monkeypatch.setattr(rpc_server, "qemu_running", lambda: False)
    assert rpc_server.compute_status() == "stopped"


def test_status_install_mode_installing_regardless_of_qemu(monkeypatch):
    """Given install mode, status is 'installing' from startup (pre-QEMU too)."""
    monkeypatch.setattr(rpc_server, "_BOOT_MODE", "install")
    for qemu_alive in (True, False):
        monkeypatch.setattr(rpc_server, "qemu_running", lambda: qemu_alive)
        assert rpc_server.compute_status() == "installing"


def test_status_installed_only_after_mark(monkeypatch):
    """Given no /mark, status is never 'installed'; after mark it is sticky."""
    monkeypatch.setattr(rpc_server, "qemu_running", lambda: True)
    assert rpc_server.compute_status() != "installed"
    rpc_server.mark_installed("installed")
    assert rpc_server.compute_status() == "installed"
    monkeypatch.setattr(rpc_server, "qemu_running", lambda: False)
    assert rpc_server.compute_status() == "installed"


# ---------------------------------------------------------------------------
# HTTP endpoints
# ---------------------------------------------------------------------------


def test_health_returns_ok(srv):
    """Given GET /health, respond 200 with ok:true."""
    status, body = srv.get("/health")
    assert status == 200
    assert json.loads(body) == {"ok": True}


def test_status_endpoint_reports_running(srv, monkeypatch):
    """Given boot mode + live fake QEMU, GET /status reports 'running'."""
    monkeypatch.setattr(rpc_server, "qemu_running", lambda: True)
    status, body = srv.get("/status")
    assert status == 200
    assert json.loads(body) == {"status": "running"}


def test_mark_sets_installed_via_endpoint_only(srv, monkeypatch, capsys):
    """Given POST /mark (guest-style raw body), status flips to 'installed';
    no other endpoint mutates the state; the receipt is logged."""
    monkeypatch.setattr(rpc_server, "qemu_running", lambda: True)
    srv.post("/shutdown", b"{}")
    srv.post("/reset", b"{}")
    srv.post("/hmp", json.dumps({"command": "info status"}).encode())
    _, body = srv.get("/status")
    assert json.loads(body) == {"status": "running"}

    status, body = srv.post(
        "/mark", b"installed", content_type="application/x-www-form-urlencoded"
    )
    assert status == 200
    assert json.loads(body) == {"status": "installed"}
    _, body = srv.get("/status")
    assert json.loads(body) == {"status": "installed"}

    out = capsys.readouterr().out
    assert "/mark received" in out
    assert "installed" in out


def test_write_file_writes_expected_path(srv, tmp_path):
    """Given POST /write-file, the decoded content lands at the requested path."""
    target = tmp_path / "floppy" / "autounattend.xml"
    content = b"<unattend>xml</unattend>"
    payload = json.dumps(
        {"path": str(target), "content_b64": base64.b64encode(content).decode()}
    ).encode()
    status, body = srv.post("/write-file", payload)
    assert status == 200
    assert json.loads(body) == {"written": len(content), "path": str(target)}
    assert target.read_bytes() == content


def test_exec_runs_sandbox_side_command(srv):
    """Given POST /exec, the command runs inside the sandbox (never the guest)."""
    payload = json.dumps({"command": "echo hello-sandbox"}).encode()
    status, body = srv.post("/exec", payload)
    assert status == 200
    result = json.loads(body)
    assert result["stdout"].strip() == "hello-sandbox"
    assert result["returncode"] == 0


def test_hmp_passthrough_forwards_command(srv, monkeypatch):
    """Given POST /hmp, the raw command is forwarded to HMP verbatim."""
    seen = []

    def fake_hmp(command):
        seen.append(command)
        return "ok"

    monkeypatch.setattr(rpc_server, "hmp_send", fake_hmp)
    payload = json.dumps({"command": "system_powerdown"}).encode()
    status, body = srv.post("/hmp", payload)
    assert status == 200
    assert json.loads(body) == {"result": "ok"}
    assert seen == ["system_powerdown"]


def test_type_sends_keys_per_char(srv, monkeypatch):
    """Given POST /type with enter:true, chars map to HMP keys + a final ret."""
    sent = []
    monkeypatch.setattr(rpc_server, "sendkey", lambda key: sent.append(key) or "")
    payload = json.dumps({"text": "Hi!", "delay": 0, "enter": True}).encode()
    status, body = srv.post("/type", payload)
    assert status == 200
    result = json.loads(body)
    assert result["typed"] == 3
    assert result["total"] == 3
    assert sent == ["shift-h", "i", "shift-1", "ret"]


def test_screenshot_errors_when_qemu_down(srv, monkeypatch):
    """Given QEMU down (screendump unavailable), /screenshot returns 500."""
    monkeypatch.setattr(rpc_server, "take_screenshot", lambda: None)
    status, body = srv.get("/screenshot")
    assert status == 500
    assert json.loads(body)["error"]


def test_unknown_endpoint_returns_404(srv):
    """Given an unknown path, respond 404."""
    status, body = srv.get("/nope")
    assert status == 404
    status, body = srv.post("/nope", b"{}")
    assert status == 404
