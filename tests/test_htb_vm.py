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
    assert 'pull-filter ignore "ifconfig-ipv6"' in src
    assert 'pull-filter ignore "route-ipv6"' in src
    assert 'pull-filter ignore "redirect-gateway ipv6"' in src
    assert "idle_timeout=${2:?idle timeout is required}" in src
    assert "pgrep -f 'sshd: root@'" in src
    assert "curl -fsS --max-time 2 http://127.0.0.1:4096/" in src
    assert "OPENCODE_IDLE_TIMEOUT_SECONDS if forensic else IDLE_TIMEOUT_SECONDS" in src


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


def test_forensics_image_includes_essential_tooling():
    config = source("devbox_core/config.py")
    images = source("devbox_core/images.py")
    for package in ("nmap", "smbclient", "chntpw", "dislocker", "libbde-utils", "libvmdk-utils"):
        assert f'"{package}"' in config
    for package in ("pypykatz", "impacket"):
        assert f'"{package}"' in config
    assert '"runtime.htb_vm"' in images.split("forensic_analysis_image", 1)[1].split("llm_playroom_image", 1)[0]
    assert "/pspy/releases/download/{PSPY_VERSION}/pspy64" in images
    assert "sha256sum -c" in images


def test_htb_launchers_exist_and_are_reachable_from_menu():
    devbox = source("devbox.py")
    menu = source("ui/launcher_menu.py")
    assert "launch_devbox_htb" in names("devbox.py")
    assert "launch_forensics_htb" in names("devbox.py")
    assert "launch_devbox_htb" in devbox
    assert "launch_forensics_htb" in devbox
    assert "Enable HTB VPN VM mode?" in menu
