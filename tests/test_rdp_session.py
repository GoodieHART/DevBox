"""Structural tests for RDP desktop session startup and idle detection.

Two production bugs motivated these tests, both confirmed on a live container:

1. `~/.xsession` was listed in `rdp_items`, so `setup_persistence()` replaced
   root's session launcher with an empty 0644 file on the volume. Debian's
   `/etc/X11/Xsession` only honours `~/.xsession` when it is *executable*, so
   every login fell through to `x-session-manager` and the desktop died right
   after authentication.

2. The idle watchdog counted sessions with `ps aux | grep -c 'xrdp-sesman.*:'`
   which never matches a real session, so the box shut itself down
   `IDLE_TIMEOUT_SECONDS` after launch even with a desktop connected.

Source is inspected instead of imported, matching tests/test_image_packaging.py
(Mural imports would need Modal credentials).
"""

import ast
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
SHARED_RUNTIME = ROOT / "runtime" / "shared_runtime.py"
IMAGES = ROOT / "devbox_core" / "images.py"

RDP_RUNTIME_FUNCTION = "run_rdp_devbox_shared"
XSESSION_LAUNCHER = "/usr/local/bin/startxfce4-wrapper"


def _tree(path: pathlib.Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"))


def _function(path: pathlib.Path, name: str) -> ast.FunctionDef:
    for node in ast.walk(_tree(path)):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"{name} not found in {path.name}")


def _strings(node: ast.AST) -> list[str]:
    """Every string literal inside `node`, in source order."""
    return [
        sub.value
        for sub in ast.walk(node)
        if isinstance(sub, ast.Constant) and isinstance(sub.value, str)
    ]


def _calls(node: ast.AST) -> list[ast.Call]:
    return [sub for sub in ast.walk(node) if isinstance(sub, ast.Call)]


def _source_of(path: pathlib.Path, node: ast.AST) -> str:
    return ast.get_source_segment(path.read_text(encoding="utf-8"), node) or ""


def _called_names(node: ast.AST) -> list[str]:
    names = []
    for call in _calls(node):
        if isinstance(call.func, ast.Name):
            names.append(call.func.id)
        elif isinstance(call.func, ast.Attribute):
            names.append(call.func.attr)
    return names


def _rdp_image_commands() -> list[str]:
    """Every string passed to `.run_commands(...)` on the RDP image."""
    commands = []
    for node in _tree(IMAGES).body:
        if not (
            isinstance(node, ast.Assign)
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id == "rdp_devbox_image"
        ):
            continue
        for sub in ast.walk(node):
            if (
                isinstance(sub, ast.Call)
                and isinstance(sub.func, ast.Attribute)
                and sub.func.attr == "run_commands"
            ):
                commands += [
                    arg.value
                    for arg in sub.args
                    if isinstance(arg, ast.Constant) and isinstance(arg.value, str)
                ]
    return commands


def test_rdp_items_does_not_persist_the_session_launcher():
    """Persisting ~/.xsession turned it into an empty file that Xsession skips."""
    items = None
    for node in ast.walk(_function(SHARED_RUNTIME, RDP_RUNTIME_FUNCTION)):
        if (
            isinstance(node, ast.Assign)
            and getattr(node.targets[0], "id", None) == "rdp_items"
            and isinstance(node.value, ast.List)
        ):
            items = [
                element.value
                for element in node.value.elts
                if isinstance(element, ast.Constant) and isinstance(element.value, str)
            ]
    assert items is not None, "rdp_items assignment missing"
    assert ".xsession" not in items


def test_runtime_installs_an_executable_xsession_after_persistence():
    """The launcher is written after setup_persistence(), which owns ~ paths."""
    function = _function(SHARED_RUNTIME, RDP_RUNTIME_FUNCTION)
    order = {}
    for call in _calls(function):
        if isinstance(call.func, ast.Name) and call.func.id in {
            "setup_persistence",
            "install_xsession_launcher",
        }:
            order[call.func.id] = call.lineno

    assert "install_xsession_launcher" in order, "launcher is never installed"
    assert order["install_xsession_launcher"] > order["setup_persistence"]

    installer = _function(SHARED_RUNTIME, "install_xsession_launcher")
    assert any("#!/bin/sh" in value for value in _strings(installer))
    assert "0o755" in _source_of(SHARED_RUNTIME, installer)


def test_runtime_does_not_delete_persisted_xfce_state():
    """`rm -rf` after setup_persistence() destroyed the symlinks it created."""
    function = _function(SHARED_RUNTIME, RDP_RUNTIME_FUNCTION)
    assert "-rf" not in _strings(function)


def test_session_count_uses_pgrep_not_a_self_matching_grep():
    """`ps | grep -c` counts its own argv; `pgrep` never reports itself."""
    counter = _function(SHARED_RUNTIME, "count_rdp_sessions")
    source = _source_of(SHARED_RUNTIME, counter)
    assert "pgrep" in source
    assert "xrdp-sesman.*:" not in source
    assert '"-c"' in source

    patterns = [
        node.value.value
        for node in ast.walk(_tree(SHARED_RUNTIME))
        if isinstance(node, ast.Assign)
        and getattr(node.targets[0], "id", None) == "RDP_SESSION_PATTERN"
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
    ]
    assert patterns, "RDP_SESSION_PATTERN missing"
    assert "xrdp-chansrv" in patterns[0]
    assert "xfce4-session" in patterns[0]


def test_idle_loop_uses_the_session_counter():
    function = _function(SHARED_RUNTIME, RDP_RUNTIME_FUNCTION)
    assert "count_rdp_sessions" in _called_names(function)


def test_rdp_image_writes_an_executable_xsession_for_root():
    """/etc/skel never reaches root's pre-existing home, so root needs its own."""
    commands = _rdp_image_commands()
    assert any("> /root/.xsession" in command for command in commands), commands
    assert "chmod +x /root/.xsession" in commands
    assert any(XSESSION_LAUNCHER in command for command in commands)
