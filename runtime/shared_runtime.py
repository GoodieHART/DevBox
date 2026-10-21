"""
Shared runtime logic for DevBox Launcher.

This module provides common runtime functionality used across different
DevBox types, including persistence setup, backup handling, and idle monitoring.

Author: GoodieHART
"""

import modal
import sys
import time
import atexit
import contextlib
import textwrap
from runtime.persistence_utils import setup_persistence, get_persistence_items
from runtime.backup_utils import restore_backup, register_custom_backup
from runtime.utils import inject_ssh_key
from devbox_core.config import IDLE_TIMEOUT_SECONDS, validate_prohibited_packages
from ui.quotes_loader import get_random_quote


def install_extra_packages(extra_packages: list[str] | None) -> None:
    """Install user-requested apt packages, after a denylist check.

    `extra_packages` arrives straight from the launcher, so it is the one path a
    prohibited package can take into a running DevBox. The check runs before
    `apt-get update` so a refused request fetches nothing.
    """
    import subprocess

    if not extra_packages:
        return

    validate_prohibited_packages(extra_packages)

    print(f"Installing extra packages: {', '.join(extra_packages)}...", file=sys.stderr)
    subprocess.run(["apt-get", "update"], check=True)
    subprocess.run(["apt-get", "install", "-y"] + extra_packages, check=True)


def seed_opencode_config(source_path="/etc/devbox/opencode.json"):
    import os
    import shutil

    target_path = "/root/.config/opencode/opencode.json"
    parent = os.path.dirname(target_path)
    if os.path.lexists(parent) and not os.path.isdir(parent):
        os.remove(parent)
    os.makedirs(parent, exist_ok=True)
    if os.path.exists(target_path) and os.path.getsize(target_path) > 0:
        return
    shutil.copyfile(source_path, target_path)

DEVBOX_BANNERS = {
    "standard_devbox": ("🛠️", "Standard DevBox"),
    "cuda_devbox_t4": ("🎮", "CUDA DevBox (T4)"),
    "cuda_devbox_l4": ("🎮", "CUDA DevBox (L4)"),
    "cuda_devbox_a10g": ("🎮", "CUDA DevBox (A10G)"),
    "doc_processing": ("📄", "Document Processing Box"),
    "assisted_coding": ("🤖", "AI Assistants Box"),
    "opencode": ("🤖", "OpenCode Box"),
    "llm_playroom": ("🧠", "LLM Playroom"),
    "forensic_analysis": ("🔍", "Forensics Analysis Box"),
}


