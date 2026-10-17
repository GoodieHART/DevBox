"""Structural tests for the dedicated OpenCode box.

These tests intentionally avoid importing Modal-dependent modules
(images, devbox, shared_runtime import `modal` at top level and
devbox.py performs Volume/Secret lookups at import time). Instead they
import the dependency-free modules directly and verify the
Modal-dependent files by AST + source inspection.
"""

import ast
import json
import pathlib

from devbox_core import config
from runtime.persistence_utils import (
    OPENCODE_PERSISTENCE_ITEMS,
    get_persistence_items,
    setup_persistence,
)

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


def test_opencode_box_roots_in_persistent_git_seeded_sessions_dir():
    assert config.OPENCODE_SESSIONS_DIR == "/data/oc-sessions"
    src = _source("runtime/shared_runtime.py")
    assert "OPENCODE_SESSIONS_DIR" in src
    assert 'cwd=OPENCODE_SESSIONS_DIR' in src
    assert '"git", "init"' in src
    assert '"--allow-empty"' in src


def test_opencode_resource_envelope_sane():
    args = config.OPENCODE_DEVBOX_ARGS
    assert args["cpu"] >= 0.5
    assert args["memory"] >= 1024
    assert args["timeout"] > 0
    assert args["timeout"] >= config.OPENCODE_IDLE_TIMEOUT_SECONDS


def test_rea_version_is_centralized():
    assert config.REA_AGENTS_VERSION == "6.4.0"
    assert config.NODE_MAJOR_VERSION == "24"


def test_opencode_config_uses_installed_rea_binary():
    config_path = ROOT / "integrations" / "opencode.json"
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    assert payload["mcp"]["rea"]["command"] == ["rea", "mcp"]
    assert "rea-agents@" not in config_path.read_text(encoding="utf-8")


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


def test_setup_persistence_repairs_stale_file_volume_entry(tmp_path):
    home = tmp_path / "home"
    store = tmp_path / "store"
    home_item = home / ".config" / "opencode"
    home_item.mkdir(parents=True)
    stale = store / ".config" / "opencode"
    stale.parent.mkdir(parents=True)
    stale.write_text("", encoding="utf-8")
    setup_persistence(
        [".config/opencode"],
        persistent_storage_dir=str(store),
        home_base=str(home),
    )
    assert stale.is_dir()
    assert home_item.is_symlink()
    assert home_item.resolve() == stale.resolve()


def test_setup_persistence_enforces_directories_without_home(tmp_path):
    home = tmp_path / "home"
    store = tmp_path / "store"
    stale = store / ".local" / "share" / "opencode"
    stale.parent.mkdir(parents=True)
    stale.write_text("", encoding="utf-8")
    setup_persistence(
        [".local/share/opencode"],
        persistent_storage_dir=str(store),
        home_base=str(home),
    )
    assert stale.is_dir()
    assert (home / ".local" / "share" / "opencode").is_symlink()


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
    assert "REA_AGENTS_VERSION" in src
    assert "npm install -g rea-agents@" in src
    assert "integrations" in src and "opencode.json" in src
    assisted_block = src.split("assisted_coding_image")[1].split("opencode_image")[0]
    assert "ln -sf /root/.opencode/bin/opencode /usr/local/bin/opencode" in assisted_block
    assert "mkdir -p /root/.config/opencode" in src
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


def test_assisted_box_forwards_opencode_web_tunnel():
    src = _source("runtime/shared_runtime.py")
    block = src.split("def run_devbox_shared")[1].split("def run_rdp_devbox_shared")[0]
    assert "ExitStack" in block
    assert "modal.forward(22" in block
    assert "modal.forward(OPENCODE_PORT" in block
    assert block.index("modal.forward(22") < block.index("modal.forward(OPENCODE_PORT")


def test_runtime_seeds_baseline_without_overwriting_config():
    src = _source("runtime/shared_runtime.py")
    assert "def seed_opencode_config" in src
    assert "os.path.getsize(target_path) > 0" in src
    assert "seed_opencode_config()" in src


def test_restore_preserves_image_installed_opencode():
    src = _source("runtime/backup_utils.py")
    assert '"-name", ".opencode"' in src or "'-name', '.opencode'" in src


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
    src = _source("ui/launcher_menu.py")
    assert 'choice == "9"' in src
    assert "launch_opencode.remote()" in src


def test_existing_launchers_still_defined():
    names = _top_level_names("devbox.py")
    for expected in ("launch_devbox", "launch_assisted_coding", "launch_rdp_devbox", "launch_llamacpp_playroom"):
        assert expected in names


# --- modal packaging (AST + source, no import) ---
#
# devbox.py executes remotely, so every module it imports at TOP LEVEL must
# be uploaded via add_local_python_source. A cpu_gate extraction once passed
# pytest locally but crash-looped every remote container with
# ModuleNotFoundError — these tests pin that gap shut.


def _top_level_local_imports(name):
    """Dotted top-level from-imports in a file (function-local excluded)."""
    tree = _tree(name)
    mods = set()
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            mods.add(node.module)
    return mods


def _packaged_modules():
    """Every module name passed to add_local_python_source in images.py."""
    mods = set()
    for node in ast.walk(_tree("devbox_core/images.py")):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == "add_local_python_source"):
            for arg in node.args:
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    mods.add(arg.value)
    return mods


def test_devbox_top_level_imports_are_packaged():
    packaged = _packaged_modules()
    for mod in _top_level_local_imports("devbox.py"):
        if mod.split(".")[0] in ("devbox_core", "runtime", "integrations", "ui"):
            assert mod in packaged, f"{mod} imported at devbox.py top level but never packaged"


def test_llamacpp_image_packages_llamacpp_modules():
    src = _source("devbox_core/images.py")
    block = src.split("llamacpp_cpu_image")[1].split("rdp_devbox_image")[0]
    assert "runtime.llamacpp_runtime" in block
    assert "devbox_core.llamacpp_models" in block
