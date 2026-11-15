"""Tests for HTB Labs and Starting Point VPN selection.

Pins the properties that make choosing between the two networks safe: every
choice maps to real profiles with distinct env keys and tun devices (a shared
key would silently drop one pack), the VM script connects each selected network
before SSH starts, a missing secret fails before a sandbox is created, and both
launch paths pass the network through.
"""

import ast
import pathlib
import subprocess

import pytest

from runtime.htb_vm import VM_SCRIPT, resolve_htb_networks

ROOT = pathlib.Path(__file__).resolve().parent.parent


def source(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


def _functions(name: str) -> dict[str, ast.FunctionDef]:
    tree = ast.parse(source(name))
    return {
        node.name: node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
    }


# --- network resolution ---


def test_default_network_is_labs():
    names, profiles = resolve_htb_networks(None)
    assert names == ("labs",)
    assert [profile["secret"] for profile in profiles] == ["htb-vpn"]
    assert [profile["key"] for profile in profiles] == ["HTB_OVPN_CONFIG"]
    assert [profile["device"] for profile in profiles] == ["tun0"]


def test_starting_point_uses_its_own_secret_key_and_device():
    names, profiles = resolve_htb_networks("starting-point")
    assert names == ("starting-point",)
    profile = profiles[0]
    assert profile["secret"] == "htb-starting-point"
    assert profile["key"] == "HTB_SP_OVPN_CONFIG"
    assert profile["device"] == "tun1"


@pytest.mark.parametrize("alias", ["starting_point", "sp", "Starting-Point"])
def test_starting_point_aliases_resolve(alias):
    assert resolve_htb_networks(alias)[0] == ("starting-point",)


def test_both_connects_two_networks_on_separate_devices():
    names, profiles = resolve_htb_networks("both")
    assert names == ("labs", "starting-point")
    assert len({profile["device"] for profile in profiles}) == 2
    assert len({profile["key"] for profile in profiles}) == 2
    assert len({profile["secret"] for profile in profiles}) == 2


def test_unknown_network_is_rejected():
    with pytest.raises(ValueError):
        resolve_htb_networks("academy")


# --- rendered VM script ---


def test_script_parses_as_posix_shell():
    result = subprocess.run(
        ["sh", "-n"], input=VM_SCRIPT, text=True, capture_output=True
    )
    assert result.returncode == 0, result.stderr


def test_script_has_a_case_arm_per_network():
    assert 'labs) connect_vpn labs "${HTB_OVPN_CONFIG:-}" tun0 ;;' in VM_SCRIPT
    assert (
        'starting-point) connect_vpn starting-point "${HTB_SP_OVPN_CONFIG:-}" tun1 ;;'
        in VM_SCRIPT
    )


def test_script_requires_the_network_list_argument():
    assert "${3:?network list is required}" in VM_SCRIPT


def test_script_connects_vpns_before_ssh_and_desktop():
    assert VM_SCRIPT.index("connect_vpn()") < VM_SCRIPT.index("/usr/sbin/sshd")
    assert VM_SCRIPT.index("connect_vpn()") < VM_SCRIPT.index("/usr/sbin/xrdp")


def test_script_fails_loudly_when_a_pack_is_empty():
    assert "VPN pack is empty; cannot connect" in VM_SCRIPT
    assert "AUTH_FAILED|Cannot open TUN|Exiting due to fatal error" in VM_SCRIPT


# --- fail fast ---


def test_missing_secret_is_detected_before_the_sandbox_starts():
    src = source("runtime/htb_vm.py")
    assert "secret.hydrate()" in src
    assert "modal.exception.NotFoundError" in src
    assert "modal.exception.ConflictError" in src
    # The message must contain a runnable fix.
    assert "modal secret create" in src
    assert src.index("_require_vpn_secrets(profiles)") < src.index("modal.Sandbox.create")


# --- launcher plumbing ---


def test_both_htb_entrypoints_accept_a_network():
    functions = _functions("devbox.py")
    for name in ("launch_devbox_htb", "launch_forensics_htb"):
        arguments = [arg.arg for arg in functions[name].args.args]
        assert "network" in arguments, f"{name} must accept network"
        segment = source("devbox.py").split(f"def {name}", 1)[1][:600]
        assert "network=network" in segment


def test_menu_prompts_for_the_network_on_both_paths():
    menu = source("ui/launcher_menu.py")
    assert "Enable HTB VPN VM mode?" in menu
    assert "def prompt_htb_vm" in menu
    assert "HTB Starting Point" in menu
    assert menu.count("= prompt_htb_vm(") == 2
    assert (
        'launch_devbox_htb.remote(network=htb["network"], box_name=htb["box_name"])'
        in menu
    )
    assert (
        'launch_forensics_htb.remote(network=htb["network"], box_name=htb["box_name"])'
        in menu
    )


def test_readme_documents_the_starting_point_secret():
    readme = source("README.md")
    assert "htb-starting-point" in readme
    assert "HTB_SP_OVPN_CONFIG" in readme
    assert "Starting Point" in readme
