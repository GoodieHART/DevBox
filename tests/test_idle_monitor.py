"""Unit tests for todo 12 idle monitor + auto-shutdown (windows_vm.py).

Fake sandbox (canned ``ss`` stdout sequences), fake RPC client (canned
/status transitions, records hmp() powerdowns) and a fake clock
(monkeypatched ``windows_vm.time.monotonic``/``sleep``, mirroring
tests/test_install_orchestration.py). No network, no modal calls, no live
sandbox — the live powerdown gate is deferred pending /dev/kvm.
"""

from __future__ import annotations

import inspect
import json

import pytest

import windows_vm

# Canonical `ss -tn state established '( sport = :3389 )'` output fragments.
SS_HEADER = (
    "State      Recv-Q Send-Q Local Address:Port                 Peer Address:Port"
)
SS_ONE = "ESTAB      0      0      127.0.0.1:3389                          127.0.0.1:51234"
SS_TWO = (
    "ESTAB      0      0      127.0.0.1:3389                          127.0.0.1:51234\n"
    "ESTAB      0      0      127.0.0.1:3389                          127.0.0.1:51235"
)


class _FakeSB:
    """Sandbox double: canned ``ss`` stdout per exec call (str, like sb.exec).

    ``ss_outputs`` pops from the front until one element remains, then that
    last element is returned forever (stuck-state support).
    """

    def __init__(self, ss_outputs=("",)):
        self._ss_outputs = list(ss_outputs)
        self.exec_calls: list[list[str]] = []
        self.terminated = False

    def exec(self, *args):
        self.exec_calls.append(list(args))
        if len(self._ss_outputs) > 1:
            out = self._ss_outputs.pop(0)
        else:
            out = self._ss_outputs[0] if self._ss_outputs else ""
        return _FakeProc(out)

    def terminate(self):
        self.terminated = True


class _FakeProc:
    def __init__(self, stdout: str):
        self.stdout = _FakeStdout(stdout)


class _FakeStdout:
    def __init__(self, value: str):
        self._value = value

    def read(self):
        return self._value


class _FakeRpc:
    """RPC client double: canned /status sequence + powerdown-aware hmp().

    ``statuses`` pops from the front until one element remains, then that
    last element repeats forever; ``errors`` is a list of bools — True makes
    the next get_status raise RpcError (ends the monitor loop). After
    ``hmp("system_powerdown")`` the fake returns "stopped" immediately when
    ``stop_after_powerdown`` is True, else keeps the canned sequence (the
    120s-cap fallback path).
    """

    def __init__(self, statuses=("running",), errors=(), stop_after_powerdown=True):
        self._statuses = list(statuses)
        self._errors = list(errors)
        self.stop_after_powerdown = stop_after_powerdown
        self.powered_down = False
        self.hmp_calls: list[str] = []
        self.status_calls = 0
        self.ready = True

    def wait_ready(self, timeout=120, poll_interval=2):
        return self.ready

    def get_status(self):
        self.status_calls += 1
        if self._errors:
            if self._errors.pop(0):
                raise windows_vm.RpcError("fake RPC unreachable")
        if self.powered_down and self.stop_after_powerdown:
            return "stopped"
        if len(self._statuses) > 1:
            return self._statuses.pop(0)
        if not self._statuses:
            raise windows_vm.RpcError("fake RPC exhausted")
        return self._statuses[0]

    def hmp(self, command):
        self.hmp_calls.append(command)
        if command == "system_powerdown":
            self.powered_down = True
        return {"result": "ok"}


class _FakeClock:
    def __init__(self, start=1000.0):
        self.now = start

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


@pytest.fixture
def fake_clock(monkeypatch):
    """Deterministic clock for the idle-monitor polling loops."""
    clock = _FakeClock()
    monkeypatch.setattr(windows_vm.time, "monotonic", clock.monotonic)
    monkeypatch.setattr(windows_vm.time, "sleep", clock.sleep)
    return clock


def _wire(monkeypatch, sb, rpc):
    """Route idle_monitor's client construction to the fake RPC client."""
    monkeypatch.setattr(windows_vm, "rpc_client_for_sandbox", lambda _sb: rpc)


