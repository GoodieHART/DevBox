"""HTB VPN VM launcher.

OpenVPN needs /dev/net/tun, which only Modal VM Sandboxes (`runtime="vm"`)
provide, so HTB networks run here rather than in the Function-based boxes.

A box can join Labs, Starting Point, or both: each network gets its own tun
device, and their non-overlapping machine ranges let both route tables coexist.

The VM Sandbox is the only DevBox runtime that can rewrite its own hostname:
it has its own kernel, and Tailscale runs in kernel mode alongside the HTB VPN.
The HTB profile is a split tunnel, so the default route stays on eth0 and the
tailnet and the lab ranges do not contend for it.
"""

import sys
import time

import modal

from devbox_core.config import (
    HTB_DEFAULT_NETWORK,
    HTB_NETWORK_CHOICES,
    HTB_VPN_NETWORKS,
)
from runtime.shared_runtime import format_banner

# Files the in-VM Tailscale step writes: the connection details on success, and
# the outcome either way. Both live under /run, never on the persistent volume.
TAILSCALE_ENV_PATH = "/run/devbox/tailscale.env"
TAILSCALE_STATUS_PATH = "/run/devbox/tailscale.status"

# One `case` arm per network, generated from config so the secret key, device,
# and name cannot drift apart. VM_SCRIPT is not an f-string (it is full of shell
# `${...}`), so the arms are interpolated in.
_VPN_DISPATCH = "\n".join(
    f'        {name}) connect_vpn {name} "${{{profile["key"]}:-}}" {profile["device"]} ;;'
    for name, profile in HTB_VPN_NETWORKS.items()
)

_NETWORK_ALIASES = {
    "labs": "labs",
    "machines": "labs",
    "starting-point": "starting-point",
    "starting_point": "starting-point",
    "startingpoint": "starting-point",
    "sp": "starting-point",
    "both": "both",
}


def resolve_htb_networks(network=None):
    """Expand a launcher choice into the concrete networks to connect.

    Returns `(names, profiles)`: names for the VM script and their config
    entries. Unknown values raise rather than falling back to Labs, so a typo
    cannot put a Starting Point session on the wrong network.
    """
    choice = str(network or HTB_DEFAULT_NETWORK).strip().lower()
    resolved = _NETWORK_ALIASES.get(choice)
    if resolved is None:
        raise ValueError(
            f"unknown HTB network {network!r}; expected one of "
            + ", ".join(HTB_NETWORK_CHOICES)
        )
    names = ("labs", "starting-point") if resolved == "both" else (resolved,)
    return names, [HTB_VPN_NETWORKS[name] for name in names]


def _secret_help(profile, error):
    return (
        f"❌ The {profile['label']} VPN cannot start: {error}\n"
        f"   Create the secret with:\n"
        f"     modal secret create {profile['secret']} "
        f'{profile["key"]}="$(cat {profile["file"]})"\n'
        f"   Pack: {profile['pack']}"
    )


def _require_vpn_secrets(profiles):
    """Resolve each network's secret, failing before any sandbox is billed.

    `Secret.from_name()` is lazy, so `hydrate()` is what makes a missing secret
    or key fail here rather than after the sandbox and image pull.
    """
    secrets = []
    for profile in profiles:
        secret = modal.Secret.from_name(
            profile["secret"], required_keys=[profile["key"]]
        )
        try:
            secret.hydrate()
        except (modal.exception.NotFoundError, modal.exception.ConflictError) as error:
            raise SystemExit(_secret_help(profile, error)) from error
        secrets.append(secret)
    return secrets


def _resolve_tailscale_secret(tailscale_secret):
    """Return a usable Tailscale secret, or None when there is none.

    Tailscale is optional: the box still launches with the Modal tunnel alone,
    so a missing secret is a warning and never a failed launch. `from_name()`
    is lazy, so `hydrate()` is what turns a missing secret into that warning
    instead of a failed sandbox creation.
    """
    if tailscale_secret is None:
        return None
    try:
        tailscale_secret.hydrate()
    except Exception as error:  # noqa: BLE001 - Tailscale must never be fatal
        print(
            f"⚠️  Tailscale is unavailable ({error}); "
            "the box will use the Modal tunnel only."
        )
        return None
    return tailscale_secret


