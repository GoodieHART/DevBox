"""Tests for the shared DevBox login banner and the tmux name label.

Every box type renders its banner through one implementation,
`devbox_core.box_identity.banner_text`, wrapped by
`runtime.shared_runtime.format_banner`. The RDP desktop box and the llama.cpp
research center gained banners; the tmux status bar shows the box name when
the box has one and falls back to `devbox`.

These tests are offline: they import the modules and inspect the
Modal-coupled files as source.
"""

import ast
import pathlib

from devbox_core.box_identity import banner_text
from runtime import shared_runtime as shared

ROOT = pathlib.Path(__file__).resolve().parent.parent


def source(name):
    return (ROOT / name).read_text(encoding="utf-8")


def _functions(name):
    tree = ast.parse(source(name))
    return {
        node.name: node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def _calls(node, name):
    return [
        call
        for call in ast.walk(node)
        if isinstance(call, ast.Call)
        and isinstance(call.func, ast.Name)
        and call.func.id == name
    ]


# --- the shared renderer ---------------------------------------------------


def test_banner_names_the_box_and_carries_the_quote(monkeypatch):
    monkeypatch.setattr(
        shared,
        "get_random_quote",
        lambda: {"text": "Code wins.", "author": "Someone"},
    )

    banner = shared.format_banner("standard_devbox")

    assert "Standard DevBox" in banner
    assert "Persistent: /data" in banner
    assert "Code wins." in banner
    assert "- Someone" in banner


def test_banner_accepts_extra_rows(monkeypatch):
    monkeypatch.setattr(
        shared, "get_random_quote", lambda: {"text": "x", "author": "y"}
    )

    banner = shared.format_banner(
        "forensic_analysis", ("OpenCode web on :4096", "RDP desktop on :3389")
    )
    rows = banner.splitlines()

    assert "Forensics Analysis Box" in banner
    assert any("OpenCode web on :4096" in row for row in rows)
    assert rows[0].startswith("╔")
    assert any(row.startswith("╚") for row in rows)


def test_banner_still_renders_without_a_quote(monkeypatch):
    def unavailable():
        raise OSError("no catalogue")

    monkeypatch.setattr(shared, "get_random_quote", unavailable)

    banner = shared.format_banner("standard_devbox")

    assert "Standard DevBox" in banner
    assert banner.rstrip().endswith("╝")


def test_banner_with_name_has_a_name_row():
    rendered = shared.format_banner(
        "standard_devbox", name="devbox-htb-std-7f3a", quote=False
    )
    assert "🏷️" in rendered
    assert "devbox-htb-std-7f3a" in rendered


def test_banner_without_name_has_no_name_row():
    rendered = shared.format_banner("rdp_devbox", quote=False)
    assert "🏷️" not in rendered


def test_banner_border_matches_the_rows():
    rendered = banner_text(
        "devbox-std-7f3a", "🛠️", "Standard DevBox", ["💾 Persistent: /data"]
    )
    lines = [line for line in rendered.splitlines() if line]
    assert lines[0].startswith("╔") and lines[0].endswith("╗")
    assert lines[-1].startswith("╚") and lines[-1].endswith("╝")
    widths = {len(line) for line in lines}
    assert len(widths) == 1, widths


# --- the writer ------------------------------------------------------------


def test_write_banner_file_writes_the_rendered_banner(tmp_path, monkeypatch):
    monkeypatch.setattr(
        shared, "get_random_quote", lambda: {"text": "x", "author": "y"}
    )
    target = tmp_path / "banner"
    written = shared.write_banner_file(
        "standard_devbox", name="devbox-std-7f3a", path=str(target)
    )
    assert written == str(target)
    content = target.read_text(encoding="utf-8")
    assert "Standard DevBox" in content
    assert "devbox-std-7f3a" in content


def test_write_banner_file_is_never_fatal(tmp_path):
    # A path inside a missing directory cannot be written; the helper reports
    # it and returns None instead of raising.
    missing = tmp_path / "nope" / "banner"
    assert shared.write_banner_file("standard_devbox", path=str(missing)) is None


# --- the two boxes that previously had no banner ---------------------------


def test_rdp_box_writes_a_banner():
    node = _functions("runtime/shared_runtime.py")["run_rdp_devbox_shared"]
    assert _calls(node, "write_banner_file"), "RDP box must write a banner"


def test_llamacpp_box_writes_a_banner():
    node = _functions("runtime/llamacpp_runtime.py")["run_llamacpp_playroom"]
    assert _calls(node, "write_banner_file"), "llama.cpp box must write a banner"


def test_rdp_and_llamacpp_banners_do_not_fabricate_a_name():
    # Both run as Modal Functions, which cannot change their kernel hostname,
    # so their banners carry no name: the RDP box passes `current_box_name()`
    # (None without an identity file) and llama.cpp omits it.
    rdp = _calls(_functions("runtime/shared_runtime.py")["run_rdp_devbox_shared"],
                 "write_banner_file")[0]
    llama = _calls(_functions("runtime/llamacpp_runtime.py")["run_llamacpp_playroom"],
                   "write_banner_file")[0]
    for call in (rdp, llama):
        for kw in call.keywords:
            if kw.arg == "name":
                assert isinstance(kw.value, ast.Call)
                assert kw.value.func.id == "current_box_name"


# --- the boxes that already had a banner -----------------------------------


def test_existing_boxes_use_the_shared_writer():
    functions = _functions("runtime/shared_runtime.py")
    for function_name in ("run_devbox_shared", "run_opencode_shared"):
        assert _calls(functions[function_name], "write_banner_file"), function_name


def test_no_inline_dedent_banner_remains():
    src = source("runtime/shared_runtime.py")
    assert "textwrap.dedent" not in src
    assert "╔══════════════════════════════════════╗" not in src


def test_existing_boxes_keep_their_random_quote():
    # `write_banner_file`/`format_banner` default to quote=True, so the SSH and
    # OpenCode boxes still get a quote without passing anything.
    signature = ast.parse(source("runtime/shared_runtime.py"))
    defaults = {}
    for node in ast.walk(signature):
        if isinstance(node, ast.FunctionDef) and node.name == "format_banner":
            args = [a.arg for a in node.args.args]
            default_values = node.args.defaults
            for arg, value in zip(args[-len(default_values):], default_values):
                if isinstance(value, ast.Constant):
                    defaults[arg] = value.value
    assert defaults.get("quote") is True


# --- the tmux status bar ---------------------------------------------------


def _status_left_line():
    return next(
        line
        for line in source("integrations/tmux.conf").splitlines()
        if line.strip().startswith("set -g status-left ")
    )


def test_tmux_status_left_reads_the_box_name_file():
    line = _status_left_line()
    assert "/etc/devbox/name" in line
    assert "cat /etc/devbox/name" in line


def test_tmux_status_left_falls_back_to_devbox():
    assert "|| echo devbox" in _status_left_line()


def test_tmux_status_left_no_longer_uses_the_session_name():
    # `#S` is the session name, always `devbox`, identical in every box.
    assert "#S" not in _status_left_line()