# ---------------------------------------------------------------------------
# count_rdp_connections parsing
# ---------------------------------------------------------------------------


def test_count_rdp_connections_header_only_is_zero():
    """Given header-only ss output, the connection count is 0."""
    assert windows_vm.count_rdp_connections(SS_HEADER) == 0


def test_count_rdp_connections_counts_established_lines():
    """Given N established lines, the count is N (header skipped)."""
    assert windows_vm.count_rdp_connections(SS_HEADER + "\n" + SS_ONE) == 1
    assert windows_vm.count_rdp_connections(SS_HEADER + "\n" + SS_TWO) == 2


def test_count_rdp_connections_empty_stdout_is_zero():
    """Given empty stdout, the count is 0."""
    assert windows_vm.count_rdp_connections("") == 0


def test_count_rdp_connections_without_header_counts_all_lines():
    """Given output with no header line (defensive), all lines count."""
    assert windows_vm.count_rdp_connections(SS_ONE) == 1


# ---------------------------------------------------------------------------
# idle-monitor decision logic (fake connection counts -> powerdown trigger)
# ---------------------------------------------------------------------------


def test_idle_monitor_zero_connections_powerdowns_exactly_once(fake_clock, monkeypatch):
    """(a) zero connections for idle_timeout -> one system_powerdown, clean return.

    Poll every 60s with a header-only ss probe: zero_since starts at t=1000,
    elapsed reaches idle_timeout (300s) at t=1300 (6th poll) -> powerdown.
    The fake RPC then reports 'stopped', so no terminate() is needed.
    """
    sb = _FakeSB(ss_outputs=(SS_HEADER,))
    rpc = _FakeRpc(statuses=("running",))
    _wire(monkeypatch, sb, rpc)

    windows_vm.idle_monitor(sb, idle_timeout=300)

    assert rpc.hmp_calls == ["system_powerdown"]  # exactly once
    assert sb.terminated is False  # graceful path — no forced termination
    assert len(sb.exec_calls) == 6  # 6 polls x 60s = 300s streak
    cmd = " ".join(sb.exec_calls[0])
    assert "state established" in cmd and "sport = :3389" in cmd


def test_idle_monitor_active_connections_never_powerdown(fake_clock, monkeypatch):
    """(b) >=1 active connection -> no powerdown while sessions are live.

    The ss probe reports one ESTABLISHED connection on every poll (idle timer
    resets); the loop ends only when the fake RPC starts raising (sandbox
    gone), and hmp() was never called.
    """
    sb = _FakeSB(ss_outputs=(SS_HEADER + "\n" + SS_ONE,))
    rpc = _FakeRpc(statuses=("running",), errors=(0, 0, 0, 1))
    _wire(monkeypatch, sb, rpc)

    windows_vm.idle_monitor(sb, idle_timeout=300)

    assert rpc.hmp_calls == []
    assert len(sb.exec_calls) == 3  # three polls before the RPC error
    assert sb.terminated is False


def test_idle_monitor_active_connection_resets_countdown(fake_clock, monkeypatch):
    """(c) an active connection mid-streak resets the idle countdown.

    Two zero polls, then one active poll, then zeros again: the powerdown
    lands ~2 polls later than the uninterrupted-streak case (t=1480 instead
    of t=1300), proving the timer restarted instead of carrying over.
    """
    sb = _FakeSB(
        ss_outputs=(SS_HEADER, SS_HEADER, SS_HEADER + "\n" + SS_ONE, SS_HEADER)
    )
    rpc = _FakeRpc(statuses=("running",))
    _wire(monkeypatch, sb, rpc)

    windows_vm.idle_monitor(sb, idle_timeout=300)

    assert rpc.hmp_calls == ["system_powerdown"]
    # Poll 3 reset the streak -> 4 zero polls (t=1180..1480) after the reset,
    # i.e. 9 ss probes total instead of 6.
    assert len(sb.exec_calls) == 9