VM_SCRIPT = (
    r'''#!/bin/sh
set -eu
mkdir -p /run/devbox

# The box identity and the box type arrive as environment variables, so they
# never show up in the arguments of anything below.
DEVBOX_NAME="${DEVBOX_NAME:-devbox-htb-box}"
DEVBOX_MODE="${1:-standard}"
export DEVBOX_NAME DEVBOX_MODE
# The image mounts the DevBox python packages under /root.
export PYTHONPATH="/root${PYTHONPATH:+:$PYTHONPATH}"
cd /root

TS_STATUS=/run/devbox/tailscale.status
TS_ENV=/run/devbox/tailscale.env
TS_LOG=/run/devbox/tailscale.log

# Tailscale comes up before the VPN. The HTB profile is a split tunnel, so the
# default route stays on eth0 and the tailnet reaches its control plane over
# the normal route. A failure here is never fatal: the box still gets a Modal
# tunnel.
parse_tailscale_result() {
    python3 -c 'import json, os, sys

data = {}
try:
    data = json.loads(sys.stdin.read() or "{}")
except Exception:
    data = {}

ip = str(data.get("ip") or "").strip()
dns = str(data.get("dns_name") or "").strip().rstrip(".")
name = os.environ.get("DEVBOX_NAME", "").strip()
if dns and "." in dns:
    name = dns.split(".")[0]
reason = " ".join(str(data.get("error") or "").split())[:300]

if data.get("ok") and name:
    with open("/run/devbox/tailscale.env", "w") as handle:
        handle.write("DEVBOX_TAILSCALE_NAME=%s\n" % name)
        handle.write("DEVBOX_TAILSCALE_IP=%s\n" % ip)
        handle.write("DEVBOX_TAILSCALE_DNS=%s\n" % dns)
    with open("/run/devbox/tailscale.status", "w") as handle:
        handle.write("ok\n")
    print("Tailscale up as %s (%s)" % (name, ip))
else:
    with open("/run/devbox/tailscale.status", "w") as handle:
        handle.write("failed: %s\n" % (reason or "no tailnet address"))
    print("Tailscale unavailable: %s" % (reason or "no tailnet address"))
'
}

start_tailscale() {
    ts_json=""
    if ! ts_json=$(python3 -m runtime.tailscale_runtime up --hostname "$DEVBOX_NAME" 2>"$TS_LOG"); then
        # A failed enrollment is never fatal: the box keeps the Modal tunnel.
        # The runtime still prints its JSON result, which explains the failure.
        if [ -n "$ts_json" ]; then
            printf '%s' "$ts_json" | parse_tailscale_result
            return 0
        fi
        ts_reason=$(tail -n 1 "$TS_LOG" 2>/dev/null || true)
        [ -n "$ts_reason" ] || ts_reason="tailscale up failed"
        printf 'failed: %s\n' "$ts_reason" > "$TS_STATUS"
        return 0
    fi
    printf '%s' "$ts_json" | parse_tailscale_result
}

start_tailscale
ts_status=$(cat "$TS_STATUS" 2>/dev/null || printf 'failed: unknown error')
if [ "$ts_status" != "ok" ]; then
    printf 'WARNING: Tailscale is not available (%s); continuing with the Modal tunnel only.\n' "$ts_status" >&2
fi

connect_vpn() {
    label=$1
    config=$2
    device=$3
    if [ -z "$config" ]; then
        printf '%s VPN pack is empty; cannot connect\n' "$label" >&2
        exit 1
    fi
    printf '%s' "$config" > "/run/devbox/htb-$label.ovpn"
    chmod 600 "/run/devbox/htb-$label.ovpn"
    openvpn --config "/run/devbox/htb-$label.ovpn" \
        --dev "$device" \
        --pull-filter ignore "ifconfig-ipv6" \
        --pull-filter ignore "route-ipv6" \
        --pull-filter ignore "redirect-gateway ipv6" \
        --log "/run/devbox/openvpn-$label.log" --daemon
    for _ in $(seq 1 60); do
        if grep -q 'Initialization Sequence Completed' "/run/devbox/openvpn-$label.log" 2>/dev/null; then
            printf '%s VPN connected on %s.\n' "$label" "$device"
            return 0
        fi
        if grep -Eq 'AUTH_FAILED|Cannot open TUN|Exiting due to fatal error' "/run/devbox/openvpn-$label.log" 2>/dev/null; then
            cat "/run/devbox/openvpn-$label.log" >&2
            exit 1
        fi
        sleep 1
    done
    cat "/run/devbox/openvpn-$label.log" >&2
    printf '%s VPN did not finish connecting within 60s\n' "$label" >&2
    exit 1
}

for network in $(printf '%s' "${3:?network list is required}" | tr ',' ' '); do
    case "$network" in
__VPN_DISPATCH__
        *)
            printf 'Unknown HTB network: %s\n' "$network" >&2
            exit 1
            ;;
    esac
done

mkdir -p /root/.ssh /var/run/sshd
if [ -n "${PUBKEYS:-}" ]; then printf '%s\n' "$PUBKEYS" > /root/.ssh/authorized_keys; fi
if [ -n "${PUBKEY:-}" ]; then printf '%s\n' "$PUBKEY" > /root/.ssh/authorized_keys; fi
chmod 600 /root/.ssh/authorized_keys
/usr/sbin/sshd
# Shared bootstrap, so this VM gets the baked config instead of tmux defaults.
sh /usr/local/bin/devbox-tmux devbox 3 ||
    printf 'tmux session setup failed; SSH will land in a plain shell\n' >&2
if [ "$1" = "forensic" ]; then
    mkdir -p /data/forensics /data/forensics/uploads
    cd /data/forensics
    opencode web --port 4096 --hostname 0.0.0.0 >/run/devbox/opencode.log 2>&1 &
    # Same xrdp + XFCE desktop as the RDP Desktop Box. This VM has no
    # persistence restore, so the launcher is written on every boot.
    mkdir -p /var/run/xrdp /run/dbus /root/.config/xfce4 /root/.cache/sessions /tmp/xdg-runtime
    rm -f /run/dbus/pid /run/dbus/system_bus_socket
    chmod 700 /tmp/xdg-runtime
    printf '#!/bin/sh\nexec /usr/local/bin/startxfce4-wrapper\n' > /root/.xsession
    chmod +x /root/.xsession
    if ! dbus-daemon --system --fork; then
        printf 'dbus-daemon failed to start; the desktop may not load\n' >&2
    fi
    if ! /usr/sbin/xrdp-sesman; then
        printf 'xrdp-sesman failed to start; the desktop will be unavailable\n' >&2
    fi
    if ! /usr/sbin/xrdp; then
        printf 'xrdp failed to start; the desktop will be unavailable\n' >&2
    fi
fi
# `opencode web` answers `/` regardless of watchers, so mirror
# count_web_clients() and count established clients. A probe that cannot run
# counts as activity: a broken `ss` must not shut the box down under a user.
web_clients_active() {
    if ! clients=$(ss -Htn state established "sport = :4096" 2>/dev/null); then
        return 0
    fi
    [ -n "$clients" ]
}

idle_seconds=0
idle_interval=15
idle_timeout=${2:?idle timeout is required}
printf 'HTB VPN ready (%s). Idle timeout: %ss.\n' "$3" "$idle_timeout"
while [ "$idle_seconds" -lt "$idle_timeout" ]; do
    sleep "$idle_interval"
    active=0
    if pgrep -f 'sshd: root@' >/dev/null 2>&1; then
        active=1
    fi
    if [ "$1" = "forensic" ] && web_clients_active; then
        active=1
    fi
    if [ "$1" = "forensic" ] && pgrep -f 'xrdp-chansrv|xfce4-session' >/dev/null 2>&1; then
        active=1
    fi
    if [ "$active" -eq 1 ]; then
        idle_seconds=0
    else
        idle_seconds=$((idle_seconds + idle_interval))
    fi
done
printf 'Idle timeout reached; shutting down.\n' >&2
exit 0
'''
).replace("__VPN_DISPATCH__", _VPN_DISPATCH)


