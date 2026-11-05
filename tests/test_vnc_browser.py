"""Structural tests for the loopback Chromium/noVNC stack.

The stack only makes sense if three properties hold together:

1. Every listener binds loopback; the phone reaches it through an SSH forward.
2. The browser starts only for the Forensics HTB VM, never the standard VM.
3. The packages and module are present in the forensic image that launches it.

These tests inspect source and the rendered script instead of executing GUI
processes, matching tests/test_image_packaging.py.
"""

import pathlib
import subprocess

from devbox_core.config import (
    NOVNC_PORT,
    NOVNC_WEB_ROOT,
    VNC_PROFILE_DIR,
    VNC_RFB_PORT,
)
from runtime.vnc_browser import VNC_BROWSER_SCRIPT

ROOT = pathlib.Path(__file__).resolve().parent.parent


def source(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


def test_script_keeps_every_listener_on_loopback():
    rendered = VNC_BROWSER_SCRIPT
    assert f'RFB_PORT="{VNC_RFB_PORT}"' in rendered
    assert f'NOVNC_PORT="{NOVNC_PORT}"' in rendered
    assert '127.0.0.1:$RFB_PORT' in rendered
    assert '127.0.0.1:$NOVNC_PORT' in rendered
    assert "-localhost" in rendered
    assert "-nopw" in rendered
    assert "0.0.0.0" not in rendered


def test_script_starts_the_full_browser_stack():
    rendered = VNC_BROWSER_SCRIPT
    assert "Xvfb" in rendered
    assert "openbox" in rendered
    assert "chromium" in rendered
    assert "x11vnc" in rendered
    assert "websockify" in rendered
    assert f'PROFILE="{VNC_PROFILE_DIR}"' in rendered
    assert f'WEB_ROOT="{NOVNC_WEB_ROOT}"' in rendered
    assert '--user-data-dir="$PROFILE"' in rendered
    assert '--web="$WEB_ROOT"' in rendered
    assert "--no-sandbox" in rendered
    assert "--disable-dev-shm-usage" in rendered
    assert "-nolisten tcp" in rendered
    assert "about:blank" in rendered.split()
    assert "vnc.html?autoconnect=1&resize=scale" in rendered


def test_script_clears_chromium_singleton_locks():
    rendered = VNC_BROWSER_SCRIPT
    assert "SingletonLock" in rendered
    assert "SingletonSocket" in rendered
    assert "SingletonCookie" in rendered


def test_script_has_no_unresolved_placeholders():
    rendered = VNC_BROWSER_SCRIPT
    assert "__VNC_" not in rendered
    assert "__NOVNC_" not in rendered


def test_script_parses_with_sh():
    result = subprocess.run(
        ["sh", "-n"],
        input=VNC_BROWSER_SCRIPT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_config_declares_browser_packages():
    config = source("devbox_core/config.py")
    for package in (
        "chromium",
        "xvfb",
        "x11vnc",
        "novnc",
        "websockify",
        "openbox",
        "fonts-liberation",
        "x11-utils",
    ):
        assert f'"{package}"' in config


def test_script_is_written_before_sandbox_exec():
    src = source("runtime/htb_vm.py")
    assert src.index('write_text(VNC_BROWSER_SCRIPT, "/run/devbox-vnc.sh")') < src.index(
        "process = sandbox.exec"
    )


def test_forensic_htb_vm_starts_browser_after_sshd():
    src = source("runtime/htb_vm.py")
    assert src.index("openvpn --config") < src.index("/usr/sbin/sshd")
    assert src.index("/usr/sbin/sshd") < src.index("sh /run/devbox-vnc.sh")
    assert "if ! sh /run/devbox-vnc.sh; then" in src


def test_browser_script_is_written_only_for_forensic_vm():
    src = source("runtime/htb_vm.py")
    forensic = src.index("if forensic:")
    write = src.index(
        'sandbox.filesystem.write_text(VNC_BROWSER_SCRIPT, "/run/devbox-vnc.sh")'
    )
    assert "from runtime.vnc_browser import VNC_BROWSER_SCRIPT" in src
    assert forensic < write


def test_connection_string_appends_the_ssh_forward():
    src = source("runtime/htb_vm.py")
    assert 'f" -L {NOVNC_PORT}:127.0.0.1:{NOVNC_PORT}" if forensic else ""' in src
    assert '?autoconnect=1&resize=scale' in src


def test_vnc_port_is_not_exposed_as_a_modal_tunnel():
    src = source("runtime/htb_vm.py")
    port_line = next(
        line for line in src.splitlines() if "unencrypted_ports=" in line
    )
    assert "6080" not in port_line


def test_forensic_image_ships_browser_packages_and_module():
    images = source("devbox_core/images.py")
    forensic = images.split("forensic_analysis_image", 1)[1].split(
        "llm_playroom_image", 1
    )[0]
    assert "*VNC_BROWSER_PACKAGES" in forensic
    assert '"runtime.vnc_browser"' in forensic


def test_standard_image_does_not_ship_browser_stack():
    images = source("devbox_core/images.py")
    standard = images.split("standard_devbox_image", 1)[1].split(
        "cuda_devbox_image", 1
    )[0]
    assert "VNC_BROWSER_PACKAGES" not in standard
    assert '"runtime.vnc_browser"' not in standard
