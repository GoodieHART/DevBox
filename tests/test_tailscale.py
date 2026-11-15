"""Tests for the Tailscale runtime and the image layer that installs it.

Everything here is offline: no Modal credentials, no network, no tailnet.
The runtime is exercised against a faked Tailscale CLI, and the image layer
is checked by building the image definitions against a fake `modal.Image`,
the way tests/test_image_packaging.py inspects the source tree.

What the tests pin down:

* the runtime module is importable inside a Modal VM Sandbox, which ships no
  `modal` package, so it must not import modal at all;
* the client is a pinned, checksum-verified download, and every image that
  runs Tailscale gets it plus the iptables its netfilter rules need;
* the DNS name and the address are read back from the control plane instead
  of being constructed from the hostname.
"""

import ast
import json
import pathlib
import subprocess
import sys
import types

import pytest

from devbox_core import config
from runtime import tailscale_runtime

ROOT = pathlib.Path(__file__).resolve().parent.parent
IMAGES = ROOT / "devbox_core" / "images.py"
RUNTIME = ROOT / "runtime" / "tailscale_runtime.py"

RUNNING_STATUS = {
    "BackendState": "Running",
    "Self": {
        "ID": "n1234567890",
        "HostName": "devbox-std-abcd",
        "DNSName": "devbox-std-abcd.tail1a2b3.ts.net.",
        "TailscaleIPs": ["100.101.102.103", "fd7a:115c:a1e0::1"],
    },
}