def _read_sandbox_file(sandbox, path):
    """Read a file from the sandbox, returning "" when it is not there yet."""
    try:
        return sandbox.filesystem.read_text(path)
    except Exception:  # noqa: BLE001 - a missing file is the normal case here
        return ""


def _wait_for_tailscale(sandbox, process=None, timeout=120):
    """Wait for the VM script to publish its Tailscale result.

    Returns `(details, reason)`. `details` is the connection details as a
    dict, empty when Tailscale did not come up. `reason` is the readable
    failure the VM published, and "" on success. The box runs on the Modal
    tunnel alone when `details` is empty, and the reason is what makes that
    visible instead of a bare "not available".
    """
    deadline = time.time() + timeout
    status = ""
    while time.time() < deadline:
        status = _read_sandbox_file(sandbox, TAILSCALE_STATUS_PATH).strip()
        if status:
            break
        if process is not None and process.poll() is not None:
            # The VM script died before publishing a result.
            return {}, "the VM script exited before publishing a Tailscale result"
        time.sleep(2)

    if not status:
        return {}, f"no Tailscale result after {timeout}s"

    if not status.startswith("ok"):
        reason = status.partition(":")[2].strip()
        return {}, reason or status

    values = {}
    for line in _read_sandbox_file(sandbox, TAILSCALE_ENV_PATH).splitlines():
        key, _, value = line.partition("=")
        if key.strip():
            values[key.strip()] = value.strip()

    if not values.get("DEVBOX_TAILSCALE_NAME"):
        return {}, "the Tailscale result has no node name"
    return values, ""


