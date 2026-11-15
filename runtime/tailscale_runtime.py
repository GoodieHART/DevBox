"""Tailscale runtime for DevBox boxes.

Brings up one Tailscale node per box: the daemon starts in the background,
the node is enrolled with an auth key, and the MagicDNS name and the node
address are read back from the control plane.

This module has no ``modal`` import: the Modal VM Sandbox image ships it, and
that image has no ``modal`` package. The same is true of
``devbox_core.box_identity``.

Facts this relies on:

* The Tailscale network interface is named ``tailscale``. Nothing here names
  the device: the daemon creates and owns it.
* Kernel mode (``--tun=tailscale``) needs ``/dev/net/tun`` and
  ``CAP_NET_ADMIN``. A VM Sandbox has both; a Modal Function container has
  neither, so the tun mode can be overridden for a userspace fallback.
* ``NetfilterMode`` defaults to on, so ``iptables`` has to be installed in
  the image or the netfilter rules fail.
* ``--state=mem:`` keeps the node state off disk.

No public function here raises: a failure is returned in the result, because
a box that cannot join the tailnet still runs.
"""

import json
import os
import subprocess
import sys
import time

from devbox_core.config import (
    TAILSCALE_AUTH_KEY_ENV,
    TAILSCALE_BIN,
    TAILSCALE_READY_TIMEOUT,
    TAILSCALE_SOCKET,
    TAILSCALE_STATE,
    TAILSCALED_BIN,
)

# The daemon log. A failed startup reports its tail, so the file lives for as
# long as the container.
TAILSCALE_LOG_PATH = "/tmp/tailscaled.log"

# Kernel mode: the daemon creates the WireGuard device itself. A Modal VM
# Sandbox has /dev/net/tun and CAP_NET_ADMIN; a Function container has
# neither, so the mode can be overridden.
TAILSCALE_TUN_MODE = "tailscale"

# Override for the tun mode, e.g. "userspace-networking" on a runtime
# without /dev/net/tun.
TAILSCALE_TUN_ENV = "DEVBOX_TAILSCALE_TUN"

# Seconds between polls of the Tailscale CLI.
_POLL_INTERVAL = 0.5

# The daemon handles, kept so the child is not reaped while it runs.
_DAEMONS = []


# --- helpers ---------------------------------------------------------------


def _socket_flag():
    """The global `--socket` flag that every invocation passes."""
    return f"--socket={TAILSCALE_SOCKET}"


def _socket_dir():
    return os.path.dirname(TAILSCALE_SOCKET)


def _client_installed():
    return os.path.exists(TAILSCALE_BIN)


def _redact(text, secret=""):
    """Remove the auth key from a message before it is shown or logged."""
    text = str(text or "").strip()
    if secret:
        text = text.replace(secret, "***")
    return text


def _log_tail(lines=20):
    """The tail of the daemon log, for a startup failure."""
    try:
        with open(TAILSCALE_LOG_PATH, "r", encoding="utf-8", errors="replace") as handle:
            content = handle.read().splitlines()
    except OSError as error:
        return f"(no daemon log: {error})"
    tail = content[-lines:]
    if not tail:
        return "(the daemon log is empty)"
    return "\n".join(tail)


def _cli(*args, timeout=30):
    """Run the Tailscale CLI against the standard socket.

    Returns `(returncode, stdout, stderr)`. A missing or failing CLI is a
    normal outcome: the caller turns it into a readable error.
    """
    command = [TAILSCALE_BIN, _socket_flag(), *[str(arg) for arg in args]]
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return 1, "", f"the command timed out after {timeout}s"
    except (OSError, subprocess.SubprocessError) as error:
        return 1, "", str(error)
    return completed.returncode, completed.stdout or "", completed.stderr or ""


