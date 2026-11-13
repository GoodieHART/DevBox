"""Structural tests for the RDP-backed Forensics boxes.

Both forensic boxes run the xrdp + XFCE desktop from the shared layer. The
assertions cover image composition, the removal of the old browser stack, and
the runtime and HTB VM wiring for xrdp and port 3389.

Source inspection only, matching tests/test_image_packaging.py: no Modal
credentials, no GUI process, no network.
"""

import ast
import pathlib

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


# --- docs ---


def test_readme_documents_rdp_instead_of_novnc():
    readme = source("README.md")
    assert "noVNC" not in readme
    assert "vnc.html" not in readme
    assert "devbox123" in readme
