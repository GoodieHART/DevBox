"""Tests for the OpenCode web activity probe used by the idle watchdog.

The server answers `/` for anyone, so a 200 response kept resetting the timer
and every OpenCode box ran to its hard timeout. Activity is now detected from
established connections to the port, and an inconclusive probe never counts as
idleness.
"""

import ast
import pathlib
import types

from runtime import shared_runtime as shared

ROOT = pathlib.Path(__file__).resolve().parent.parent
SHARED_RUNTIME = ROOT / "runtime" / "shared_runtime.py"


def _fake_run(stdout: str, returncode: int, seen: list):
    def run(command, **kwargs):
        seen.append(command)
        return types.SimpleNamespace(stdout=stdout, returncode=returncode)

    return run


def _patch(monkeypatch, run):
    monkeypatch.setattr(shared, "subprocess", types.SimpleNamespace(run=run))


def test_counts_established_clients(monkeypatch):
    seen: list = []
    _patch(monkeypatch, _fake_run("0 0 127.0.0.1:4096 127.0.0.1:5555\n0 0 127.0.0.1:4096 127.0.0.1:5556\n", 0, seen))

    assert shared.count_web_clients(4096) == 2
    assert seen, "ss was never called"
    assert "sport = :4096" in seen[0]
    assert "established" in seen[0]


def test_no_connections_means_no_activity(monkeypatch):
    _patch(monkeypatch, _fake_run("\n", 0, []))
    assert shared.count_web_clients(4096) == 0


def test_failed_probe_is_unknown_not_idle(monkeypatch):
    # Unknown must not read as 0, or an ss failure would shut the box down.
    _patch(monkeypatch, _fake_run("", 1, []))
    assert shared.count_web_clients(4096) is None


def test_missing_ss_is_unknown_not_idle(monkeypatch):
    def boom(command, **kwargs):
        raise OSError("ss: not found")

    _patch(monkeypatch, boom)
    assert shared.count_web_clients(4096) is None


def _called_names(node: ast.AST) -> list[str]:
    names = []
    for call in ast.walk(node):
        if not isinstance(call, ast.Call):
            continue
        if isinstance(call.func, ast.Name):
            names.append(call.func.id)
        elif isinstance(call.func, ast.Attribute):
            names.append(call.func.attr)
    return names


def test_idle_loop_uses_the_client_counter():
    tree = ast.parse(SHARED_RUNTIME.read_text(encoding="utf-8"))
    function = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "run_opencode_shared"
    )
    assert "count_web_clients" in _called_names(function)
    # The HTTP probe that always succeeded is gone.
    assert "_http_active" not in SHARED_RUNTIME.read_text(encoding="utf-8")