def _status_payload():
    """The parsed `tailscale status --json` document, or None.

    None means the daemon did not answer. The exit code alone cannot tell that
    apart from a daemon that answered while the node was logged out, so the
    JSON document decides.
    """
    _code, out, _err = _cli("status", "--json")
    text = out.strip()
    if not text:
        return None
    try:
        payload = json.loads(text)
    except ValueError:
        return None
    return payload if isinstance(payload, dict) else None


def _daemon_answers():
    """True when the daemon is up and answering on the socket."""
    code, out, _err = _cli("status", "--json")
    if code == 0:
        return True
    # The daemon is up but the node still has to log in: the CLI exits
    # non-zero and still prints the status document.
    text = out.strip()
    if not text:
        return False
    try:
        payload = json.loads(text)
    except ValueError:
        return False
    return isinstance(payload, dict)


def _self_ip(status):
    """The node's Tailscale address: IPv4 when it has one, IPv6 otherwise."""
    self_node = (status or {}).get("Self") or {}
    addresses = self_node.get("TailscaleIPs") or []
    for address in addresses:
        if ":" not in str(address):
            return str(address)
    return str(addresses[0]) if addresses else None


def _self_dns_name(status):
    """The MagicDNS name out of a status document.

    The name is reported by the control plane, never constructed here, and
    the trailing root dot is dropped so it can be used as a host name.
    """
    self_node = (status or {}).get("Self") or {}
    return str(self_node.get("DNSName") or "").strip().rstrip(".")


def _wait_until(check, deadline):
    """Poll `check` until it is true or the deadline passes."""
    while True:
        if check():
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(_POLL_INTERVAL)


def _running_status():
    """The status document once the node is Running, or None."""
    payload = _status_payload()
    if payload is None:
        return None
    if str(payload.get("BackendState") or "") != "Running":
        return None
    return payload


def _start_daemon(tun_mode=TAILSCALE_TUN_MODE):
    """Start tailscaled in the background. It has to outlive this call."""
    command = [
        TAILSCALED_BIN,
        f"--tun={tun_mode}",
        # Node state stays in memory: nothing about the node is written to
        # disk, and a restarted container starts from a clean slate.
        f"--state={TAILSCALE_STATE}",
        _socket_flag(),
    ]
    try:
        os.makedirs(_socket_dir(), exist_ok=True)
    except OSError:
        # The directory usually exists in the image. If it cannot be
        # created, the daemon reports the real problem in its log.
        pass

    log = open(TAILSCALE_LOG_PATH, "ab", buffering=0)
    try:
        process = subprocess.Popen(
            command,
            stdout=log,
            stderr=log,
            stdin=subprocess.DEVNULL,
            # The daemon must survive this call and the shell that ran it.
            start_new_session=True,
        )
    finally:
        log.close()
    _DAEMONS.append(process)
    return process


# --- public API ------------------------------------------------------------


def tailscale_status():
    """The parsed `tailscale status --json` document, or {} on failure."""
    return _status_payload() or {}


def tailscale_ip():
    """The node's Tailscale address, read back from the control plane."""
    return _self_ip(tailscale_status())


def tailscale_logout():
    """Remove this node from the tailnet. True when the logout went through."""
    code, _out, _err = _cli("logout")
    return code == 0


