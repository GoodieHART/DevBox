import time

import modal

VM_SCRIPT = r'''#!/bin/sh
set -eu
mkdir -p /run/devbox
printf '%s' "$HTB_OVPN_CONFIG" > /run/devbox/htb.ovpn
chmod 600 /run/devbox/htb.ovpn
openvpn --config /run/devbox/htb.ovpn \
    --pull-filter ignore "ifconfig-ipv6" \
    --pull-filter ignore "route-ipv6" \
    --pull-filter ignore "redirect-gateway ipv6" \
    --log /run/devbox/openvpn.log --daemon
for _ in $(seq 1 60); do
    if grep -q 'Initialization Sequence Completed' /run/devbox/openvpn.log 2>/dev/null; then
        break
    fi
    if grep -Eq 'AUTH_FAILED|Cannot open TUN|Exiting due to fatal error' /run/devbox/openvpn.log 2>/dev/null; then
        cat /run/devbox/openvpn.log >&2
        exit 1
    fi
    sleep 1
done
grep -q 'Initialization Sequence Completed' /run/devbox/openvpn.log
mkdir -p /root/.ssh /var/run/sshd
if [ -n "${PUBKEYS:-}" ]; then printf '%s\n' "$PUBKEYS" > /root/.ssh/authorized_keys; fi
if [ -n "${PUBKEY:-}" ]; then printf '%s\n' "$PUBKEY" > /root/.ssh/authorized_keys; fi
chmod 600 /root/.ssh/authorized_keys
/usr/sbin/sshd
tmux new-session -d -s devbox -n window-1 2>/dev/null || true
tmux new-window -t devbox -n window-2 2>/dev/null || true
tmux new-window -t devbox -n window-3 2>/dev/null || true
if [ "$1" = "forensic" ]; then
    mkdir -p /data/forensics /data/forensics/uploads
    cd /data/forensics
    opencode web --port 4096 --hostname 0.0.0.0 >/run/devbox/opencode.log 2>&1 &
    if ! sh /run/devbox-vnc.sh; then
        printf 'noVNC browser failed to start; see /data/devbox-vnc/logs\n' >&2
    fi
fi
idle_seconds=0
idle_interval=15
idle_timeout=${2:?idle timeout is required}
printf 'HTB VPN connected. Idle timeout: %ss.\n' "$idle_timeout"
while [ "$idle_seconds" -lt "$idle_timeout" ]; do
    sleep "$idle_interval"
    active=0
    if pgrep -f 'sshd: root@' >/dev/null 2>&1; then
        active=1
    fi
    if [ "$1" = "forensic" ] && curl -fsS --max-time 2 http://127.0.0.1:4096/ >/dev/null 2>&1; then
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


def run_htb_vm(image, volume, ssh_secret, *, forensic=False, resources=None):
    from devbox_core.config import IDLE_TIMEOUT_SECONDS, NOVNC_PORT, OPENCODE_IDLE_TIMEOUT_SECONDS

    idle_timeout = OPENCODE_IDLE_TIMEOUT_SECONDS if forensic else IDLE_TIMEOUT_SECONDS
    htb_secret = modal.Secret.from_name("htb-vpn", required_keys=["HTB_OVPN_CONFIG"])
    sandbox = modal.Sandbox.create(
        "sleep",
        "infinity",
        app=modal.App.lookup("personal-devbox-launcher", create_if_missing=True),
        image=image,
        runtime="vm",
        secrets=[ssh_secret, htb_secret],
        env={"DEVBOX_IDLE_TIMEOUT": str(idle_timeout)},
        volumes={"/data": volume},
        cpu=resources.get("cpu") if resources else None,
        memory=resources.get("memory") if resources else None,
        timeout=resources.get("timeout") if resources else None,
        unencrypted_ports=[22, 4096] if forensic else [22],
    )
    try:
        sandbox.filesystem.write_text(VM_SCRIPT, "/run/devbox-vm.sh")
        if forensic:
            # Import locally: runtime.htb_vm is packaged into every image, but
            # the browser module and its packages only ship in the forensic image.
            from runtime.vnc_browser import VNC_BROWSER_SCRIPT

            sandbox.filesystem.write_text(VNC_BROWSER_SCRIPT, "/run/devbox-vnc.sh")
        process = sandbox.exec(
            "sh",
            "/run/devbox-vm.sh",
            "forensic" if forensic else "standard",
            str(idle_timeout),
        )
        tunnels = sandbox.tunnels(timeout=120)
        ssh_tunnel = tunnels[22]
        forward = (
            f" -L {NOVNC_PORT}:127.0.0.1:{NOVNC_PORT}" if forensic else ""
        )
        print(
            f"SSH: ssh root@{ssh_tunnel.unencrypted_host} "
            f"-p {ssh_tunnel.unencrypted_port}{forward} -t \"tmux attach -t devbox\""
        )
        if forensic:
            print(
                f"Browser: http://127.0.0.1:{NOVNC_PORT}/vnc.html"
                "?autoconnect=1&resize=scale"
            )
            web_tunnel = tunnels[4096]
            print(
                f"OpenCode web: http://{web_tunnel.unencrypted_host}:"
                f"{web_tunnel.unencrypted_port}"
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
