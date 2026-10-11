"""Structural tests for the dedicated OpenCode box.

These tests intentionally avoid importing Modal-dependent modules
(images, devbox, shared_runtime import `modal` at top level and
devbox.py performs Volume/Secret lookups at import time). Instead they
import the dependency-free modules directly and verify the
Modal-dependent files by AST + source inspection.
"""

import ast
import pathlib

from devbox_core import config
from runtime.persistence_utils import OPENCODE_PERSISTENCE_ITEMS, get_persistence_items

ROOT = pathlib.Path(__file__).resolve().parent.parent


def _source(name):
    return (ROOT / name).read_text(encoding="utf-8")


def _tree(name):
    return ast.parse(_source(name))


def _top_level_names(name):
    return {n.name for n in ast.walk(_tree(name)) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))} | {
        t.id for n in ast.walk(_tree(name)) if isinstance(n, ast.Assign) for t in n.targets if isinstance(t, ast.Name)
    }


# --- config.py: resource envelope ---


def test_opencode_port_and_workdir():
    assert config.OPENCODE_PORT == 4096
    assert config.OPENCODE_HOSTNAME == "0.0.0.0"
    assert config.OPENCODE_WORKDIR == "/data"


def test_opencode_resource_envelope_sane():
    args = config.OPENCODE_DEVBOX_ARGS
    assert args["cpu"] >= 0.5
    assert args["memory"] >= 1024
    assert args["timeout"] > 0
    assert args["timeout"] >= config.OPENCODE_IDLE_TIMEOUT_SECONDS


def test_existing_envelopes_untouched():
    assert config.CPU_DEVBOX_ARGS == {"secrets": None, "volumes": None, "cpu": 0.5, "memory": 1024, "timeout": 3600}
    assert config.IDLE_TIMEOUT_SECONDS == 300


# --- persistence_utils.py ---


def test_opencode_persistence_items():
    items = get_persistence_items("opencode")
    assert ".config/opencode" in items
    assert ".local/share/opencode" in items
    # SSH basics still persisted
    assert ".bash_history" in items
    assert items is OPENCODE_PERSISTENCE_ITEMS or items == OPENCODE_PERSISTENCE_ITEMS


def test_unknown_type_still_falls_back_to_ssh():
    assert get_persistence_items("does-not-exist") == get_persistence_items("ssh")


def test_assisted_coding_mapping_preserved():
    # launch_assisted_coding uses devbox_type="assisted_coding" which previously
    # fell through to SSH defaults; it now maps to the gemini envelope.
    assert ".config/gemini" in get_persistence_items("assisted_coding")


# --- images.py (AST + source, no import) ---


def test_opencode_image_defined():
    assert "opencode_image" in _top_level_names("devbox_core/images.py")


def test_opencode_image_installs_opencode_and_ssh():
    src = _source("devbox_core/images.py")
    assert "opencode.ai/install" in src
    assert "get_ssh_setup_commands" in src
    # Dedicated box: must not bundle Gemini CLI (that's the assisted box's job)
    block = src.split("opencode_image")[1].split("llamacpp_cpu_image")[0]
    assert "gemini-cli" not in block


def test_existing_images_still_defined():
    names = _top_level_names("devbox_core/images.py")
    for expected in ("standard_devbox_image", "cuda_devbox_image", "assisted_coding_image", "rdp_devbox_image"):
        assert expected in names


# --- shared_runtime.py (AST + source, no import) ---


def test_run_opencode_shared_defined():
    assert "run_opencode_shared" in _top_level_names("runtime/shared_runtime.py")


def test_run_opencode_shared_serves_and_forwards():
    src = _source("runtime/shared_runtime.py")
    assert "opencode" in src and '"web"' in src or "'web'" in src or "opencode\", \"web\"" in src
    assert "modal.forward(22" in src
    assert "OPENCODE_PORT" in src
    # Nested tunnels: web forward must be inside the ssh forward block
    ssh_idx = src.index("def run_opencode_shared")
    tail = src[ssh_idx:]
    assert tail.index("modal.forward(22") < tail.index("modal.forward(OPENCODE_PORT")


def test_run_devbox_shared_still_defined():
    assert "run_devbox_shared" in _top_level_names("runtime/shared_runtime.py")


# --- devbox.py (AST + source, no import) ---


def test_launch_opencode_defined_and_uses_opencode_image():
    names = _top_level_names("devbox.py")
    assert "launch_opencode" in names
    src = _source("devbox.py")
    assert "opencode_image" in src
    block_start = src.index("def launch_opencode")
    assert "run_opencode_shared" in src[block_start : block_start + 500]


def test_menu_exposes_opencode_option():
    src = _source("devbox.py")
    assert 'choice == "9"' in src
    assert "launch_opencode.remote()" in src


def test_existing_launchers_still_defined():
    names = _top_level_names("devbox.py")
    for expected in ("launch_devbox", "launch_assisted_coding", "launch_rdp_devbox", "launch_llamacpp_playroom"):
        assert expected in names