def start_tailscale(hostname, auth_key=None, timeout=TAILSCALE_READY_TIMEOUT, tun=None):
    """Start tailscaled and bring the node up.

    Args:
        hostname: the node name to register in the tailnet.
        auth_key: the enrollment key. Falls back to the `TS_AUTHKEY`
            environment variable when it is missing or empty.
        timeout: seconds to wait for the node to reach the "Running" state.
        tun: the daemon tun mode. Defaults to kernel mode
            (`tailscale`), and can be overridden by the `DEVBOX_TAILSCALE_TUN`
            environment variable for a runtime without `/dev/net/tun`.

    Returns:
        dict: `{"ok": bool, "dns_name": str|None, "ip": str|None,
        "error": str|None}`. The DNS name and the address are the ones the
        control plane reported, never constructed here. Never raises.
    """
    result = {"ok": False, "dns_name": None, "ip": None, "error": None}

    try:
        key = str(auth_key or os.environ.get(TAILSCALE_AUTH_KEY_ENV) or "").strip()
        if not key:
            result["error"] = (
                "no Tailscale auth key: pass one or set "
                f"{TAILSCALE_AUTH_KEY_ENV}"
            )
            return result

        name = str(hostname or "").strip()
        if not name:
            result["error"] = "no hostname given for the Tailscale node"
            return result

        if not _client_installed():
            result["error"] = (
                f"the Tailscale client is not installed at {TAILSCALE_BIN}; "
                "the image is missing the Tailscale layer"
            )
            return result

        mode = str(
            tun or os.environ.get(TAILSCALE_TUN_ENV) or TAILSCALE_TUN_MODE
        ).strip()
        deadline = time.monotonic() + max(0.0, float(timeout))

        # A daemon that is already running is reused: starting a second one
        # on the same socket would only fail.
        if not _daemon_answers():
            _start_daemon(mode)

        if not _wait_until(_daemon_answers, deadline):
            result["error"] = (
                f"tailscaled did not answer on {TAILSCALE_SOCKET} within "
                f"{timeout}s:\n{_log_tail()}"
            )
            return result

        code, out, err = _cli(
            "up",
            f"--authkey={key}",
            f"--hostname={name}",
            timeout=max(1.0, deadline - time.monotonic()),
        )
        if code != 0:
            result["error"] = (
                f"tailscale up failed: {_redact(err or out, key)}\n{_log_tail()}"
            )
            return result

        if not _wait_until(lambda: _running_status() is not None, deadline):
            result["error"] = (
                "the Tailscale node did not reach the Running state within "
                f"{timeout}s:\n{_log_tail()}"
            )
            return result
        status = _running_status() or {}

        dns_name = _self_dns_name(status)
        ip = _self_ip(status)
        if not dns_name and not ip:
            result["error"] = (
                "the Tailscale node is Running but reports neither a DNS name "
                "nor an address"
            )
            return result

        result["ok"] = True
        result["dns_name"] = dns_name or None
        result["ip"] = ip
    except Exception as error:  # noqa: BLE001 - a box must never die over this
        result["error"] = f"{type(error).__name__}: {error}"

    return result


def main(argv=None):
    """CLI: `python3 -m runtime.tailscale_runtime up --hostname NAME`.

    Prints exactly one line of JSON on stdout:
    `{"ok": bool, "dns_name": str|None, "ip": str|None, "error": str|None}`.
    Exits 0 on success and 1 on failure. The auth key comes from the
    `TS_AUTHKEY` environment variable.
    """
    import argparse

    parser = argparse.ArgumentParser(
        prog="runtime.tailscale_runtime",
        description="Bring up the Tailscale node for this box.",
    )
    commands = parser.add_subparsers(dest="command")
    up = commands.add_parser("up", help="start tailscaled and join the tailnet")
    up.add_argument("--hostname", required=True, help="the node name in the tailnet")
    up.add_argument(
        "--timeout",
        type=int,
        default=TAILSCALE_READY_TIMEOUT,
        help="seconds to wait for the node to be Running",
    )
    commands.add_parser("status", help="print the node status document")

    try:
        args = parser.parse_args(argv)
    except SystemExit as exit_error:
        # argparse has already written the problem to stderr. The CLI
        # contract is an exit code, so hand one back instead of raising.
        return int(exit_error.code or 0)

    if args.command == "status":
        payload = tailscale_status()
        print(json.dumps(payload, sort_keys=True))
        return 0 if payload else 1

    if args.command != "up":
        parser.print_usage(sys.stderr)
        return 2

    result = start_tailscale(args.hostname, timeout=args.timeout)
    print(
        json.dumps(
            {
                "ok": bool(result.get("ok")),
                "dns_name": result.get("dns_name"),
                "ip": result.get("ip"),
                "error": result.get("error"),
            }
        )
    )
    return 0 if result.get("ok") else 1


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    sys.exit(main())