def _print_field(label, value):
    """One aligned row of the connection block."""
    print(f"   {label:<12}{value}")


def _print_ready_block(
    tailscale,
    tunnels,
    forensic=False,
    *,
    opencode_port=4096,
    rdp_port=3389,
    rdp_user="root",
    rdp_password="",
    tailscale_error="",
):
    """Print the connection block for a ready HTB box.

    The Tailscale address comes first and the Modal tunnel is the labelled
    break-glass fallback. When Tailscale did not come up, only the Modal
    tunnel block is printed, never a half-empty Tailscale address.
    """
    title = (
        "🔍  Your HTB Forensics DevBox is ready!"
        if forensic
        else "🛡️  Your HTB DevBox is ready!"
    )
    print()
    print("=" * 60)
    print(title)
    print("=" * 60)
    print()

    short = (tailscale or {}).get("DEVBOX_TAILSCALE_NAME", "")
    if short:
        print("🔗 Tailscale (recommended):")
        _print_field(
            "SSH:", f'ssh root@{short} -p 22 -t "tmux attach -t devbox"'
        )
        tailnet_ip = tailscale.get("DEVBOX_TAILSCALE_IP", "")
        if tailnet_ip:
            _print_field("Tailnet IP:", tailnet_ip)
        dns_name = tailscale.get("DEVBOX_TAILSCALE_DNS", "")
        if dns_name:
            _print_field("Full DNS:", dns_name)
        if forensic:
            _print_field("OpenCode:", f"http://{short}:{opencode_port}")
            _print_field("RDP:", f"{short}:{rdp_port}")
        print()
    else:
        print("⚠️  Tailscale is not available - use the Modal tunnel below.")
        if tailscale_error:
            print(f"    Reason: {tailscale_error}")
        print()

    print("🚪 Modal tunnel (break-glass):")
    ssh_tunnel = tunnels[22]
    _print_field(
        "SSH:",
        f'ssh root@{ssh_tunnel.unencrypted_host} -p {ssh_tunnel.unencrypted_port} '
        '-t "tmux attach -t devbox"',
    )
    if forensic:
        web_tunnel = tunnels[opencode_port]
        _print_field(
            "OpenCode:",
            f"http://{web_tunnel.unencrypted_host}:{web_tunnel.unencrypted_port}",
        )
        rdp_tunnel = tunnels[rdp_port]
        _print_field(
            "RDP:",
            f"{rdp_tunnel.unencrypted_host}:{rdp_tunnel.unencrypted_port} "
            f"(username {rdp_user}, password {rdp_password})",
        )
    print("=" * 60)


