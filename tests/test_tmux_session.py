"""Tests for the shared tmux bootstrap.

Both the Function runtimes via `start_tmux_session()` and the HTB VM
entrypoint have to use the same baked helper.
"""

import ast
import pathlib
import types

from runtime import shared_runtime as shared

ROOT = pathlib.Path(__file__).resolve().parent.parent
IMAGES = ROOT / "devbox_core" / "images.py"
SCRIPT = ROOT / "integrations" / "devbox-tmux.sh"
BASE_BUILDERS = ("create_base_devbox_image", "create_base_minimal_image")


def source(path):
    return path.read_text(encoding="utf-8")


def _tree():
    return ast.parse(source(IMAGES))


def _assignments():
    text = source(IMAGES)
    return {
        node.targets[0].id: ast.get_source_segment(text, node) or ""
        for node in _tree().body
        if isinstance(node, ast.Assign)
        and isinstance(node.targets[0], ast.Name)
        and node.targets[0].id.endswith("_image")
    }


def _functions():
    text = source(IMAGES)
    return {
        node.name: ast.get_source_segment(text, node) or ""
        for node in _tree().body
        if isinstance(node, ast.FunctionDef)
    }


def _desktop_layer():
    text = source(IMAGES)
    for node in _tree().body:
        if (
            isinstance(node, ast.Assign)
            and getattr(node.targets[0], "id", None) == "_rdp_desktop_layer"
        ):
            return ast.get_source_segment(text, node) or ""
    raise AssertionError("_rdp_desktop_layer assignment missing")


# --- image wiring -----------------------------------------------------------


def test_both_base_builders_ship_the_helper():
    functions = _functions()
    for builder in BASE_BUILDERS:
        segment = functions[builder]
        assert '"/usr/local/bin/devbox-tmux"' in segment, builder
        index = segment.index('"/usr/local/bin/devbox-tmux"')
        # copy=True: callers chain build steps after add_local_* on these images.
        assert "copy=True" in segment[index:index + 300], builder
        assert "chmod 755 /usr/local/bin/devbox-tmux" in segment, builder


def test_cuda_image_mounts_the_helper_despite_bypassing_the_bases():
    segment = _assignments()["cuda_devbox_image"]
    assert '"/usr/local/bin/devbox-tmux"' in segment
    assert "copy=True" in segment


def test_every_image_reaches_the_helper():
    functions = _functions()
    assert any('"/usr/local/bin/devbox-tmux"' in functions[b] for b in BASE_BUILDERS)
    # The RDP desktop layer derives from a base builder, so it inherits the
    # helper.
    assert any(f"{builder}(" in _desktop_layer() for builder in BASE_BUILDERS)

    for name, segment in _assignments().items():
        direct = '"/usr/local/bin/devbox-tmux"' in segment
        derives = any(
            (f"{builder}(" if builder in BASE_BUILDERS else builder) in segment
            for builder in (*BASE_BUILDERS, "_rdp_desktop_layer")
        )
        assert direct or derives, f"{name} has no path to the tmux helper"


def test_tmux_conf_is_still_mounted_last():
    steps = (
        ".add_local_file(", ".add_local_python_source(", ".add_local_dir(",
        ".run_commands(", ".pip_install(", ".apt_install(",
    )
    for name, segment in _assignments().items():
        mounted = segment.rindex('"tmux.conf"')
        later = [step for step in steps if segment.find(step, mounted) != -1]
        assert not later, f"{name}: {later} after the tmux.conf mount"


# --- the helper itself ------------------------------------------------------


def test_helper_loads_the_baked_config_for_every_caller():
    text = source(SCRIPT)
    assert text.startswith("#!/bin/sh")
    assert "/etc/devbox/tmux.conf" in text
    assert 'set -- -f "$config"' in text
    assert "ln -s" in text
    assert "set-option -g mouse on" in text


def test_helper_selects_by_name_because_base_index_is_one():
    text = source(SCRIPT)
    assert 'select-window -t "$session:window-1"' in text
    # `devbox:0` does not exist once the config sets base-index 1.
    assert ":0" not in text


def test_helper_takes_session_and_window_count():
    text = source(SCRIPT)
    assert "session=${1:-devbox}" in text
    assert "windows=${2:-3}" in text
    assert '[ "$window" -le "$windows" ]' in text


def test_helper_fails_loudly_when_it_cannot_create_a_session():
    text = source(SCRIPT)
    assert "command -v tmux" in text
    assert "has-session" in text
    assert "exit 1" in text


# --- runtime delegation -----------------------------------------------------


def _fake_run(seen, returncode=0, stderr=""):
    def run(command, **kwargs):
        seen.append(command)
        return types.SimpleNamespace(returncode=returncode, stdout="", stderr=stderr)

    return run


def test_runtime_delegates_to_the_baked_helper(monkeypatch, capsys):
    seen = []
    monkeypatch.setattr(shared.subprocess, "run", _fake_run(seen))

    shared.start_tmux_session()

    assert seen == [["/usr/local/bin/devbox-tmux", "devbox", "3"]]
    assert "ready (3 windows)" in capsys.readouterr().err


def test_runtime_passes_session_name_and_window_count(monkeypatch):
    seen = []
    monkeypatch.setattr(shared.subprocess, "run", _fake_run(seen))

    shared.start_tmux_session(session_name="alt", windows=5)

    assert seen == [["/usr/local/bin/devbox-tmux", "alt", "5"]]


def test_failed_helper_is_reported_not_raised(monkeypatch, capsys):
    seen = []
    monkeypatch.setattr(
        shared.subprocess, "run",
        _fake_run(seen, returncode=1, stderr="warning: tmux is not installed"),
    )

    shared.start_tmux_session()

    err = capsys.readouterr().err
    assert "setup failed" in err
    assert "tmux is not installed" in err


def test_missing_helper_is_not_fatal(monkeypatch, capsys):
    def boom(command, **kwargs):
        raise OSError("not found")

    monkeypatch.setattr(shared.subprocess, "run", boom)

    shared.start_tmux_session()

    assert "skipping tmux session" in capsys.readouterr().err


def test_no_path_builds_a_session_without_the_helper():
    runtime = source(ROOT / "runtime" / "shared_runtime.py")
    vm = source(ROOT / "runtime" / "htb_vm.py")

    assert "new-session" not in runtime
    assert "new-session" not in vm
    assert "sh /usr/local/bin/devbox-tmux devbox 3" in vm
