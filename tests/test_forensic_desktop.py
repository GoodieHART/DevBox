"""Structural tests for the RDP-backed Forensics boxes.

Both forensic boxes run the xrdp + XFCE desktop from the shared layer. The
assertions cover image composition, the removal of the old browser stack, and
the runtime and HTB VM wiring for xrdp and port 3389.

Source inspection only, matching tests/test_image_packaging.py: no Modal
credentials, no GUI process, no network.
"""

import ast
import pathlib

from runtime import shared_runtime as shared

ROOT = pathlib.Path(__file__).resolve().parent.parent
SHARED_RUNTIME = ROOT / "runtime" / "shared_runtime.py"


def source(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


def _function(name: str) -> ast.FunctionDef:
    tree = ast.parse(SHARED_RUNTIME.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"{name} not found in runtime/shared_runtime.py")


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


def _forensic_block() -> str:
    images = source("devbox_core/images.py")
    return images.split("forensic_analysis_image = (", 1)[1].split(
        "llm_playroom_image", 1
    )[0]


# --- image composition ---


def test_forensic_image_builds_on_the_shared_rdp_desktop_layer():
    images = source("devbox_core/images.py")
    assert "_rdp_desktop_layer" in images
    assert "_rdp_desktop_layer" in _forensic_block()
    # The RDP box itself must use the same layer.
    rdp_block = images.split("rdp_devbox_image = (", 1)[1]
    assert "_rdp_desktop_layer" in rdp_block


def test_vnc_stack_and_chromium_are_gone_from_config():
    config = source("devbox_core/config.py")
    for package in ("chromium", "xvfb", "x11vnc", "novnc", "websockify", "openbox"):
        assert f'"{package}"' not in config, f"{package} should no longer be installed"
    for constant in ("VNC_DISPLAY", "VNC_GEOMETRY", "NOVNC_PORT", "VNC_BROWSER_PACKAGES"):
        assert constant not in config, f"{constant} should be removed"


def test_forensics_ships_firefox_and_network_diagnostics():
    config = source("devbox_core/config.py")
    for package in ("firefox-esr", "netcat-openbsd", "iputils-ping"):
        assert f'"{package}"' in config


def test_vnc_module_and_its_tests_are_deleted():
    assert not (ROOT / "runtime" / "vnc_browser.py").exists()
    assert not (ROOT / "tests" / "test_vnc_browser.py").exists()


# --- standalone forensic runtime ---


def test_forensic_runtime_starts_the_desktop_and_counts_rdp_activity():
    function = _function("run_opencode_shared")
    calls = _called_names(function)
    for name in (
        "prepare_xfce_session",
        "install_xsession_launcher",
        "install_desktop_shortcuts",
        "start_rdp_services",
        "count_rdp_sessions",
    ):
        assert name in calls, f"run_opencode_shared never calls {name}"

    segment = ast.get_source_segment(
        SHARED_RUNTIME.read_text(encoding="utf-8"), function
    ) or ""
    assert "RDP_DESKTOP_ITEMS" in segment
    assert "modal.forward(RDP_PORT" in segment
    assert "if forensic" in segment


def test_desktop_layer_helpers_exist_and_use_the_rdp_port():
    shared = source("runtime/shared_runtime.py")
    assert "RDP_DESKTOP_ITEMS = [" in shared
    assert "def prepare_xfce_session" in shared
    assert "def start_rdp_services" in shared
    assert "def print_rdp_connection" in shared
    config = source("devbox_core/config.py")
    assert "RDP_PORT = 3389" in config
    assert 'RDP_USER = "root"' in config
    assert 'RDP_PASSWORD = "devbox123"' in config


# --- HTB VM ---


def test_htb_forensic_vm_exposes_rdp_and_starts_xrdp():
    htb = source("runtime/htb_vm.py")
    assert "RDP_PORT" in htb
    assert "[22, 4096, RDP_PORT] if forensic else [22]" in htb
    assert "xrdp" in htb
    assert "startxfce4-wrapper" in htb
    assert "pgrep -f 'xrdp-chansrv|xfce4-session'" in htb


def test_htb_forensic_vm_no_longer_uses_vnc():
    htb = source("runtime/htb_vm.py")
    assert "vnc" not in htb.lower()
    assert "6080" not in htb


def test_htb_prints_rdp_credentials_only_for_the_forensic_vm():
    htb = source("runtime/htb_vm.py")
    assert "RDP_USER" in htb and "RDP_PASSWORD" in htb
    forensic_branch = htb.split("if forensic:", 1)[1]
    assert "rdp_tunnel" in forensic_branch


# --- tooling shortcuts ---


def _shortcut_block() -> str:
    images = source("devbox_core/images.py")
    return images.split("def _forensic_shortcut_commands", 1)[1].split(
        "\nforensic_analysis_image = (", 1
    )[0]


def test_shortcut_commands_are_wired_into_the_forensic_image():
    assert "*_forensic_shortcut_commands()" in _forensic_block()


def test_shortcuts_put_ghidra_and_jadx_on_path():
    block = _shortcut_block()
    for wrapper in ('"ghidra":', '"ghidra-headless":', '"jadx":', '"jadx-gui":'):
        assert wrapper in block, f"missing {wrapper} wrapper"
    assert "/usr/local/bin/{name}" in block
    # Install paths stay derived from the version constants.
    assert "ghidra_{GHIDRA_VERSION}_PUBLIC" in block
    assert "GHIDRA_PROJECTS_DIR" in block
    # The wrappers export the JDK themselves for desktop launches.
    assert "JAVA_HOME" in block and "/opt/java/temurin-21" in block


def test_shortcuts_add_desktop_entries():
    block = _shortcut_block()
    assert "/usr/share/applications/ghidra.desktop" in block
    assert "/usr/share/applications/jadx-gui.desktop" in block
    assert "/root/Desktop/ghidra.desktop" in block
    assert "/root/Desktop/jadx-gui.desktop" in block
    assert "Exec=/usr/local/bin/ghidra %f" in block
    assert "Exec=/usr/local/bin/jadx-gui %f" in block
    # The icon must exist in the installed themes, or XFCE shows a blank.
    assert "Icon=application-x-executable" in block
    assert "Icon=applications-development" in block
    assert "applications-engineering" not in block


def test_shortcuts_reach_non_login_shells():
    block = _shortcut_block()
    assert "/etc/profile.d/devbox-forensics.sh" in block
    assert "/etc/bash.bashrc" in block
    for alias in (
        "alias vol3='vol'",
        "alias vol.py='vol'",
        "alias volshell3='volshell'",
        "alias pspy='pspy64'",
    ):
        assert alias in block, f"missing {alias}"


def test_config_declares_the_ghidra_projects_directory_and_awt_libraries():
    config = source("devbox_core/config.py")
    assert 'GHIDRA_PROJECTS_DIR = "/data/forensics/ghidra"' in config
    for package in ("libxtst6", "libxi6", "libxrender1", "libxext6"):
        assert f'"{package}"' in config


def test_shortcut_wrappers_are_not_shadowed_by_the_jadx_bin_directory():
    # /opt/jadx/bin ahead of /usr/local/bin would bypass the JAVA_HOME wrappers.
    for name in ("devbox_core/images.py", "runtime/shared_runtime.py"):
        text = source(name)
        assert "/opt/jadx/bin:$PATH" not in text, f"{name} still prepends /opt/jadx/bin"


def test_persisted_profiles_drop_the_jadx_bin_directory():
    # Volumes written before the wrappers exist still prepend /opt/jadx/bin.
    shared_code = source("runtime/shared_runtime.py")
    assert 'replace("/opt/jadx/bin:", "")' in shared_code
    assert 'replace(":/opt/jadx/bin", "")' in shared_code


def test_desktop_shortcuts_are_reinstalled_on_launch(tmp_path):
    source_dir = tmp_path / "applications"
    source_dir.mkdir()
    for name in shared.DESKTOP_SHORTCUTS:
        (source_dir / f"{name}.desktop").write_text("[Desktop Entry]\n", encoding="utf-8")

    home = tmp_path / "root"
    shared.install_desktop_shortcuts(str(home), str(source_dir))

    for name in shared.DESKTOP_SHORTCUTS:
        entry = home / "Desktop" / f"{name}.desktop"
        assert entry.is_file()
        assert entry.stat().st_mode & 0o111, "desktop entries must be executable"


# --- docs ---


def test_readme_documents_rdp_instead_of_novnc():
    readme = source("README.md")
    assert "noVNC" not in readme
    assert "vnc.html" not in readme
    assert "devbox123" in readme