def run_htb_vm(
    image,
    volume,
    ssh_secret,
    *,
    forensic=False,
    resources=None,
    network=None,
    box_name=None,
    tailscale_secret=None,
):
    from devbox_core.box_identity import apply_sandbox_identity, resolve_box_name
    from devbox_core.config import (
        IDLE_TIMEOUT_SECONDS,
        OPENCODE_IDLE_TIMEOUT_SECONDS,
        OPENCODE_PORT,
        RDP_PASSWORD,
        RDP_PORT,
        RDP_USER,
    )

    devbox_type = "forensic_analysis" if forensic else "standard_devbox"
    name = resolve_box_name(devbox_type, htb=True, custom=box_name)

    names, profiles = resolve_htb_networks(network)
    vpn_secrets = _require_vpn_secrets(profiles)
    labels = ", ".join(profile["label"] for profile in profiles)

    idle_timeout = OPENCODE_IDLE_TIMEOUT_SECONDS if forensic else IDLE_TIMEOUT_SECONDS
    exposed_ports = [22, OPENCODE_PORT, RDP_PORT] if forensic else [22]

    secrets = [ssh_secret, *vpn_secrets]
    ts_secret = _resolve_tailscale_secret(tailscale_secret)
    if ts_secret is not None:
        secrets.append(ts_secret)

    sandbox = modal.Sandbox.create(
        "sleep",
        "infinity",
        app=modal.App.lookup("personal-devbox-launcher", create_if_missing=True),
        image=image,
        runtime="vm",
        secrets=secrets,
        env={
            "DEVBOX_IDLE_TIMEOUT": str(idle_timeout),
            "DEVBOX_NAME": name,
            "DEVBOX_MODE": "forensic" if forensic else "standard",
            # The image mounts the DevBox python packages under /root.
            "PYTHONPATH": "/root",
        },
        volumes={"/data": volume},
        cpu=resources.get("cpu") if resources else None,
        memory=resources.get("memory") if resources else None,
        timeout=resources.get("timeout") if resources else None,
        unencrypted_ports=exposed_ports,
    )
    print(f"HTB network(s): {labels}")
    print(f"Box name: {name}")
    extra_lines = (
        ("🌐 OpenCode web on :4096", "🖥️ RDP desktop on :3389") if forensic else ()
    )
    banner = format_banner(
        "forensic_analysis" if forensic else "standard_devbox",
        extra_lines,
        name=name,
    )
    sandbox.filesystem.write_text(banner, "/etc/devbox-banner")
    try:
        # The VM has its own kernel, so the box can rename itself. This runs
        # before the VM script, so SSH lands on the named box.
        identity = apply_sandbox_identity(sandbox, name)
        if not identity.get("hostname_changed"):
            print(
                f"⚠️  Hostname unchanged: "
                f"{identity.get('reason') or 'unknown reason'}"
            )
        sandbox.filesystem.write_text(VM_SCRIPT, "/run/devbox-vm.sh")
        process = sandbox.exec(
            "sh",
            "/run/devbox-vm.sh",
            "forensic" if forensic else "standard",
            str(idle_timeout),
            ",".join(names),
        )
        tailscale, tailscale_error = _wait_for_tailscale(sandbox, process)
        tunnels = sandbox.tunnels(timeout=120)
        _print_ready_block(
            tailscale,
            tunnels,
            forensic,
            opencode_port=OPENCODE_PORT,
            rdp_port=RDP_PORT,
            rdp_user=RDP_USER,
            rdp_password=RDP_PASSWORD,
            tailscale_error=tailscale_error,
        )
        for line in process.stdout:
            print(line, end="")
        while process.poll() is None:
            time.sleep(5)
        exit_code = process.wait()
        stderr = process.stderr.read()
        if stderr:
            print(stderr, end="", file=sys.stderr)
        if exit_code != 0:
            raise RuntimeError(f"HTB VM Sandbox exited with status {exit_code}")
    finally:
        sandbox.terminate(wait=True)