def test_idle_monitor_installing_status_skips_powerdown(fake_clock, monkeypatch):
    """(d) installing status -> no powerdown and no ss probing (install mode).

    Install mode runs the fixed-timeout flow; the loop holds without counting
    idle and ends when the RPC goes unreachable. The ss probe must never run
    during an install session.
    """
    sb = _FakeSB(ss_outputs=(SS_HEADER,))
    rpc = _FakeRpc(statuses=("installing",), errors=(0, 0, 1))
    _wire(monkeypatch, sb, rpc)

    windows_vm.idle_monitor(sb, idle_timeout=300)

    assert rpc.hmp_calls == []
    assert sb.exec_calls == []  # install session: no connection counting


def test_idle_monitor_installed_status_is_non_idle(fake_clock, monkeypatch):
    """(e) 'installed' (/mark received) is defensively non-idle — no powerdown."""
    sb = _FakeSB(ss_outputs=(SS_HEADER,))
    rpc = _FakeRpc(statuses=("installed",), errors=(0, 0, 1))
    _wire(monkeypatch, sb, rpc)

    windows_vm.idle_monitor(sb, idle_timeout=300)

    assert rpc.hmp_calls == []
    assert sb.exec_calls == []


def test_idle_monitor_graceful_shutdown_no_terminate(fake_clock, monkeypatch):
    """(f) powerdown -> /status transitions to 'stopped' -> clean return.

    Explicitly exercises the graceful path: the guest reports 'stopped' after
    the ACPI request, the monitor returns, and the sandbox is NOT terminated
    (the entrypoint exits 0 and the sandbox ends on its own).
    """
    sb = _FakeSB(ss_outputs=(SS_HEADER,))
    rpc = _FakeRpc(statuses=("running",), stop_after_powerdown=True)
    _wire(monkeypatch, sb, rpc)

    windows_vm.idle_monitor(sb, idle_timeout=300)

    assert rpc.hmp_calls == ["system_powerdown"]
    assert sb.terminated is False


def test_idle_monitor_terminate_fallback_after_120s_cap(fake_clock, monkeypatch):
    """(g) status STAYS non-stopped past the 120s cap -> sb.terminate() fallback.

    The fake RPC keeps reporting 'running' after the powerdown: the graceful
    window (SHUTDOWN_TIMEOUT_SECONDS=120, 5s polls) expires and the sandbox
    is terminated. Exactly one powerdown was attempted first.
    """
    sb = _FakeSB(ss_outputs=(SS_HEADER,))
    rpc = _FakeRpc(statuses=("running",), stop_after_powerdown=False)
    _wire(monkeypatch, sb, rpc)

    windows_vm.idle_monitor(sb, idle_timeout=300)

    assert rpc.hmp_calls == ["system_powerdown"]  # graceful attempt came first
    assert sb.terminated is True  # ...then the fallback


# ---------------------------------------------------------------------------
# T11 integration shape
# ---------------------------------------------------------------------------


def test_idle_monitor_shape_matches_t11_wiring():
    """T11 calls idle_monitor(sb) via getattr — signature (sb, idle_timeout=1800).

    The default MUST be 1800 (30 min), NOT the SSH boxes' 300 — devbox.py's
    launcher calls idle_monitor(sb) with no timeout argument.
    """
    assert callable(windows_vm.idle_monitor)
    params = inspect.signature(windows_vm.idle_monitor).parameters
    assert list(params) == ["sb", "idle_timeout"]
    assert params["sb"].default is inspect.Parameter.empty
    assert params["idle_timeout"].default == 1800


def test_idle_monitor_hmp_client_method_payload(monkeypatch):
    """WindowsVMClient.hmp posts {"command": ...} to /hmp (rpc_server contract)."""
    requests = []

    def _fake_urlopen(req, timeout=None):
        requests.append((req.get_method(), req.full_url, req.data))
        return _FakeResp(b'{"result": "ok"}')

    monkeypatch.setattr(windows_vm.urllib.request, "urlopen", _fake_urlopen)
    client = windows_vm.WindowsVMClient("https://t.example")
    result = client.hmp("system_powerdown")
    assert result == {"result": "ok"}
    method, url, data = requests[0]
    assert method == "POST"
    assert url == "https://t.example/hmp"
    assert json.loads(data) == {"command": "system_powerdown"}


class _FakeResp:
    def __init__(self, body: bytes):
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return self._body