def source(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


# --- the runtime module ----------------------------------------------------


def test_runtime_module_never_imports_modal():
    """The VM Sandbox image ships this module but no `modal` package."""
    tree = ast.parse(RUNTIME.read_text(encoding="utf-8"))
    offenders = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            offenders += [
                alias.name for alias in node.names
                if alias.name.split(".")[0] == "modal"
            ]
        elif isinstance(node, ast.ImportFrom):
            if (node.module or "").split(".")[0] == "modal":
                offenders.append(node.module)
    assert offenders == [], f"runtime/tailscale_runtime.py imports modal: {offenders}"


def test_runtime_module_never_hardcodes_the_tailscale0_interface():
    """The interface is named `tailscale`, not `tailscale0`."""
    assert "tailscale0" not in RUNTIME.read_text(encoding="utf-8")


def test_runtime_module_never_constructs_a_tailnet_name():
    """The DNS name comes from the control plane, never from the hostname."""
    text = RUNTIME.read_text(encoding="utf-8")
    assert "ts.net" not in text


def test_runtime_module_only_imports_packaged_first_party_modules():
    """`devbox_core.config` is packaged into every image."""
    tree = ast.parse(RUNTIME.read_text(encoding="utf-8"))
    imported = set()
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
        elif isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
    first_party = {
        name for name in imported
        if name.split(".")[0] in {"devbox_core", "runtime", "ui", "integrations"}
    }
    assert first_party == {"devbox_core.config"}


# --- the pinned constants --------------------------------------------------


def test_tailscale_version_is_pinned():
    assert config.TAILSCALE_VERSION == "1.104.7"


def test_tarball_url_matches_the_pinned_version():
    assert config.TAILSCALE_TARBALL_URL == (
        "https://pkgs.tailscale.com/stable/tailscale_1.104.7_amd64.tgz"
    )
    assert f"tailscale_{config.TAILSCALE_VERSION}_amd64.tgz" in (
        config.TAILSCALE_TARBALL_URL
    )


def test_checksum_is_a_sha256_digest():
    digest = config.TAILSCALE_SHA256
    assert len(digest) == 64
    assert all(character in "0123456789abcdef" for character in digest)
    assert digest == (
        "e56693ff74a64f2591b7e819c280635a100aae1ddfb0ef058fcd052b7cd8d16c"
    )


def test_socket_state_and_binary_paths_are_standardised():
    assert config.TAILSCALE_SOCKET == "/run/tailscale/tailscaled.sock"
    assert config.TAILSCALE_STATE == "mem:"
    assert config.TAILSCALE_BIN == "/usr/local/bin/tailscale"
    assert config.TAILSCALED_BIN == "/usr/local/bin/tailscaled"
    assert config.TAILSCALE_READY_TIMEOUT == 90
    assert config.TAILSCALE_AUTH_KEY_ENV == "TS_AUTHKEY"
    assert config.TAILSCALE_SECRET_NAME == "tailscale-devbox-auth"


# --- the image layer -------------------------------------------------------


class _FakeImage:
    """A stand-in for `modal.Image` that records the build steps."""

    def __init__(self, tag="fake"):
        self.tag = tag
        self.apt_packages = []
        self.pip_packages = []
        self.commands = []
        self.local_files = []
        self.python_sources = []
        self.steps = []

    def apt_install(self, *packages):
        self.apt_packages.append(list(packages))
        self.steps.append(("apt_install", list(packages)))
        return self

    def pip_install(self, *packages):
        self.pip_packages.append(list(packages))
        self.steps.append(("pip_install", list(packages)))
        return self

    def run_commands(self, *commands, **kwargs):
        self.commands.append(list(commands))
        self.steps.append(("run_commands", list(commands)))
        return self

    def add_local_file(self, local_path, remote_path, **kwargs):
        self.local_files.append((str(local_path), remote_path))
        self.steps.append(("add_local_file", remote_path))
        return self

    def add_local_python_source(self, *modules, **kwargs):
        self.python_sources.append(list(modules))
        self.steps.append(("add_local_python_source", list(modules)))
        return self

    def all_commands(self):
        return [command for group in self.commands for command in group]


def _fake_modal():
    """A `modal` module that only knows how to build fake images."""
    modal = types.ModuleType("modal")

    class Image(_FakeImage):
        @staticmethod
        def debian_slim(python_version=None, **kwargs):
            return _FakeImage(tag=f"debian_slim:{python_version}")

        @staticmethod
        def from_registry(tag, **kwargs):
            return _FakeImage(tag=tag)

    modal.Image = Image
    return modal


def _load_images(monkeypatch):
    """Import devbox_core/images.py against the fake Modal."""
    monkeypatch.setitem(sys.modules, "modal", _fake_modal())
    namespace = {"__name__": "devbox_core.images", "__file__": str(IMAGES)}
    exec(compile(IMAGES.read_text(encoding="utf-8"), str(IMAGES), "exec"), namespace)
    return namespace


def _tailscale_commands(image):
    """The build commands that install the Tailscale client."""
    return [
        command
        for command in image.all_commands()
        if "tailscale" in command
    ]


def test_layer_verifies_the_checksum_before_installing(monkeypatch):
    images = _load_images(monkeypatch)
    layer = images["_tailscale_layer"](_FakeImage())

    commands = layer.all_commands()
    download = next(c for c in commands if "curl" in c)
    assert config.TAILSCALE_TARBALL_URL in download

    verify = next(c for c in commands if "sha256sum -c -" in c)
    assert config.TAILSCALE_SHA256 in verify
    # The checksum is checked before anything is unpacked.
    assert commands.index(verify) < commands.index(
        next(c for c in commands if "tar -xzf" in c)
    )


def test_layer_installs_both_binaries_into_usr_local_bin(monkeypatch):
    images = _load_images(monkeypatch)
    layer = images["_tailscale_layer"](_FakeImage())

    commands = layer.all_commands()
    install = next(c for c in commands if "install -m 755" in c and "tailscaled" in c)
    assert "/tmp/tailscale/tailscaled" in install
    assert config.TAILSCALED_BIN in install

    install_client = next(
        c for c in commands if "install -m 755" in c and "tailscaled" not in c
    )
    assert "/tmp/tailscale/tailscale" in install_client
    assert config.TAILSCALE_BIN in install_client


def test_the_layer_is_pinned_to_one_version(monkeypatch):
    """One version, one URL, one checksum."""
    images = _load_images(monkeypatch)
    layer = images["_tailscale_layer"](_FakeImage())

    commands = layer.all_commands()
    downloads = [c for c in commands if "curl" in c]
    assert len(downloads) == 1
    assert config.TAILSCALE_TARBALL_URL in downloads[0]
    assert config.TAILSCALE_VERSION in config.TAILSCALE_TARBALL_URL

    verifications = [c for c in commands if "sha256sum -c -" in c]
    assert len(verifications) == 1
    assert config.TAILSCALE_SHA256 in verifications[0]


def test_layer_installs_iptables_for_the_netfilter_rules(monkeypatch):
    images = _load_images(monkeypatch)
    layer = images["_tailscale_layer"](_FakeImage())

    installed = [package for group in layer.apt_packages for package in group]
    assert "iptables" in installed


def test_layer_creates_the_socket_directory_and_drops_the_tarball(monkeypatch):
    images = _load_images(monkeypatch)
    layer = images["_tailscale_layer"](_FakeImage())

    commands = layer.all_commands()
    assert any("mkdir -p /run/tailscale" in command for command in commands)
    assert any("rm -rf" in command and "tailscale.tgz" in command for command in commands)


def test_base_builders_include_the_tailscale_layer(monkeypatch):
    images = _load_images(monkeypatch)
    for builder in ("create_base_devbox_image", "create_base_minimal_image"):
        image = images[builder]()
        commands = _tailscale_commands(image)
        assert commands, f"{builder} does not install the Tailscale client"
        assert any(config.TAILSCALE_SHA256 in command for command in commands)
        assert "iptables" in [
            package for group in image.apt_packages for package in group
        ]


def test_cuda_image_carries_its_own_copy_of_the_layer(monkeypatch):
    """The CUDA image starts from the NVIDIA registry, not a base builder."""
    images = _load_images(monkeypatch)
    image = images["cuda_devbox_image"]

    commands = _tailscale_commands(image)
    assert commands, "the CUDA image does not install the Tailscale client"
    assert any(config.TAILSCALE_SHA256 in command for command in commands)
    assert any(config.TAILSCALE_BIN in command for command in commands)
    assert "iptables" in [
        package for group in image.apt_packages for package in group
    ]


def test_every_image_ships_the_tailscale_client(monkeypatch):
    images = _load_images(monkeypatch)
    for name, image in images.items():
        if not isinstance(image, _FakeImage):
            continue
        commands = _tailscale_commands(image)
        assert commands, f"{name} does not install the Tailscale client"
        assert any(config.TAILSCALE_SHA256 in command for command in commands)


def test_the_tailscale_layer_is_applied_before_the_local_file_mounts(monkeypatch):
    """Modal rejects build steps after a local-file mount."""
    images = _load_images(monkeypatch)
    for name, image in images.items():
        if not isinstance(image, _FakeImage):
            continue
        steps = image.steps
        tailscale_step = next(
            index
            for index, (method, payload) in enumerate(steps)
            if method == "run_commands"
            and any(config.TAILSCALE_SHA256 in command for command in payload)
        )
        first_mount = next(
            (
                index
                for index, (method, _payload) in enumerate(steps)
                if method in {"add_local_file", "add_local_python_source"}
            ),
            None,
        )
        assert first_mount is not None, f"{name} mounts nothing"
        assert tailscale_step < first_mount, (
            f"{name} installs the Tailscale client after a local-file mount; "
            "Modal rejects build steps that come after a mount"
        )


# --- packaging -------------------------------------------------------------


def _image_assignments() -> dict[str, ast.Assign]:
    tree = ast.parse(IMAGES.read_text(encoding="utf-8"))
    return {
        node.targets[0].id: node
        for node in tree.body
        if isinstance(node, ast.Assign)
        and isinstance(node.targets[0], ast.Name)
        and node.targets[0].id.endswith("_image")
    }


def _packaged_modules() -> dict[str, list[str]]:
    packaged = {}
    for name, node in _image_assignments().items():
        modules = []
        for sub in ast.walk(node):
            if (
                isinstance(sub, ast.Call)
                and isinstance(sub.func, ast.Attribute)
                and sub.func.attr == "add_local_python_source"
            ):
                modules += [
                    arg.value for arg in sub.args if isinstance(arg, ast.Constant)
                ]
        packaged[name] = modules
    return packaged


def test_every_image_packages_the_tailscale_runtime():
    for image, modules in _packaged_modules().items():
        assert "runtime.tailscale_runtime" in modules, (
            f"{image} does not package runtime.tailscale_runtime; the box "
            "cannot bring up a Tailscale node"
        )


def test_every_image_packages_the_box_identity():
    for image, modules in _packaged_modules().items():
        assert "devbox_core.box_identity" in modules, (
            f"{image} does not package devbox_core.box_identity"
        )


# --- the runtime, against a faked CLI --------------------------------------


class _Result:
    def __init__(self, returncode, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class _Process:
    pid = 4242


class _FakeCLI:
    """A stand-in for the Tailscale CLI.

    `status --json` reports "not answering" until `ready_after` calls have
    been made, so the runtime has to start the daemon first.
    """

    def __init__(self, status=None, ready_after=0, up_code=0, up_message="Success."):
        self.status = status if status is not None else RUNNING_STATUS
        self.ready_after = ready_after
        self.up_code = up_code
        self.up_message = up_message
        self.status_calls = 0
        self.commands = []

    def run(self, command, capture_output=False, text=False, timeout=None):
        self.commands.append(list(command))
        args = list(command[2:])
        if args[:2] == ["status", "--json"]:
            self.status_calls += 1
            if self.status_calls <= self.ready_after:
                return _Result(1, "", "status: failed to connect to local tailscaled")
            return _Result(0, json.dumps(self.status), "")
        if args and args[0] == "up":
            if self.up_code == 0:
                return _Result(0, self.up_message, "")
            return _Result(self.up_code, "", self.up_message)
        return _Result(0, "", "")

    def popen(self, command, **kwargs):
        self.commands.append(list(command))
        return _Process()

    def commands_with(self, needle):
        return [command for command in self.commands if needle in command]

    def daemon_commands(self):
        """The commands that started tailscaled itself."""
        return [
            command for command in self.commands
            if command and str(command[0]).endswith("tailscaled")
        ]


@pytest.fixture
def fake_cli(monkeypatch, tmp_path):
    """Install the fake CLI and the fake environment the runtime needs."""
    cli = _FakeCLI()
    fake = types.SimpleNamespace(
        run=cli.run,
        Popen=cli.popen,
        TimeoutExpired=subprocess.TimeoutExpired,
        SubprocessError=subprocess.SubprocessError,
        DEVNULL=subprocess.DEVNULL,
    )
    monkeypatch.setattr(tailscale_runtime, "subprocess", fake)
    monkeypatch.setattr(tailscale_runtime, "_POLL_INTERVAL", 0)
    monkeypatch.setattr(tailscale_runtime, "_client_installed", lambda: True)
    monkeypatch.setattr(tailscale_runtime, "TAILSCALE_LOG_PATH", str(tmp_path / "tailscaled.log"))
    monkeypatch.setattr(tailscale_runtime, "_socket_dir", lambda: str(tmp_path))
    monkeypatch.delenv(tailscale_runtime.TAILSCALE_AUTH_KEY_ENV, raising=False)
    monkeypatch.delenv(tailscale_runtime.TAILSCALE_TUN_ENV, raising=False)
    return cli


def test_start_tailscale_reads_the_name_and_address_back_from_the_status(fake_cli):
    result = tailscale_runtime.start_tailscale("devbox-std-abcd", auth_key="tskey")

    assert result["ok"] is True
    assert result["error"] is None
    # The DNS name is the one the control plane reported, not one built
    # from the hostname.
    assert result["dns_name"] == "devbox-std-abcd.tail1a2b3.ts.net"
    assert result["ip"] == "100.101.102.103"


def test_start_tailscale_uses_the_auth_key_from_the_environment(fake_cli, monkeypatch):
    monkeypatch.setenv(tailscale_runtime.TAILSCALE_AUTH_KEY_ENV, "tskey-env")

    result = tailscale_runtime.start_tailscale("devbox-std-abcd")

    assert result["ok"] is True
    up = fake_cli.commands_with("up")[0]
    assert "--authkey=tskey-env" in up


def test_start_tailscale_without_a_key_fails_cleanly(fake_cli):
    result = tailscale_runtime.start_tailscale("devbox-std-abcd")

    assert result["ok"] is False
    assert result["dns_name"] is None
    assert result["ip"] is None
    assert tailscale_runtime.TAILSCALE_AUTH_KEY_ENV in result["error"]


def test_start_tailscale_reports_the_daemon_log_when_the_node_never_runs(
    fake_cli, monkeypatch, tmp_path
):
    (tmp_path / "tailscaled.log").write_text(
        "log: failed to connect to local tailscaled\n", encoding="utf-8"
    )
    monkeypatch.setattr(fake_cli, "status", {"BackendState": "NoState"})
    monkeypatch.setattr(fake_cli, "ready_after", 0)

    result = tailscale_runtime.start_tailscale(
        "devbox-std-abcd", auth_key="tskey", timeout=0
    )

    assert result["ok"] is False
    assert "did not reach the Running state" in result["error"]
    # The log tail is what makes the failure debuggable.
    assert "failed to connect to local tailscaled" in result["error"]


def test_start_tailscale_reports_a_failed_tailscale_up(fake_cli, monkeypatch):
    monkeypatch.setattr(fake_cli, "up_code", 1)
    monkeypatch.setattr(
        fake_cli, "up_message", "failed to register node: invalid auth key"
    )

    result = tailscale_runtime.start_tailscale("devbox-std-abcd", auth_key="tskey-secret")

    assert result["ok"] is False
    assert "tailscale up failed" in result["error"]


def test_the_auth_key_never_appears_in_an_error(fake_cli, monkeypatch):
    monkeypatch.setattr(fake_cli, "up_code", 1)
    monkeypatch.setattr(fake_cli, "up_message", "auth key tskey-secret was rejected")

    result = tailscale_runtime.start_tailscale("devbox-std-abcd", auth_key="tskey-secret")

    assert "tskey-secret" not in result["error"]
    assert "***" in result["error"]


def test_the_daemon_runs_in_kernel_mode_with_memory_state(fake_cli, monkeypatch):
    monkeypatch.setattr(fake_cli, "ready_after", 2)

    result = tailscale_runtime.start_tailscale("devbox-std-abcd", auth_key="tskey")

    assert result["ok"] is True
    daemon = fake_cli.daemon_commands()[0]
    assert "--tun=tailscale" in daemon
    assert "--state=mem:" in daemon
    assert f"--socket={config.TAILSCALE_SOCKET}" in daemon


def test_every_cli_call_uses_the_standard_socket(fake_cli, monkeypatch):
    monkeypatch.setattr(fake_cli, "ready_after", 2)

    tailscale_runtime.start_tailscale("devbox-std-abcd", auth_key="tskey")

    assert fake_cli.commands
    for command in fake_cli.commands:
        assert f"--socket={config.TAILSCALE_SOCKET}" in command


def test_the_tun_mode_can_be_overridden(fake_cli, monkeypatch):
    monkeypatch.setattr(fake_cli, "ready_after", 2)
    monkeypatch.setenv(tailscale_runtime.TAILSCALE_TUN_ENV, "userspace-networking")

    result = tailscale_runtime.start_tailscale("devbox-std-abcd", auth_key="tskey")

    assert result["ok"] is True
    daemon = fake_cli.daemon_commands()[0]
    assert "--tun=userspace-networking" in daemon


def test_tailscale_status_returns_the_parsed_document(fake_cli):
    status = tailscale_runtime.tailscale_status()
    assert status["BackendState"] == "Running"
    assert status["Self"]["DNSName"] == "devbox-std-abcd.tail1a2b3.ts.net."


def test_tailscale_status_is_empty_when_the_daemon_is_gone(fake_cli, monkeypatch):
    monkeypatch.setattr(fake_cli, "ready_after", 10_000)
    assert tailscale_runtime.tailscale_status() == {}


def test_tailscale_ip_reads_the_address_from_the_status(fake_cli):
    assert tailscale_runtime.tailscale_ip() == "100.101.102.103"


def test_tailscale_ip_is_none_without_a_node(fake_cli, monkeypatch):
    monkeypatch.setattr(fake_cli, "ready_after", 10_000)
    assert tailscale_runtime.tailscale_ip() is None


# --- the CLI ---------------------------------------------------------------


def test_cli_prints_one_json_line_and_exits_zero(fake_cli, capsys, monkeypatch):
    monkeypatch.setenv(tailscale_runtime.TAILSCALE_AUTH_KEY_ENV, "tskey")

    code = tailscale_runtime.main(["up", "--hostname", "devbox-std-abcd"])

    assert code == 0
    out = capsys.readouterr().out
    lines = [line for line in out.splitlines() if line.strip()]
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert set(payload) == {"ok", "dns_name", "ip", "error"}
    assert payload["ok"] is True
    assert payload["dns_name"] == "devbox-std-abcd.tail1a2b3.ts.net"
    assert payload["ip"] == "100.101.102.103"
    assert payload["error"] is None


def test_cli_exits_one_when_the_node_does_not_come_up(fake_cli, capsys, monkeypatch):
    monkeypatch.setenv(tailscale_runtime.TAILSCALE_AUTH_KEY_ENV, "tskey")
    monkeypatch.setattr(fake_cli, "up_code", 1)
    monkeypatch.setattr(fake_cli, "up_message", "registration failed")

    code = tailscale_runtime.main(["up", "--hostname", "devbox-std-abcd"])

    assert code == 1
    payload = json.loads(capsys.readouterr().out.strip())
    assert payload["ok"] is False
    assert payload["error"]


def test_cli_never_prints_the_auth_key(fake_cli, capsys, monkeypatch):
    monkeypatch.setenv(tailscale_runtime.TAILSCALE_AUTH_KEY_ENV, "tskey-secret")
    monkeypatch.setattr(fake_cli, "up_code", 1)
    monkeypatch.setattr(fake_cli, "up_message", "auth key tskey-secret was rejected")

    code = tailscale_runtime.main(["up", "--hostname", "devbox-std-abcd"])

    assert code == 1
    captured = capsys.readouterr()
    assert "tskey-secret" not in captured.out
    assert "tskey-secret" not in captured.err


def test_cli_without_a_command_returns_a_failure_code(fake_cli, capsys):
    assert tailscale_runtime.main([]) != 0