def run_devbox_shared(extra_packages=None, devbox_type="ssh"):
    """Single consolidated function for all SSH DevBoxes."""
    import os
    import subprocess

    restore_backup()
    
    setup_persistence(get_persistence_items(devbox_type))

    if devbox_type == "assisted_coding":
        seed_opencode_config()
    
    # Register backup on exit
    register_custom_backup("/root", "/data/root_full_backup.tar.gz")
    
    inject_ssh_key()

    # Write devbox banner with quote
    icon, name = DEVBOX_BANNERS.get(devbox_type, ("🚀", "DevBox"))
    banner = textwrap.dedent(f"""\
    ╔══════════════════════════════════════╗
    ║  {icon} {name:<30} ║
    ║  {'💾 Persistent: /data':<36} ║
    ╚══════════════════════════════════════╝
    """)
    try:
        q = get_random_quote()
        banner += f"\n{q['text']}\n- {q['author']}\n"
    except Exception:
        pass  # Quotes are optional — banner still works without them
    with open("/etc/devbox-banner", "w") as f:
        f.write(banner)

    install_extra_packages(extra_packages)
    
    # Start SSH and monitor
    subprocess.run(["/usr/sbin/sshd"])

    # Assisted box: background `opencode web` so users get the Web UI
    # instead of the TUI (which stalls on minimal terminals). Non-fatal:
    # the SSH box must still work if the web server fails.
    import urllib.request
    from devbox_core.config import OPENCODE_HOSTNAME, OPENCODE_PORT, OPENCODE_WORKDIR
    oc_web_proc = None
    if devbox_type == "assisted_coding":
        os.makedirs(OPENCODE_WORKDIR, exist_ok=True)
        try:
            oc_web_proc = subprocess.Popen(
                ["opencode", "web", "--port", str(OPENCODE_PORT), "--hostname", OPENCODE_HOSTNAME],
                cwd=OPENCODE_WORKDIR,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except FileNotFoundError:
            print("⚠️ 'opencode' binary not found — skipping background web server.", file=sys.stderr)
        else:
            for _ in range(30):
                time.sleep(1)
                if oc_web_proc.poll() is not None:
                    print("⚠️ OpenCode web exited on startup — skipping.", file=sys.stderr)
                    oc_web_proc = None
                    break
                try:
                    with urllib.request.urlopen(f"http://127.0.0.1:{OPENCODE_PORT}/", timeout=2) as resp:
                        if resp.status < 500:
                            print(f"✅ OpenCode web ready on {OPENCODE_HOSTNAME}:{OPENCODE_PORT}", file=sys.stderr)
                            break
                except Exception:
                    continue
            else:
                print("⚠️ OpenCode web did not become ready in 30s — skipping.", file=sys.stderr)
                oc_web_proc.terminate()
                oc_web_proc = None
    
    # ExitStack keeps the SSH tunnel (and, for the assisted box, the OpenCode web
    # tunnel) alive for the whole session; the web tunnel is added conditionally
    # so other box types don't expose a port nothing is listening on.
    with contextlib.ExitStack() as tunnels:
        ssh_tunnel = tunnels.enter_context(modal.forward(22, unencrypted=True))
        print(f"\n🚀 Your DevBox is ready!\nssh root@{ssh_tunnel.host} -p {ssh_tunnel.unencrypted_port}")

        if devbox_type == "assisted_coding" and oc_web_proc is not None:
            web_tunnel = tunnels.enter_context(modal.forward(OPENCODE_PORT, unencrypted=True))
            print(f"\n🌐 OpenCode web: http://{web_tunnel.host}:{web_tunnel.unencrypted_port}")
            print("   (Open in browser for the Web UI; unsecured — the tunnel URL is the only secret.)")
        
        idle_time = 0
        check_interval = 15
        while idle_time < IDLE_TIMEOUT_SECONDS:
            time.sleep(check_interval)
            result = subprocess.run("ps -ef | grep 'sshd: root@' | grep -v grep", shell=True, capture_output=True)
            print(f"[DEBUG] SSH session check: {result.stdout!r}", file=sys.stderr)
            print(f"[DEBUG] Current idle time: {idle_time}s", file=sys.stderr)
            web_active = False
            if devbox_type == "assisted_coding" and oc_web_proc is not None and oc_web_proc.poll() is None:
                try:
                    with urllib.request.urlopen(f"http://127.0.0.1:{OPENCODE_PORT}/", timeout=2) as resp:
                        web_active = resp.status < 500
                except Exception:
                    pass
            if result.stdout or web_active:
                idle_time = 0
                print("[DEBUG] User Connected. Resetting idle timer.", file=sys.stderr)
            else:
                idle_time += check_interval
                remaining = IDLE_TIMEOUT_SECONDS - idle_time
                print(f"No active SSH connection. Shutting down in {remaining}s...", file=sys.stderr,)


def run_rdp_devbox_shared(extra_packages=None):
    """
    Shared logic for launching an RDP desktop development environment.
    Sets up public key, persistent dotfiles, installs packages, and runs RDP server.
    """
    import os
    import subprocess
    import time
    
    from runtime.backup_utils import restore_backup, register_custom_backup
    from runtime.persistence_utils import setup_persistence
    from runtime.utils import inject_ssh_key
    from devbox_core.config import IDLE_TIMEOUT_SECONDS
    
    restore_backup()
    
    inject_ssh_key()
    
    rdp_items = [
        ".bash_history", ".bashrc", ".profile", ".viminfo", ".vimrc",
        ".gitconfig", ".ssh/config", ".ssh/known_hosts",
        ".config/xfce4", ".local/share/xfce4", ".cache/sessions",
        "Desktop", ".xsession",
    ]
    setup_persistence(rdp_items)
    
    register_custom_backup("/root", "/data/root_full_backup.tar.gz")
    
    install_extra_packages(extra_packages)
    
    # Setup XFCE environment
    # Start D-Bus daemon for xfconfd
    subprocess.Popen(["dbus-daemon", "--system", "--fork"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    # Clean and recreate XFCE config directories
    subprocess.run(["rm", "-rf", "/root/.config/xfce4"], check=False)
    subprocess.run(["rm", "-rf", "/root/.cache/sessions"], check=False)
    subprocess.run(["mkdir", "-p", "/root/.config/xfce4"], check=True)
    subprocess.run(["mkdir", "-p", "/root/.cache/sessions"], check=True)
    
    # Set permissions
    subprocess.run(["chown", "-R", "root:root", "/root/.config"], check=False)
    subprocess.run(["chown", "-R", "root:root", "/root/.cache"], check=False)
    
    # XDG environment variables
    os.environ.setdefault('XDG_CONFIG_DIRS', '/etc/xdg')
    os.environ.setdefault('XDG_DATA_DIRS', '/usr/local/share:/usr/share')
    os.environ.setdefault('XDG_RUNTIME_DIR', '/tmp/xdg-runtime')
    os.makedirs('/tmp/xdg-runtime', exist_ok=True)
    os.chmod('/tmp/xdg-runtime', 0o700)
    
    # Start RDP services
    subprocess.Popen(["/usr/sbin/xrdp"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.Popen(["/usr/sbin/xrdp-sesman"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    with modal.forward(3389, unencrypted=True) as tunnel:
        print("\n" + "=" * 60)
        print("🖥️ Your RDP Desktop is ready!")
        print("=" * 60)
        print(f"\n📡 RDP Address: {tunnel.host}:{tunnel.unencrypted_port}")
        print("👤 Username: root")
        print("🔑 Password: devbox123")
        print("\n" + "=" * 60)
        
        idle_time = 0
        check_interval = 15
        
        while idle_time < IDLE_TIMEOUT_SECONDS:
            time.sleep(check_interval)
            
            # Check for active RDP sessions
            result = subprocess.run(
                "ps aux | grep -c 'xrdp-sesman.*:' | grep -v grep", shell=True, capture_output=True, text=True
            )
            # remeber to add debug logs to check the output of the command
            try:
                active_sessions = int(result.stdout.strip())
                if active_sessions > 0:
                    idle_time = 0
                    print(f"[DEBUG] RDP session check: {active_sessions} {result.stdout!r}", file=sys.stderr)
                else:
                    idle_time += check_interval
                    remaining = IDLE_TIMEOUT_SECONDS - idle_time
                    print(f"[DEBUG] No active RDP connection. Shutting down in {remaining}s...", file=sys.stderr, end="\r")
            except (ValueError, AttributeError):
                idle_time += check_interval
        
        print("\nIdle timeout reached. Shutting down RDP Desktop.", file=sys.stderr)


def run_opencode_shared(extra_packages=None):
    """Lifecycle for the dedicated OpenCode box: SSH + `opencode web` server.

    Keeps the exact same provisioning primitives as the SSH boxes
    (backup restore, persistence symlinks, SSH key injection, atexit backup)
    then starts sshd AND `opencode web --port 4096 --hostname 0.0.0.0` with
    workdir /data/oc-sessions. Both ports are forwarded; idle shutdown resets on either
    SSH activity or HTTP activity against the OpenCode server.
    """
    import os
    import subprocess
    import urllib.request

    from devbox_core.config import (
        OPENCODE_HOSTNAME,
        OPENCODE_IDLE_TIMEOUT_SECONDS,
        OPENCODE_PORT,
        OPENCODE_SESSIONS_DIR,
        OPENCODE_UPLOADS_DIR,
        GHIDRA_VERSION,
        JADX_HEADLESS_MCP_VERSION,
    )
    restore_backup()

    setup_persistence(get_persistence_items("opencode"))
    seed_opencode_config()

    # Register backup on exit (same target as SSH boxes)
    register_custom_backup("/root", "/data/root_full_backup.tar.gz")

    inject_ssh_key()

    # Write devbox banner (same mechanism as run_devbox_shared)
    icon, name = DEVBOX_BANNERS.get("opencode", ("🚀", "DevBox"))
    banner = textwrap.dedent(f"""\
    ╔══════════════════════════════════════╗
    ║  {icon} {name:<30} ║
    ║  {'💾 Persistent: /data':<36} ║
    ║  {'🌐 OpenCode web on :4096':<36} ║
    ╚══════════════════════════════════════╝
    """)
    try:
        q = get_random_quote()
        banner += f"\n{q['text']}\n- {q['author']}\n"
    except Exception:
        pass  # Quotes are optional — banner still works without them
    with open("/etc/devbox-banner", "w") as f:
        f.write(banner)

    install_extra_packages(extra_packages)

    # Root OpenCode in a dedicated persistent dir on the volume (created if
    # missing) and seed a git repo with an initial commit so OpenCode resolves
    # a real project id instead of falling back to "global" (worktree "/").
    os.makedirs(OPENCODE_SESSIONS_DIR, exist_ok=True)
    if not os.path.isdir(os.path.join(OPENCODE_SESSIONS_DIR, ".git")):
        subprocess.run(["git", "init", "-q", OPENCODE_SESSIONS_DIR], check=False)
        subprocess.run(
            [
                "git", "-C", OPENCODE_SESSIONS_DIR,
                "-c", "user.email=devbox@localhost", "-c", "user.name=devbox",
                "commit", "-q", "--allow-empty", "-m", "init oc-sessions",
            ],
            check=False,
        )

    # Dedicated persistent uploads dir for user-supplied files (e.g. targets for
    # the REA MCP). Lives on the volume, so it survives relaunches.
    os.makedirs(OPENCODE_UPLOADS_DIR, exist_ok=True)

    # REA reads absolute paths directly (there is no "roots approval" env
    # var), so /data/uploads and /data/oc-sessions are already reachable by
    # the `rea mcp` child. Persist REA's real env vars for SSH shells.
    _rea_marker = "# devbox rea env"
    try:
        _profile = "/root/.bashrc"
        _existing = open(_profile).read() if os.path.exists(_profile) else ""
        if _rea_marker not in _existing:
            with open(_profile, "a") as _f:
                _f.write("\n" + _rea_marker + "\n")
                _f.write("export JAVA_HOME=/opt/java/temurin-21\n")
                _f.write(f"export GHIDRA_INSTALL_DIR=/opt/ghidra/ghidra_{GHIDRA_VERSION}_PUBLIC\n")
                _f.write("export REA_GHIDRA_STARTUP_TIMEOUT_MS=120000\n")
                _f.write("export REA_MCP_MAX_RESPONSE_BYTES=52428800\n")
                _f.write(f"export REA_JADX_MCP_JAR=/opt/jadx-headless-mcp/jadx-headless-mcp-{JADX_HEADLESS_MCP_VERSION}-all.jar\n")
                _f.write("export PATH=/opt/java/temurin-21/bin:/opt/jadx/bin:$PATH\n")
    except Exception:
        pass

    # Ensure the `rea mcp` child (inherited env) sees the same values even
    # when /etc/profile.d/rea.sh was not sourced by this process.
    os.environ.setdefault("JAVA_HOME", "/opt/java/temurin-21")
    os.environ.setdefault("GHIDRA_INSTALL_DIR", f"/opt/ghidra/ghidra_{GHIDRA_VERSION}_PUBLIC")
    os.environ.setdefault("REA_GHIDRA_STARTUP_TIMEOUT_MS", "120000")
    os.environ.setdefault("REA_MCP_MAX_RESPONSE_BYTES", "52428800")
    os.environ.setdefault("REA_JADX_MCP_JAR", f"/opt/jadx-headless-mcp/jadx-headless-mcp-{JADX_HEADLESS_MCP_VERSION}-all.jar")

    password = os.environ.get("OPENCODE_SERVER_PASSWORD", "")
    auth_note = "🔒 Password auth: enabled" if password else "⚠️ No OPENCODE_SERVER_PASSWORD set — tunnel URL is the only secret"

    # Start SSH (same as SSH boxes)
    subprocess.run(["/usr/sbin/sshd"])

    # Start OpenCode web server in background, rooted at /data so sessions persist
    server_cmd = [
        "opencode", "web",
        "--port", str(OPENCODE_PORT),
        "--hostname", OPENCODE_HOSTNAME,
    ]
    try:
        server_proc = subprocess.Popen(
            server_cmd,
            cwd=OPENCODE_SESSIONS_DIR,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
    except FileNotFoundError:
        print(
            "❌ 'opencode' binary not found. The image install step or a stale "
            "session backup (/data/root_full_backup.tar.gz) may be at fault.",
            file=sys.stderr,
        )
        raise

    # Wait for server readiness (fail fast with a clear error instead of
    # printing a dead URL)
    ready = False
    for _ in range(30):
        time.sleep(1)
        if server_proc.poll() is not None:
            err = ""
            try:
                raw = server_proc.stderr.read() if server_proc.stderr else None
                err = (raw or b"").decode(errors="replace")[-2000:]
            except Exception:
                pass
            print(f"❌ OpenCode server exited on startup. {err}", file=sys.stderr)
            raise RuntimeError("OpenCode server failed to start — see stderr above")
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{OPENCODE_PORT}/", timeout=2) as resp:
                if resp.status < 500:
                    ready = True
                    break
        except Exception:
            continue
    if not ready:
        print("❌ OpenCode server did not become ready in 30s.", file=sys.stderr)
        server_proc.terminate()
        raise RuntimeError("OpenCode server did not become ready in time")

    print(f"✅ OpenCode web ready on {OPENCODE_HOSTNAME}:{OPENCODE_PORT}", file=sys.stderr)
    print(auth_note, file=sys.stderr)

    def _http_active():
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{OPENCODE_PORT}/", timeout=2) as resp:
                return resp.status < 500
        except Exception as e:
            print(f"[DEBUG] OpenCode health check failed: {e}", file=sys.stderr)
            return False

    # Nested tunnels keep BOTH alive for the whole session (exiting a `with`
    # block closes that tunnel — see llamacpp pattern which drops SSH early)
    with modal.forward(22, unencrypted=True) as ssh_tunnel:
        with modal.forward(OPENCODE_PORT, unencrypted=True) as web_tunnel:
            ssh_cmd = f"ssh root@{ssh_tunnel.host} -p {ssh_tunnel.unencrypted_port}"
            web_url = f"http://{web_tunnel.host}:{web_tunnel.unencrypted_port}"
            print("\n" + "=" * 60)
            print("🤖 Your OpenCode Box is ready!")
            print("=" * 60)
            print(f"\n🌐 OpenCode web: {web_url}")
            print("   (Open in browser; attach TUI via SSH with `opencode attach http://127.0.0.1:4096`)")
            print(f"\n🔐 SSH: {ssh_cmd}")
            print(f"📁 Workdir: {OPENCODE_SESSIONS_DIR} (persistent)")
            print(f"⏰ Idle timeout: {OPENCODE_IDLE_TIMEOUT_SECONDS // 60} minutes (SSH or web activity resets it)")
            print(f"{auth_note}")
            print("\n" + "=" * 60)

            idle_time = 0
            check_interval = 15
            while idle_time < OPENCODE_IDLE_TIMEOUT_SECONDS:
                time.sleep(check_interval)
                ssh_result = subprocess.run(
                    "ps -ef | grep 'sshd: root@' | grep -v grep",
                    shell=True, capture_output=True,
                )
                ssh_active = bool(ssh_result.stdout)
                # HTTP listener alone is NOT activity — only a successful
                # response resets the timer, so an idle-but-running server
                # still shuts down and saves cost.
                web_active = _http_active()
                active = ssh_active or web_active
                print(
                    f"[DEBUG] OpenCode idle check: ssh={ssh_active} web={web_active} idle={idle_time}s",
                    file=sys.stderr,
                )
                if active:
                    idle_time = 0
                else:
                    idle_time += check_interval
                    remaining = OPENCODE_IDLE_TIMEOUT_SECONDS - idle_time
                    print(f"No activity. Shutting down in {remaining}s...", file=sys.stderr)

            print("\nIdle timeout reached. Shutting down OpenCode Box.", file=sys.stderr)
    server_proc.terminate()
