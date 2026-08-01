"""Unit tests for todo 8 install orchestration (windows_vm.py additions).

Fake VM objects with canned /status transitions and screenshots — no network,
no modal calls, no sandbox (KVM gate is deferred; these tests are the
KVM-independent acceptance). Style mirrors tests/test_rpc_server.py and
tests/test_windows_vm.py.
"""

from __future__ import annotations

import json
import subprocess
import sys
import urllib.error

import pytest

import windows_vm
from install_files.autounattend import PRODUCT_KEY, build_autounattend

# A wiminfo sample with a multi-edition WIM: IoT LTSC 2024 at index 2.
WIMINFO_SAMPLE = """\
WIM Information:
-----------------
Path:           /vol/isos/windows.iso
Image Count:    2

Imaging Index:  1
Name:           Windows 11 Home
Description:    Windows 11 Home

Imaging Index:  2
Name:           Windows 11 IoT Enterprise LTSC 2024
Description:    Windows 11 IoT Enterprise LTSC 2024
Languages:      en-US
"""


class _FakeVM:
    """VM client double with canned status/frame sequences + call recording.

    Sequences: each call pops from the front until one element remains, then
    that last element is returned forever (stuck-state support). ``errors``
    is a list of bools — True makes the next get_status raise RpcError.
    """

    def __init__(self, statuses=("installing",), frames=(), errors=()):
        self._statuses = list(statuses)
        self._frames = list(frames)
        self._errors = list(errors)
        self.calls: list[tuple] = []
        self.typed: list[tuple] = []  # (text, enter, delay) from type_text

    def get_status(self):
        self.calls.append(("get_status",))
        if self._errors:
            if self._errors.pop(0):
                raise windows_vm.RpcError("fake RPC unreachable")
        if len(self._statuses) > 1:
            return self._statuses.pop(0)
        if not self._statuses:
            return "running"
        return self._statuses[0]

    def screenshot(self):
        self.calls.append(("screenshot",))
        if len(self._frames) > 1:
            return self._frames.pop(0)
        if not self._frames:
            return None
        return self._frames[0]

    def write_file(self, path, content):
        self.calls.append(("write_file", path, content))
        return {"written": len(content), "path": path}

    def sendkey(self, key):
        self.calls.append(("sendkey", key))
        return {"result": "ok", "key": key}

    def type_text(self, text, *, enter=False, delay=0.12):
        self.typed.append((text, enter, delay))
        return {"typed": 1, "skipped": [], "total": len(text)}

    def wait_ready(self, timeout=120):
        self.calls.append(("wait_ready",))
        return True


class _FakeClock:
    def __init__(self, start=1000.0):
        self.now = start

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


@pytest.fixture
def fake_clock(monkeypatch):
    """Deterministic clock for wait_for_setup/install_windows polling."""
    clock = _FakeClock()
    monkeypatch.setattr(windows_vm.time, "monotonic", clock.monotonic)
    monkeypatch.setattr(windows_vm.time, "sleep", clock.sleep)
    return clock


# ---------------------------------------------------------------------------
# wiminfo index resolution
# ---------------------------------------------------------------------------


def test_parse_wiminfo_index_finds_iot_ltsc():
    """Given multi-edition wiminfo output, the IoT LTSC 2024 index is returned."""
    assert windows_vm.parse_wiminfo_index(WIMINFO_SAMPLE) == 2


def test_parse_wiminfo_index_single_edition():
    """Given single-edition output (index 1), the IoT LTSC index is 1."""
    single = "Imaging Index:  1\nName:   Windows 11 IoT Enterprise LTSC 2024\n"
    assert windows_vm.parse_wiminfo_index(single) == 1


def test_parse_wiminfo_index_raises_when_edition_missing():
    """Given output without the IoT LTSC edition, parse raises ValueError."""
    with pytest.raises(ValueError):
        windows_vm.parse_wiminfo_index("Imaging Index: 1\nName: Windows 11 Pro\n")


