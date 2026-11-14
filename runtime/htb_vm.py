"""HTB VPN VM launcher.

OpenVPN needs /dev/net/tun, which only Modal VM Sandboxes (`runtime="vm"`)
provide, so HTB networks run here rather than in the Function-based boxes.

A box can join Labs, Starting Point, or both: each network gets its own tun
device, and their non-overlapping machine ranges let both route tables coexist.
"""

import time

import modal

from devbox_core.config import (
    HTB_DEFAULT_NETWORK,
    HTB_NETWORK_CHOICES,
    HTB_VPN_NETWORKS,
)

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


VM_SCRIPT = (
    r'''#!/bin/sh
set -eu
mkdir -p /run/devbox

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
    if [ "$1" = "forensic" ] && curl -fsS --max-time 2 http://127.0.0.1:4096/ >/dev/null 2>&1; then
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


def run_htb_vm(image, volume, ssh_secret, *, forensic=False, resources=None, network=None):
    from devbox_core.config import (
        IDLE_TIMEOUT_SECONDS,
        OPENCODE_IDLE_TIMEOUT_SECONDS,
        RDP_PASSWORD,
        RDP_PORT,
        RDP_USER,
    )

    names, profiles = resolve_htb_networks(network)
    vpn_secrets = _require_vpn_secrets(profiles)
    labels = ", ".join(profile["label"] for profile in profiles)

    idle_timeout = OPENCODE_IDLE_TIMEOUT_SECONDS if forensic else IDLE_TIMEOUT_SECONDS
    exposed_ports = [22, 4096, RDP_PORT] if forensic else [22]
    sandbox = modal.Sandbox.create(
        "sleep",
        "infinity",
        app=modal.App.lookup("personal-devbox-launcher", create_if_missing=True),
        image=image,
        runtime="vm",
        secrets=[ssh_secret, *vpn_secrets],
        env={"DEVBOX_IDLE_TIMEOUT": str(idle_timeout)},
        volumes={"/data": volume},
        cpu=resources.get("cpu") if resources else None,
        memory=resources.get("memory") if resources else None,
        timeout=resources.get("timeout") if resources else None,
        unencrypted_ports=exposed_ports,
    )
    print(f"HTB network(s): {labels}")
    try:
        sandbox.filesystem.write_text(VM_SCRIPT, "/run/devbox-vm.sh")
        process = sandbox.exec(
            "sh",
            "/run/devbox-vm.sh",
            "forensic" if forensic else "standard",
            str(idle_timeout),
            ",".join(names),
        )
        tunnels = sandbox.tunnels(timeout=120)
        ssh_tunnel = tunnels[22]
        print(
            f"SSH: ssh root@{ssh_tunnel.unencrypted_host} "
            f"-p {ssh_tunnel.unencrypted_port} -t \"tmux attach -t devbox\""
        )
        if forensic:
            web_tunnel = tunnels[4096]
            print(
                f"OpenCode web: http://{web_tunnel.unencrypted_host}:"
                f"{web_tunnel.unencrypted_port}"
            )
            rdp_tunnel = tunnels[RDP_PORT]
            print(
                f"RDP: {rdp_tunnel.unencrypted_host}:{rdp_tunnel.unencrypted_port} "
                f"(username {RDP_USER}, password {RDP_PASSWORD})"
            )
        for line in process.stdout:
            print(line, end="")
        while process.poll() is None:
            time.sleep(5)
        exit_code = process.wait()
        stderr = process.stderr.read()
        if stderr:
            print(stderr, end="", file=__import__("sys").stderr)
        if exit_code != 0:
            raise RuntimeError(f"HTB VM Sandbox exited with status {exit_code}")
    finally:
        sandbox.terminate(wait=True)
