"""Tests for the DevBox identity and Tailscale access on the HTB VM boxes.

The HTB boxes are the only DevBoxes that run in a Modal VM Sandbox, so they
are the only ones that can rename themselves and join a tailnet. These tests
pin the properties that make that safe:

* the name travels from the prompt to the sandbox, and only the two HTB
  launchers take it (the Function-based boxes are out of scope);
* Tailscale is enrolled before the VPN connect, and a failed enrollment never
  aborts the box;
* the auth key is only ever read from the environment, never passed as an
  argument and never written to the persistent volume;
* the connection block always keeps the Modal tunnel as a labelled fallback
  and never prints a half-empty Tailscale address.

`runtime.tailscale_runtime` is exercised in `tests/test_tailscale.py`; here
the VM script that calls it is inspected as source.
"""

import ast
import os
import pathlib
import subprocess

from devbox_core.box_identity import apply_sandbox_identity, resolve_box_name
from runtime.htb_vm import VM_SCRIPT, _print_ready_block, _wait_for_tailscale
from ui.launcher_menu import prompt_htb_vm

ROOT = pathlib.Path(__file__).resolve().parent.parent


def source(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


def _functions(name: str) -> dict:
    tree = ast.parse(source(name))
    return {
        node.name: node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def _sandbox_create_call():
    """The `modal.Sandbox.create(...)` call in the HTB VM runtime."""
    tree = ast.parse(source("runtime/htb_vm.py"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if (
            isinstance(func, ast.Attribute)
            and func.attr == "create"
            and isinstance(func.value, ast.Attribute)
            and func.value.attr == "Sandbox"
        ):
            return node
    return None


class FakeTunnel:
    """Stand-in for a Modal tunnel handle."""

    def __init__(self, host: str, port: int):
        self.unencrypted_host = host
        self.unencrypted_port = port


def _fake_tunnels():
    return {
        22: FakeTunnel("r505.modal.host", 40755),
        4096: FakeTunnel("r505.modal.host", 40756),
        3389: FakeTunnel("r505.modal.host", 40757),
    }


def _fake_tailscale():
    return {
        "DEVBOX_TAILSCALE_NAME": "devbox-htb-std-7f3a",
        "DEVBOX_TAILSCALE_IP": "100.101.102.103",
        "DEVBOX_TAILSCALE_DNS": "devbox-htb-std-7f3a.tail1234.ts.net",
    }


def _answers(monkeypatch, *values):
    """Feed `values` to input(), then raise EOFError like a closed stdin."""
    remaining = list(values)

    def fake_input(prompt=""):
        if not remaining:
            raise EOFError
        return remaining.pop(0)

    monkeypatch.setattr("builtins.input", fake_input)


# --- launcher plumbing ---


def test_both_htb_launchers_accept_a_box_name():
    functions = _functions("devbox.py")
    for name in ("launch_devbox_htb", "launch_forensics_htb"):
        arguments = [arg.arg for arg in functions[name].args.args]
        assert "box_name" in arguments, f"{name} must accept box_name"
        segment = source("devbox.py").split(f"def {name}", 1)[1][:900]
        assert "box_name=box_name" in segment
        assert "tailscale_secret=tailscale_secret" in segment


def test_the_function_launchers_do_not_take_a_box_name():
    """Only the two HTB VM boxes are in scope for the identity work."""
    functions = _functions("devbox.py")
    for name in (
        "launch_devbox",
        "launch_rdp_devbox",
        "launch_forensics_image",
        "launch_llamacpp_playroom",
        "launch_devbox_t4",
        "launch_assisted_coding",
    ):
        arguments = [arg.arg for arg in functions[name].args.args]
        assert "box_name" not in arguments, f"{name} must not take a box_name"


def test_the_tailscale_secret_is_declared_next_to_the_other_secrets():
    devbox = source("devbox.py")
    assert 'modal.Secret.from_name("tailscale-devbox-auth")' in devbox
    assert "tailscale_secret" in devbox


# --- the name prompt ---


def test_the_name_prompt_runs_on_both_htb_paths():
    menu = source("ui/launcher_menu.py")
    assert menu.count("= prompt_htb_vm(") == 2
    assert 'prompt_htb_vm("standard_devbox")' in menu
    assert 'prompt_htb_vm("forensic_analysis")' in menu
    assert (
        'launch_devbox_htb.remote(network=htb["network"], box_name=htb["box_name"])'
        in menu
    )
    assert (
        'launch_forensics_htb.remote(network=htb["network"], box_name=htb["box_name"])'
        in menu
    )


def test_the_name_prompt_uses_a_box_banner():
    menu = source("ui/launcher_menu.py")
    assert "create_box" in menu
    assert "BOX NAME" in menu
    assert "Name this box?" in menu


def test_the_name_prompt_defaults_to_a_generated_htb_name(monkeypatch, capsys):
    _answers(monkeypatch, "y", "1", "")
    result = prompt_htb_vm("standard_devbox")
    assert result["network"] == "labs"
    assert result["box_name"].startswith("devbox-htb-std-")
    # devbox-htb-std-<four hex characters>
    assert len(result["box_name"]) == len("devbox-htb-std-") + 4
    assert all(character in "0123456789abcdef" for character in result["box_name"][-4:])


def test_the_generated_name_matches_the_shared_identity_helper():
    """The prompt and the runtime must agree on how a name is built."""
    assert resolve_box_name("standard_devbox", htb=True).startswith("devbox-htb-std-")
    assert resolve_box_name("forensic_analysis", htb=True).startswith(
        "devbox-htb-forensics-"
    )
    assert resolve_box_name("standard_devbox", htb=True, custom="My Box") == "my-box"


def test_the_forensics_prompt_uses_the_forensics_name(monkeypatch, capsys):
    _answers(monkeypatch, "y", "1", "")
    result = prompt_htb_vm("forensic_analysis")
    assert result["box_name"].startswith("devbox-htb-forensics-")


def test_a_typed_name_is_used_after_sanitising(monkeypatch, capsys):
    _answers(monkeypatch, "y", "2", "My Lab Box")
    result = prompt_htb_vm("standard_devbox")
    assert result["network"] == "starting-point"
    assert result["box_name"] == "my-lab-box"


def test_the_name_prompt_is_eof_safe(monkeypatch, capsys):
    """EOF at the name prompt behaves exactly like pressing Enter."""
    _answers(monkeypatch, "y", "1")
    result = prompt_htb_vm("standard_devbox")
    assert result["network"] == "labs"
    assert result["box_name"].startswith("devbox-htb-std-")


def test_declining_the_vm_returns_none(monkeypatch, capsys):
    _answers(monkeypatch, "n")
    assert prompt_htb_vm("standard_devbox") is None


# --- the name reaches the sandbox ---


def test_run_htb_vm_resolves_the_name_with_htb_true():
    src = source("runtime/htb_vm.py")
    assert "resolve_box_name(devbox_type, htb=True, custom=box_name)" in src
    assert '"forensic_analysis" if forensic else "standard_devbox"' in src


def test_the_resolved_name_is_passed_into_the_sandbox():
    call = _sandbox_create_call()
    assert call is not None
    env = next(kw.value for kw in call.keywords if kw.arg == "env")
    keys = {key.value for key in env.keys}
    assert "DEVBOX_NAME" in keys
    assert "DEVBOX_MODE" in keys


def test_the_identity_is_applied_before_the_vm_script_is_exec_d():
    src = source("runtime/htb_vm.py")
    assert "apply_sandbox_identity(sandbox, name)" in src
    assert src.index("apply_sandbox_identity(sandbox, name)") < src.index("sandbox.exec(")


def test_the_launcher_writes_the_login_banner_with_the_name():
    src = source("runtime/htb_vm.py")
    # The banner is rendered by the launcher (with the box name) and written
    # into the sandbox, which the shell profile prints on login.
    assert "format_banner(" in src
    assert "name=name" in src
    assert 'sandbox.filesystem.write_text(banner, "/etc/devbox-banner")' in src
    assert "Persistent: /data" in source("runtime/shared_runtime.py")


# --- Tailscale inside the VM ---


def test_the_vm_script_calls_the_tailscale_runtime():
    assert "python3 -m runtime.tailscale_runtime up --hostname" in VM_SCRIPT
    assert '--hostname "$DEVBOX_NAME"' in VM_SCRIPT


def test_the_vm_script_starts_tailscale_before_the_vpn_connect():
    """The tailnet needs the normal default route, so it goes up first."""
    tailscale = VM_SCRIPT.index("python3 -m runtime.tailscale_runtime up --hostname")
    openvpn = VM_SCRIPT.index("openvpn --config")
    assert tailscale < openvpn
    # The enrollment call itself runs before the network loop.
    assert VM_SCRIPT.index("\nstart_tailscale\n") < VM_SCRIPT.index(
        "for network in $(printf"
    )


def test_a_failed_tailscale_enrollment_does_not_abort_the_vm():
    script = VM_SCRIPT
    # A non-zero exit is caught, so `set -e` cannot kill the box.
    assert "if ! ts_json=$(python3 -m runtime.tailscale_runtime up --hostname" in script
    # The failure is a warning on stderr and the script carries on.
    assert "WARNING: Tailscale is not available" in script
    assert script.index("\nstart_tailscale\n") < script.index("for network in $(printf")


def test_the_vm_script_publishes_the_tailscale_result():
    assert "/run/devbox/tailscale.env" in VM_SCRIPT
    assert "/run/devbox/tailscale.status" in VM_SCRIPT
    for key in (
        "DEVBOX_TAILSCALE_NAME",
        "DEVBOX_TAILSCALE_IP",
        "DEVBOX_TAILSCALE_DNS",
    ):
        assert key in VM_SCRIPT


# --- the auth key ---


def test_the_auth_key_is_never_passed_as_an_argument():
    """The key is read from TS_AUTHKEY by the runtime module, never passed."""
    assert "TS_AUTHKEY" not in VM_SCRIPT
    assert "--auth-key" not in VM_SCRIPT

    tree = ast.parse(source("runtime/htb_vm.py"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        for argument in node.args:
            if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
                assert "tskey-" not in argument.value
                assert "TS_AUTHKEY" not in argument.value


def test_the_auth_key_is_never_written_to_the_volume_or_printed():
    offending = [
        line
        for line in VM_SCRIPT.splitlines()
        if "TS_AUTHKEY" in line or "tskey-" in line.lower()
    ]
    assert offending == [], f"the auth key must not appear in the VM script: {offending}"

    # Nothing in the VM script writes the key onto the persistent volume.
    for line in VM_SCRIPT.splitlines():
        if "/data" in line:
            assert "TS_AUTHKEY" not in line

    # The launcher never prints a secret handle either.
    tree = ast.parse(source("runtime/htb_vm.py"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not (isinstance(node.func, ast.Name) and node.func.id == "print"):
            continue
        for argument in node.args:
            for inner in ast.walk(argument):
                if isinstance(inner, ast.Name):
                    assert inner.id not in {"TS_AUTHKEY", "tailscale_secret", "ts_secret"}


def test_the_tailscale_secret_is_optional():
    """A missing secret must not stop the box from launching."""
    src = source("runtime/htb_vm.py")
    assert "def _resolve_tailscale_secret" in src
    assert "tailscale_secret.hydrate()" in src
    assert "secrets.append(ts_secret)" in src
    # The secret is only attached when it resolved.
    assert "if ts_secret is not None:" in src


# --- the connection block ---


def test_the_connection_block_prints_the_short_name_and_keeps_the_modal_tunnel(capsys):
    _print_ready_block(_fake_tailscale(), _fake_tunnels(), False)
    out = capsys.readouterr().out
    assert "🔗 Tailscale (recommended):" in out
    assert 'ssh root@devbox-htb-std-7f3a -p 22 -t "tmux attach -t devbox"' in out
    assert "100.101.102.103" in out
    assert "devbox-htb-std-7f3a.tail1234.ts.net" in out
    assert "🚪 Modal tunnel (break-glass):" in out
    assert 'ssh root@r505.modal.host -p 40755 -t "tmux attach -t devbox"' in out
    # The recommended path is read first.
    assert out.index("Tailscale (recommended)") < out.index("Modal tunnel (break-glass)")


def test_the_connection_block_never_prints_an_empty_tailscale_address(capsys):
    _print_ready_block({}, _fake_tunnels(), False)
    out = capsys.readouterr().out
    assert "Tailscale (recommended)" not in out
    assert "Modal tunnel (break-glass)" in out
    assert "not available" in out


def test_the_connection_block_shows_why_tailscale_failed(capsys):
    _print_ready_block(
        {},
        _fake_tunnels(),
        False,
        tailscale_error="no Tailscale auth key: set TS_AUTHKEY",
    )
    out = capsys.readouterr().out
    assert "not available" in out
    assert "Reason: no Tailscale auth key: set TS_AUTHKEY" in out


class _FakeFileSystem:
    def __init__(self, files):
        self._files = files

    def read_text(self, path):
        if path not in self._files:
            raise FileNotFoundError(path)
        return self._files[path]


class _FakeSandbox:
    def __init__(self, files=None):
        self.filesystem = _FakeFileSystem(files or {})


def test_the_tailscale_failure_reason_is_read_from_the_vm():
    sandbox = _FakeSandbox(
        {"/run/devbox/tailscale.status": "failed: no Tailscale auth key\n"}
    )
    details, reason = _wait_for_tailscale(sandbox, timeout=1)
    assert details == {}
    assert reason == "no Tailscale auth key"


def test_a_tailscale_result_without_a_name_is_a_failure():
    sandbox = _FakeSandbox(
        {
            "/run/devbox/tailscale.status": "ok\n",
            "/run/devbox/tailscale.env": "DEVBOX_TAILSCALE_IP=100.1.2.3\n",
        }
    )
    details, reason = _wait_for_tailscale(sandbox, timeout=1)
    assert details == {}
    assert "no node name" in reason


class _FakeExecProcess:
    def __init__(self, stdout="", stderr="", returncode=0):
        self.stdout = _FakeStream(stdout)
        self.stderr = _FakeStream(stderr)
        self._returncode = returncode

    def wait(self):
        return self._returncode


class _FakeStream:
    def __init__(self, text):
        self._text = text

    def read(self):
        return self._text


class _FakeExecSandbox:
    def __init__(self, process):
        self._process = process
        self.calls = []

    def exec(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return self._process


def test_identity_runs_from_the_baked_package_with_an_explicit_pythonpath():
    sandbox = _FakeExecSandbox(
        _FakeExecProcess(stdout='{"name": "box", "hostname_changed": true, "reason": ""}\n')
    )
    result = apply_sandbox_identity(sandbox, "box")
    assert result["hostname_changed"] is True
    _args, kwargs = sandbox.calls[0]
    assert kwargs["workdir"] == "/root"
    assert kwargs["env"] == {"PYTHONPATH": "/root"}


def test_identity_reports_the_python_error_instead_of_unknown_reason():
    sandbox = _FakeExecSandbox(
        _FakeExecProcess(
            stderr="ModuleNotFoundError: No module named 'devbox_core'\n",
            returncode=1,
        )
    )
    result = apply_sandbox_identity(sandbox, "box")
    assert result["hostname_changed"] is False
    assert "ModuleNotFoundError" in result["reason"]


def test_the_forensics_block_shows_both_paths(capsys):
    _print_ready_block(_fake_tailscale(), _fake_tunnels(), True, rdp_password="devbox123")
    out = capsys.readouterr().out
    # Tailscale form: the real in-container ports.
    assert "http://devbox-htb-std-7f3a:4096" in out
    assert "devbox-htb-std-7f3a:3389" in out
    # Modal tunnel form.
    assert "http://r505.modal.host:40756" in out
    assert "r505.modal.host:40757" in out
    assert "username root" in out


# --- the VM script, run for real ---


def _run_vm_head(tmp_path, tailscale_module: str):
    """Run the head of the VM script (everything before the VPN connect)."""
    fake_pkg = tmp_path / "fake"
    (fake_pkg / "runtime").mkdir(parents=True)
    (fake_pkg / "runtime" / "__init__.py").write_text("")
    (fake_pkg / "runtime" / "tailscale_runtime.py").write_text(tailscale_module)

    run_dir = tmp_path / "run"
    run_dir.mkdir()
    banner = tmp_path / "devbox-banner"

    head = VM_SCRIPT.split("connect_vpn() {")[0]
    head = head.replace("/run/devbox", str(run_dir))
    head = head.replace("/etc/devbox-banner", str(banner))
    head = head.replace("cd /root", f"cd {tmp_path}")
    script = tmp_path / "vm-head.sh"
    script.write_text(head)

    env = dict(os.environ)
    env["PYTHONPATH"] = f"{fake_pkg}:{ROOT}"
    env["DEVBOX_NAME"] = "devbox-htb-std-7f3a"
    env["DEVBOX_MODE"] = "standard"

    result = subprocess.run(
        ["sh", str(script)],
        cwd=str(tmp_path),
        env=env,
        text=True,
        capture_output=True,
    )
    return result, run_dir


def test_the_vm_script_survives_a_failed_enrollment(tmp_path):
    module = (
        "import sys\n"
        "sys.stderr.write('tailscale: no auth key\\n')\n"
        "sys.exit(1)\n"
    )
    result, run_dir = _run_vm_head(tmp_path, module)
    assert result.returncode == 0, result.stderr
    assert "WARNING: Tailscale is not available" in result.stderr
    assert (run_dir / "tailscale.status").read_text().startswith("failed")
    assert not (run_dir / "tailscale.env").exists()


def test_the_vm_script_publishes_the_connection_details_on_success(tmp_path):
    module = (
        "print('{\"ok\": true, "
        "\"dns_name\": \"devbox-htb-std-7f3a.tail1234.ts.net.\", "
        "\"ip\": \"100.101.102.103\", \"error\": null}')\n"
    )
    result, run_dir = _run_vm_head(tmp_path, module)
    assert result.returncode == 0, result.stderr
    assert "Tailscale up as devbox-htb-std-7f3a" in result.stdout
    assert (run_dir / "tailscale.status").read_text().strip() == "ok"
    published = dict(
        line.split("=", 1)
        for line in (run_dir / "tailscale.env").read_text().splitlines()
        if "=" in line
    )
    assert published["DEVBOX_TAILSCALE_NAME"] == "devbox-htb-std-7f3a"
    assert published["DEVBOX_TAILSCALE_IP"] == "100.101.102.103"
    assert published["DEVBOX_TAILSCALE_DNS"] == "devbox-htb-std-7f3a.tail1234.ts.net"