def test_resolve_image_index_uses_runner():
    """Given a runner callable, its stdout is parsed and returned."""
    captured = []

    def runner():
        captured.append(True)
        return WIMINFO_SAMPLE

    assert windows_vm.resolve_image_index(runner=runner) == 2
    assert captured == [True]


def test_resolve_image_index_default_runner_is_regular_container(monkeypatch):
    """Given no runner, the default path goes through probe_wiminfo.probe (no KVM)."""
    captured = []

    def fake_probe():
        captured.append(True)
        return WIMINFO_SAMPLE

    monkeypatch.setattr(windows_vm.probe_wiminfo, "probe", fake_probe)
    assert windows_vm.resolve_image_index() == 2
    assert captured == [True]


def test_probe_wiminfo_module_is_self_contained():
    """The probe module imports ONLY stdlib + modal — no repo modules at module level.

    Regression test for the container crash: the probe image mounts only
    probe_wiminfo (named add_local_python_source), so importing repo modules
    (config/images/install_files) here would ModuleNotFoundError in the
    worker container at import time.
    """
    code = (
        "import probe_wiminfo, sys; "
        "assert 'config' not in sys.modules, 'config leaked'; "
        "assert 'images' not in sys.modules, 'images leaked'; "
        "assert 'install_files' not in sys.modules, 'install_files leaked'; "
        "print('CLEAN')"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stderr
    assert "CLEAN" in result.stdout


# ---------------------------------------------------------------------------
# autounattend delivery + UEFI navigation
# ---------------------------------------------------------------------------


def test_deliver_autounattend_payload():
    """Given an index, autounattend.xml for THAT index lands at the staging path."""
    vm = _FakeVM()
    result = windows_vm.deliver_autounattend(vm, 2)
    writes = [c for c in vm.calls if c[0] == "write_file"]
    assert len(writes) == 1
    _, path, content = writes[0]
    assert path == windows_vm.FLOPPY_STAGING_PATH
    assert content == build_autounattend(2).encode("utf-8")
    assert b"<Value>2</Value>" in content
    assert result == {"written": len(content), "path": path}


def test_deliver_autounattend_uses_given_index_not_hardcoded():
    """Given index 1, the payload is built with index 1 (never a hardcoded 2)."""
    vm = _FakeVM()
    windows_vm.deliver_autounattend(vm, 1)
    _, _, content = [c for c in vm.calls if c[0] == "write_file"][0]
    assert content == build_autounattend(1).encode("utf-8")


def test_navigate_uefi_boot_sendkey_sequence():
    """Given a VM client, the UEFI nav keys are sent in exact order."""
    vm = _FakeVM()
    sent = windows_vm.navigate_uefi_boot(vm)
    assert sent == ["esc", "down", "down", "ret", "ret"]
    keys = [c[1] for c in vm.calls if c[0] == "sendkey"]
    assert keys == ["esc", "down", "down", "ret", "ret"]


# ---------------------------------------------------------------------------
# setup polling (fake status sequences)
# ---------------------------------------------------------------------------


def test_wait_for_setup_progression_running_installing(fake_clock):
    """(a) running -> installing with progressing frames confirms setup."""
    vm = _FakeVM(
        statuses=("running", "installing"),
        frames=(b"a" * 12000, b"b" * 12000),
    )
    result = windows_vm.wait_for_setup(vm, timeout=600, poll_interval=10)
    assert result.status == "installing"
    assert result.saw_installing is True
    assert result.gvlk_injected is False
    assert len(result.frames) == 2
    assert result.elapsed == 10  # two polls, one 10s sleep


def test_wait_for_setup_installed_marker_returns_immediately(fake_clock):
    """Given status 'installed' (guest /mark), setup is confirmed at once."""
    vm = _FakeVM(statuses=("installed",), frames=())
    result = windows_vm.wait_for_setup(vm, timeout=600, poll_interval=10)
    assert result.status == "installed"
    assert result.saw_installing is True
    assert result.elapsed == 0


def test_wait_for_setup_stuck_in_installing_times_out(fake_clock):
    """(b) stuck at 'installing' with no valid frames -> SetupTimeoutError."""
    vm = _FakeVM(statuses=("installing",), frames=())
    with pytest.raises(windows_vm.SetupTimeoutError) as excinfo:
        windows_vm.wait_for_setup(vm, timeout=600, poll_interval=10)
    assert excinfo.value.saw_installing is True
    assert excinfo.value.gvlk_injected is False
    assert excinfo.value.elapsed == 600
    assert excinfo.value.frames == []


def test_wait_for_setup_never_installing_times_out(fake_clock):
    """Given status never reaching 'installing', the cap raises."""
    vm = _FakeVM(statuses=("running",), frames=(b"a" * 12000,))
    with pytest.raises(windows_vm.SetupTimeoutError) as excinfo:
        windows_vm.wait_for_setup(vm, timeout=300, poll_interval=10)
    assert excinfo.value.saw_installing is False
    assert len(excinfo.value.frames) > 0  # frames saved as evidence


def test_wait_for_setup_freeze_injects_gvlk_once(fake_clock):
    """(c) static setup screen >3 min -> GVLK typed once via /type+ret (idempotent)."""
    frame = b"\x89PNG" + b"\x00" * windows_vm.MIN_FRAME_BYTES
    vm = _FakeVM(statuses=("installing",), frames=(frame,))
    with pytest.raises(windows_vm.SetupTimeoutError) as excinfo:
        windows_vm.wait_for_setup(vm, timeout=3600, poll_interval=10)
    assert excinfo.value.gvlk_injected is True
    assert vm.typed == [(PRODUCT_KEY, True, 0.12)]
    # No double injection on continued freezes.
    assert len(vm.typed) == 1


def test_wait_for_setup_survives_transient_rpc_errors(fake_clock):
    """Given transient RpcError blips, polling continues and setup confirms."""
    vm = _FakeVM(
        statuses=("installing",),
        frames=(b"a" * 12000, b"b" * 12000),
        errors=(1, 0),
    )
    result = windows_vm.wait_for_setup(vm, timeout=600, poll_interval=10)
    assert result.status == "installing"
    assert result.saw_installing is True


def test_detect_key_prompt_heuristic():
    """Given identical non-blank frames, the prompt heuristic fires; blank/changed do not."""
    frame = b"x" * 20000
    assert windows_vm.detect_key_prompt(frame, frame) is True
    assert windows_vm.detect_key_prompt(frame, b"y" * 20000) is False
    assert windows_vm.detect_key_prompt(None, frame) is False
    assert windows_vm.detect_key_prompt(frame, None) is False
    assert windows_vm.detect_key_prompt(b"small", b"small") is False


# ---------------------------------------------------------------------------
# install_windows orchestration
# ---------------------------------------------------------------------------


def test_install_windows_orchestration_order(fake_clock):
    """Given an index, install_windows: wait_ready -> deliver -> nav -> poll."""
    vm = _FakeVM(statuses=("installing",), frames=(b"a" * 12000, b"b" * 12000))
    result = windows_vm.install_windows(vm, index=2, timeout=600, poll_interval=10)
    assert result.saw_installing is True

    kinds = [c[0] for c in vm.calls]
    assert kinds.index("wait_ready") < kinds.index("write_file")
    assert kinds.index("write_file") < kinds.index("sendkey")
    assert kinds.index("sendkey") < kinds.index("get_status")
    keys = [c[1] for c in vm.calls if c[0] == "sendkey"]
    assert keys == ["esc", "down", "down", "ret", "ret"]


def test_install_windows_resolves_index_when_not_given(fake_clock, monkeypatch):
    """Given no index, install_windows resolves it via the wiminfo runner."""
    monkeypatch.setattr(
        windows_vm.probe_wiminfo, "probe", lambda: WIMINFO_SAMPLE
    )
    vm = _FakeVM(statuses=("installing",), frames=(b"a" * 12000, b"b" * 12000))
    result = windows_vm.install_windows(vm, timeout=600, poll_interval=10)
    assert result.saw_installing is True
    _, _, content = [c for c in vm.calls if c[0] == "write_file"][0]
    assert content == build_autounattend(2).encode("utf-8")


# ---------------------------------------------------------------------------
# WindowsVMClient payload contract (no network — urlopen monkeypatched)
# ---------------------------------------------------------------------------


class _FakeResponse:
    def __init__(self, body: bytes):
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return self._body


def _fake_urlopen(requests, body=b'{"status": "installing"}'):
    def _open(req, timeout=None):
        requests.append(
            (req.get_method(), req.full_url, req.data, dict(req.header_items()), timeout)
        )
        return _FakeResponse(body)

    return _open


def test_client_get_status_parses_json(monkeypatch):
    """Given GET /status, the client parses the state string."""
    requests = []
    monkeypatch.setattr(windows_vm.urllib.request, "urlopen", _fake_urlopen(requests))
    client = windows_vm.WindowsVMClient("https://tunnel.example/")
    assert client.get_status() == "installing"
    method, url, data, _, _ = requests[0]
    assert method == "GET"
    assert url == "https://tunnel.example/status"
    assert data is None


def test_client_write_file_payload_contract(monkeypatch):
    """Given /write-file, the payload carries path + base64 content (rpc_server contract)."""
    requests = []
    monkeypatch.setattr(windows_vm.urllib.request, "urlopen", _fake_urlopen(requests))
    client = windows_vm.WindowsVMClient("https://tunnel.example")
    content = b"<unattend/>"
    client.write_file("/tmp/floppy_contents/autounattend.xml", content)
    method, url, data, headers, _ = requests[0]
    assert method == "POST"
    assert url == "https://tunnel.example/write-file"
    assert headers.get("Content-type") == "application/json"
    assert json.loads(data) == {
        "path": "/tmp/floppy_contents/autounattend.xml",
        "content_b64": "PHVuYXR0ZW5kLz4=",
    }


def test_client_type_text_enter_payload(monkeypatch):
    """Given /type with enter, the payload carries text/delay/enter."""
    requests = []
    monkeypatch.setattr(windows_vm.urllib.request, "urlopen", _fake_urlopen(requests))
    windows_vm.WindowsVMClient("https://t.example").type_text("KEY-123", enter=True)
    _, url, data, _, _ = requests[0]
    assert url == "https://t.example/type"
    assert json.loads(data) == {"text": "KEY-123", "delay": 0.12, "enter": True}


def test_client_screenshot_none_when_qemu_down(monkeypatch):
    """Given /screenshot returning 500, the client yields None (not an exception)."""

    def _boom(req, timeout=None):
        raise urllib.error.HTTPError(req.full_url, 500, "no screenshot", {}, None)

    monkeypatch.setattr(windows_vm.urllib.request, "urlopen", _boom)
    client = windows_vm.WindowsVMClient("https://t.example")
    assert client.screenshot() is None


def test_client_raises_rpc_error_on_transport_failure(monkeypatch):
    """Given an unreachable server, client methods raise RpcError."""

    def _boom(req, timeout=None):
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr(windows_vm.urllib.request, "urlopen", _boom)
    client = windows_vm.WindowsVMClient("https://t.example")
    with pytest.raises(windows_vm.RpcError):
        client.get_status()


def test_client_wait_ready_times_out(fake_clock, monkeypatch):
    """Given the server never answers /health, wait_ready raises RpcError."""

    def _boom(req, timeout=None):
        raise urllib.error.URLError("refused")

    monkeypatch.setattr(windows_vm.urllib.request, "urlopen", _boom)
    client = windows_vm.WindowsVMClient("https://t.example")
    with pytest.raises(windows_vm.RpcError):
        client.wait_ready(timeout=30, poll_interval=10)
