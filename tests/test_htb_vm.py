import ast
import pathlib


ROOT = pathlib.Path(__file__).resolve().parent.parent


def source(name):
    return (ROOT / name).read_text(encoding="utf-8")


def names(name):
    tree = ast.parse(source(name))
    return {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    }


def test_htb_vm_runtime_uses_vm_sandbox_and_required_secret():
    src = source("runtime/htb_vm.py")
    assert "modal.Sandbox.create" in src
    assert 'runtime="vm"' in src
    assert 'modal.Secret.from_name("htb-vpn"' in src
    assert 'required_keys=["HTB_OVPN_CONFIG"]' in src
    assert "sandbox.tunnels" in src
    assert "exit_code = process.wait()" in src
    assert "stderr = process.stderr.read()" in src


def test_htb_entrypoint_starts_openvpn_before_services():
    src = source("runtime/htb_vm.py")
    assert "openvpn --config /run/devbox/htb.ovpn" in src
    assert "Initialization Sequence Completed" in src
    assert src.index("openvpn --config") < src.index("/usr/sbin/sshd")


def test_htb_images_package_entrypoint_and_openvpn():
    config = source("devbox_core/config.py")
    images = source("devbox_core/images.py")
    assert '"openvpn"' in config
    assert '"iproute2"' in config
    assert '"runtime.htb_vm"' in images.split("standard_devbox_image", 1)[1].split("cuda_devbox_image", 1)[0]


def test_forensics_image_packages_htb_runtime():
    images = source("devbox_core/images.py")
    forensic_block = images.split("forensic_analysis_image", 1)[1].split("llm_playroom_image", 1)[0]
    assert '"runtime.htb_vm"' in forensic_block


def test_htb_launchers_exist_and_are_reachable_from_menu():
    devbox = source("devbox.py")
    menu = source("ui/launcher_menu.py")
    assert "launch_devbox_htb" in names("devbox.py")
    assert "launch_forensics_htb" in names("devbox.py")
    assert "launch_devbox_htb" in devbox
    assert "launch_forensics_htb" in devbox
    assert "Enable HTB VPN VM mode?" in menu
