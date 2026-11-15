"""
Shared runtime logic for DevBox Launcher.

This module provides common runtime functionality used across different
DevBox types, including persistence setup, backup handling, and idle monitoring.

Author: GoodieHART
"""

import modal
import os
import shutil
import subprocess
import sys
import time
import atexit
import contextlib
from runtime.persistence_utils import setup_persistence, get_persistence_items
from runtime.backup_utils import restore_backup, register_custom_backup
from runtime.utils import inject_ssh_key
from devbox_core.config import IDLE_TIMEOUT_SECONDS, OPENCODE_PORT, validate_prohibited_packages
from ui.quotes_loader import get_random_quote
from runtime.cost_tracker import start_session, register_cost_flush, checkpoint


# Debian's /etc/xrdp/startwm.sh execs /etc/X11/Xsession, which only honors
# ~/.xsession when it is executable, so the runtime reinstalls it on each launch.
XSESSION_LAUNCHER = "/usr/local/bin/startxfce4-wrapper"

# RDP color-depth presets.  Lower values reduce bandwidth at the cost of
# color fidelity; the RDP client can still choose a smaller value.
RDP_QUALITY_PRESETS = {
    "low": 16,
    "medium": 24,
    "balanced": 24,
    "high": 32,
    "auto": 32,
}
RDP_RECOMMENDED_RESOLUTIONS = {
    "low": "800x600 or 1024x768",
    "medium": "1024x768 or 1280x720",
    "balanced": "1024x768 or 1280x720",
    "high": "your native display resolution",
    "auto": "your native display resolution",
}

# Processes that only exist while somebody is using the desktop: xrdp's
# per-session channel server and the XFCE session itself. The xrdp and
# xrdp-sesman daemons run all the time, so they are not activity signals.
RDP_SESSION_PATTERN = "xrdp-chansrv|xfce4-session"

# Persisted RDP dotfiles and desktop state. `.xsession` is the session launcher,
# not user state: a persisted copy is empty and non-executable, and Xsession then
# starts no desktop.
RDP_DESKTOP_ITEMS = [
    ".bash_history", ".bashrc", ".profile", ".viminfo", ".vimrc",
    ".gitconfig", ".ssh/config", ".ssh/known_hosts",
    ".config/xfce4", ".local/share/xfce4", ".cache/sessions",
    "Desktop",
]


def _resolve_rdp_max_bpp(rdp_quality="auto", rdp_max_bpp=None):
    """Resolve an xrdp max_bpp value from a quality preset or explicit value."""
    if rdp_max_bpp is not None:
        try:
            value = int(rdp_max_bpp)
        except (TypeError, ValueError) as error:
            raise ValueError(f"invalid RDP max_bpp value: {rdp_max_bpp!r}") from error
        if value in (8, 15, 16, 24, 32):
            return value
        # xrdp only supports a small fixed set of color depths.
        return min((8, 15, 16, 24, 32), key=lambda candidate: abs(candidate - value))

    env_value = os.environ.get("RDP_MAX_BPP")
    if env_value is not None:
        try:
            value = int(env_value)
        except ValueError as error:
            raise ValueError(f"invalid RDP_MAX_BPP value: {env_value!r}") from error
        if value in (8, 15, 16, 24, 32):
            return value
        return min((8, 15, 16, 24, 32), key=lambda candidate: abs(candidate - value))

    quality = str(os.environ.get("RDP_QUALITY", rdp_quality)).strip().lower()
    return RDP_QUALITY_PRESETS.get(quality, 32)


def _configure_xrdp_quality(max_bpp):
    """Apply the resolved color depth to xrdp's configuration."""
    config_path = "/etc/xrdp/xrdp.ini"
    if not os.path.isfile(config_path):
        return

    with open(config_path, "r", encoding="utf-8") as handle:
        lines = handle.readlines()

    replaced = False
    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("max_bpp=") or stripped.startswith("max_bpp ="):
            lines[index] = f"max_bpp={max_bpp}\n"
            replaced = True
            break

    if not replaced:
        for index, line in enumerate(lines):
            if line.strip() == "[Globals]":
                lines.insert(index + 1, f"max_bpp={max_bpp}\n")
                break
        else:
            lines.insert(0, f"max_bpp={max_bpp}\n")

    with open(config_path, "w", encoding="utf-8") as handle:
        handle.writelines(lines)


def install_xsession_launcher(home: str = "/root") -> None:
    """Write an executable `~/.xsession` that starts the XFCE wrapper.

    `restore_backup()` wipes `/root` and `setup_persistence()` owns the paths it
    links, so the launcher is reinstalled after both on every launch.
    """
    path = os.path.join(home, ".xsession")
    if os.path.islink(path):
        os.remove(path)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(f"#!/bin/sh\nexec {XSESSION_LAUNCHER}\n")
    os.chmod(path, 0o755)
    print(f"  - Installed {path} -> {XSESSION_LAUNCHER}", file=sys.stderr)


DESKTOP_SHORTCUTS = ("ghidra", "jadx-gui")


def install_desktop_shortcuts(
    home: str = "/root", source_dir: str = "/usr/share/applications"
) -> None:
    """Copy the tool shortcuts into the desktop directory.

    `~/Desktop` is linked onto the persistence volume, which hides the copies
    baked into the image, so they are reinstalled on every launch.
    """
    desktop = os.path.join(home, "Desktop")
    os.makedirs(desktop, exist_ok=True)
    for name in DESKTOP_SHORTCUTS:
        source = os.path.join(source_dir, f"{name}.desktop")
        if not os.path.isfile(source):
            continue
        target = os.path.join(desktop, f"{name}.desktop")
        shutil.copyfile(source, target)
        os.chmod(target, 0o755)


def count_rdp_sessions() -> int | None:
    """How many live RDP session processes exist (0 when nobody is connected).

    `pgrep` never reports its own command line, which is why it is used instead
    of `ps | grep`: a grep pipeline matches the pattern in its own argv and so
    always reports at least one session.

    Returns `None` when the probe itself failed, which is distinct from "no
    session": treating a broken probe as 0 would shut the desktop down under an
    active user.
    """
    try:
        result = subprocess.run(
            ["pgrep", "-c", "-f", RDP_SESSION_PATTERN],
            capture_output=True,
            text=True,
        )
    except OSError as error:
        print(f"  - WARNING: RDP session probe failed: {error}", file=sys.stderr)
        return None
    try:
        return int(result.stdout.strip() or 0)
    except ValueError:
        return None


def count_web_clients(port: int = OPENCODE_PORT) -> int | None:
    """How many clients hold a connection to the OpenCode port.

    The server answers `/` whether or not anyone is watching, so a 200 response
    proves nothing. An open tab keeps an SSE connection established, which this
    counts. Returns `None` when the probe itself failed, so a broken `ss` never
    shuts the box down under a user.
    """
    try:
        result = subprocess.run(
            ["ss", "-Htn", "state", "established", f"sport = :{port}"],
            capture_output=True,
            text=True,
        )
    except OSError as error:
        print(f"  - WARNING: OpenCode client probe failed: {error}", file=sys.stderr)
        return None
    if result.returncode != 0:
        return None
    return len([line for line in result.stdout.splitlines() if line.strip()])


def prepare_xfce_session() -> None:
    """Start D-Bus and create the state directories an xrdp/XFCE login needs.

    Runs after `setup_persistence()` and only ensures the `/root` config dirs,
    so the persisted symlinks survive.
    """
    os.makedirs("/run/dbus", exist_ok=True)
    # A stale pid file makes a forked system bus refuse to start in a reused
    # container image.
    subprocess.run(
        ["rm", "-f", "/run/dbus/pid", "/run/dbus/system_bus_socket"],
        check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    subprocess.Popen(
        ["dbus-daemon", "--system", "--fork"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    subprocess.run(["mkdir", "-p", "/root/.config/xfce4"], check=True)
    subprocess.run(["mkdir", "-p", "/root/.cache/sessions"], check=True)
    subprocess.run(["chown", "-R", "root:root", "/root/.config"], check=False)
    subprocess.run(["chown", "-R", "root:root", "/root/.cache"], check=False)

    os.environ.setdefault("XDG_CONFIG_DIRS", "/etc/xdg")
    os.environ.setdefault("XDG_DATA_DIRS", "/usr/local/share:/usr/share")
    os.environ.setdefault("XDG_RUNTIME_DIR", "/tmp/xdg-runtime")
    os.makedirs("/tmp/xdg-runtime", exist_ok=True)
    os.chmod("/tmp/xdg-runtime", 0o700)


def start_rdp_services() -> None:
    """Start xrdp and its session manager for a running desktop."""
    os.makedirs("/var/run/xrdp", exist_ok=True)
    subprocess.Popen(["/usr/sbin/xrdp"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.Popen(["/usr/sbin/xrdp-sesman"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def print_rdp_connection(tunnel) -> None:
    """Print the RDP address and static credentials for a Modal tunnel."""
    from devbox_core.config import RDP_PASSWORD, RDP_USER

    print("\n" + "=" * 60)
    print("🖥️ Your RDP Desktop is ready!")
    print("=" * 60)
    print(f"\n📡 RDP Address: {tunnel.host}:{tunnel.unencrypted_port}")
    print(f"👤 Username: {RDP_USER}")
    print(f"🔑 Password: {RDP_PASSWORD}")
    print("\n" + "=" * 60)


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
    "cuda_devbox_l40s": ("🎮", "CUDA DevBox (L40S)"),
    "assisted_coding": ("🤖", "AI Assistants Box"),
    "opencode": ("🤖", "OpenCode Box"),
    "llm_playroom": ("🧠", "LLM Playroom"),
    "forensic_analysis": ("🔍", "Forensics Analysis Box"),
    "rdp_devbox": ("🖥️", "RDP Desktop Box"),
    "llamacpp_cpu": ("🔬", "llama.cpp Research Center"),
    "llamacpp_gpu": ("🔬", "llama.cpp Research Center"),
}


# The login banner every DevBox type shows. `/etc/profile.d/devbox-banner.sh`
# prints it for interactive bash shells, and `/etc/devbox/zshrc` prints it for
# zsh.
BANNER_PATH = "/etc/devbox-banner"


def current_box_name():
    """The DevBox identity recorded for this container, or None.

    Only the HTB VM boxes write a name file; the Function-based boxes have no
    identity and therefore show no name row.
    """
    try:
        from devbox_core.box_identity import read_name_file

        return read_name_file()
    except Exception:
        return None


def format_banner(devbox_type, extra_lines=(), name=None, quote=True):
    """Render the login banner: header, rows, and a random quote when found.

    The box is drawn by `devbox_core.box_identity.banner_text`, so every box
    type shares one format. `name` adds a name row and is None for a box that
    has no identity.
    """
    from devbox_core.box_identity import banner_text

    icon, title = DEVBOX_BANNERS.get(devbox_type, ("🚀", "DevBox"))
    rows = ["💾 Persistent: /data", *extra_lines]
    banner = banner_text(name, icon, title, rows)
    if quote:
        try:
            quote_data = get_random_quote()
            banner += f"\n{quote_data['text']}\n- {quote_data['author']}\n"
        except Exception:
            pass  # Quotes are optional; the header still renders.
    return banner


def write_banner_file(devbox_type, extra_lines=(), name=None, quote=True,
                      path=BANNER_PATH):
    """Write the login banner to disk. Never raises."""
    try:
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(format_banner(devbox_type, extra_lines, name=name,
                                       quote=quote))
    except Exception as error:
        print(f"⚠️ could not write the DevBox banner: {error}", file=sys.stderr)
        return None
    return path


TMUX_SESSION_SCRIPT = "/usr/local/bin/devbox-tmux"


def start_tmux_session(session_name="devbox", windows=3):
    """Create the detached `session_name` tmux session via the baked helper.

    The HTB VM entrypoint runs the same script, so config, window names, and
    mouse support stay identical across boxes. Best-effort: on failure the
    DevBox still works over plain SSH.
    """
    import subprocess
    import sys

    try:
        result = subprocess.run(
            [TMUX_SESSION_SCRIPT, session_name, str(windows)],
            capture_output=True,
            text=True,
        )
    except OSError as error:
        print(
            f"⚠️ tmux helper unavailable ({error}) — skipping tmux session.",
            file=sys.stderr,
        )
        return

    warnings = (result.stderr or "").strip()
    if result.returncode != 0:
        detail = warnings or f"exit {result.returncode}"
        print(f"⚠️ tmux session setup failed: {detail}", file=sys.stderr)
        return

    for line in warnings.splitlines():
        print(line, file=sys.stderr)
    print(f"✅ tmux session '{session_name}' ready ({windows} windows)", file=sys.stderr)


def run_devbox_shared(extra_packages=None, devbox_type="ssh", resources=None):
    """Single consolidated function for all SSH DevBoxes."""
    import os
    import subprocess

    restore_backup()
    
    setup_persistence(get_persistence_items(devbox_type))

    if devbox_type == "assisted_coding":
        seed_opencode_config()
    
    # Register backup on exit
    register_custom_backup("/root", "/data/root_full_backup.tar.gz")

    # Cost tracking: one record per launch (best-effort, never blocks startup)
    try:
        _ct_session = start_session(devbox_type, resources)
        register_cost_flush(_ct_session)
    except Exception as _e:
        print(f"[cost_tracker] init failed: {_e}", file=sys.stderr)

    inject_ssh_key()

    # Write devbox banner with quote
    write_banner_file(devbox_type, name=current_box_name())

    install_extra_packages(extra_packages)
    
    # Start SSH and monitor
    subprocess.run(["/usr/sbin/sshd"])

    # Launch a tmux session (3 windows) users can attach to.
    start_tmux_session()

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
        print(f"\n🚀 Your DevBox is ready!\nssh root@{ssh_tunnel.host} -p {ssh_tunnel.unencrypted_port} -t \"tmux attach -t devbox\"")

        if devbox_type == "assisted_coding" and oc_web_proc is not None:
            web_tunnel = tunnels.enter_context(modal.forward(OPENCODE_PORT, unencrypted=True))
            print(f"\n🌐 OpenCode web: http://{web_tunnel.host}:{web_tunnel.unencrypted_port}")
            print("   (Open in browser for the Web UI; unsecured — the tunnel URL is the only secret.)")
        
        idle_time = 0
        check_interval = 15
        while idle_time < IDLE_TIMEOUT_SECONDS:
            time.sleep(check_interval)
            try:
                checkpoint()
            except Exception:
                pass
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


def run_rdp_devbox_shared(extra_packages=None, devbox_type="rdp_devbox", resources=None,
                          rdp_quality="auto", rdp_max_bpp=None):
    """
    Shared logic for launching an RDP desktop development environment.
    Sets up public key, persistent dotfiles, installs packages, and runs RDP server.
    """
    import time
    
    from runtime.backup_utils import restore_backup, register_custom_backup
    from runtime.persistence_utils import setup_persistence
    from runtime.utils import inject_ssh_key
    from devbox_core.config import IDLE_TIMEOUT_SECONDS
    
    restore_backup()
    
    inject_ssh_key()
    
    setup_persistence(RDP_DESKTOP_ITEMS)
    install_xsession_launcher()

    # Cargo is absent from this image, and a persisted profile that sources
    # ~/.cargo/env aborts /etc/xrdp/startwm.sh before XFCE can start.
    for shell_profile in (".profile", ".bashrc"):
        profile_path = os.path.join("/root", shell_profile)
        if os.path.isfile(profile_path):
            with open(profile_path, "r", encoding="utf-8") as handle:
                lines = handle.readlines()
            cleaned = [line for line in lines if ".cargo/env" not in line]
            if cleaned != lines:
                with open(profile_path, "w", encoding="utf-8") as handle:
                    handle.writelines(cleaned)

    register_custom_backup("/root", "/data/root_full_backup.tar.gz")

    # Cost tracking: one record per launch (best-effort)
    try:
        _ct_session = start_session(devbox_type, resources)
        register_cost_flush(_ct_session)
    except Exception as _e:
        print(f"[cost_tracker] init failed: {_e}", file=sys.stderr)

    # Login banner for the desktop box, written before the desktop services
    # come up. The RDP box runs as a Modal Function, so it has no identity.
    write_banner_file("rdp_devbox", ["🖥️  RDP on :3389"], name=current_box_name())

    install_extra_packages(extra_packages)

    prepare_xfce_session()

    # Apply the requested RDP color-depth preset before xrdp starts.  RDP
    # resolution itself is negotiated by the client, so the server-side knob is
    # max_bpp; the recommended client settings are printed below.
    resolved_rdp_quality = str(os.environ.get("RDP_QUALITY", rdp_quality)).strip().lower()
    resolved_max_bpp = _resolve_rdp_max_bpp(rdp_quality, rdp_max_bpp)
    _configure_xrdp_quality(resolved_max_bpp)
    print(f"[RDP] Quality preset: {resolved_rdp_quality} "
          f"(max_bpp={resolved_max_bpp})", file=sys.stderr)
    print(f"[RDP] Recommended client resolution: "
          f"{RDP_RECOMMENDED_RESOLUTIONS.get(resolved_rdp_quality, 'your native display resolution')}",
          file=sys.stderr)
    print("[RDP] Also set the mstsc color depth to match or below the server max_bpp.",
          file=sys.stderr)

    start_rdp_services()

    from devbox_core.config import RDP_PORT

    with modal.forward(RDP_PORT, unencrypted=True) as tunnel:
        print_rdp_connection(tunnel)
        
        idle_time = 0
        check_interval = 15
        
        while idle_time < IDLE_TIMEOUT_SECONDS:
            time.sleep(check_interval)
            try:
                checkpoint()
            except Exception:
                pass
            
            active_sessions = count_rdp_sessions()
            if active_sessions is None:
                # A failed probe is not idleness; the desktop would die under an
                # active user.
                print("[DEBUG] RDP session probe unavailable; not counting as idle.", file=sys.stderr)
            elif active_sessions > 0:
                idle_time = 0
                print(f"[DEBUG] RDP session check: {active_sessions} live session(s)", file=sys.stderr)
            else:
                idle_time += check_interval
                remaining = IDLE_TIMEOUT_SECONDS - idle_time
                print(f"[DEBUG] No active RDP connection. Shutting down in {remaining}s...", file=sys.stderr, end="\r")
        
        print("\nIdle timeout reached. Shutting down RDP Desktop.", file=sys.stderr)


def run_opencode_shared(extra_packages=None, resources=None, forensic=False):
    """Run the OpenCode box: SSH plus an `opencode web` server.

    Same provisioning as the SSH boxes, then sshd and the web server. SSH, web,
    and (on the forensics box) RDP activity reset the idle timer.
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
        RDP_PORT,
    )
    restore_backup()

    persistence_items = get_persistence_items("forensic_analysis" if forensic else "opencode")
    if forensic:
        # The forensics box also runs the xrdp/XFCE desktop, so it persists both
        # states. dict.fromkeys de-duplicates without reordering.
        persistence_items = list(dict.fromkeys(persistence_items + RDP_DESKTOP_ITEMS))
    setup_persistence(persistence_items)
    if forensic:
        install_xsession_launcher()
        install_desktop_shortcuts()
    seed_opencode_config()

    # Cargo is absent from this image, and a persisted profile that sources
    # ~/.cargo/env aborts /etc/xrdp/startwm.sh before XFCE can start. An older
    # profile can also put /opt/jadx/bin ahead of the JAVA_HOME wrappers.
    if forensic:
        for shell_profile in (".profile", ".bashrc"):
            profile_path = os.path.join("/root", shell_profile)
            if os.path.isfile(profile_path):
                with open(profile_path, "r", encoding="utf-8") as handle:
                    lines = handle.readlines()
                cleaned = [
                    line.replace("/opt/jadx/bin:", "").replace(":/opt/jadx/bin", "")
                    for line in lines
                    if ".cargo/env" not in line
                ]
                if cleaned != lines:
                    with open(profile_path, "w", encoding="utf-8") as handle:
                        handle.writelines(cleaned)

    # Register backup on exit (same target as SSH boxes)
    register_custom_backup("/root", "/data/root_full_backup.tar.gz")

    # Cost tracking: one record per launch (best-effort)
    try:
        _ct_session = start_session("forensic_analysis" if forensic else "assisted_coding", resources)
        register_cost_flush(_ct_session)
    except Exception as _e:
        print(f"[cost_tracker] init failed: {_e}", file=sys.stderr)

    inject_ssh_key()

    # Write devbox banner (same mechanism as run_devbox_shared)
    extra_lines = ()
    if forensic:
        extra_lines = ("🌐 OpenCode web on :4096", "🖥️ RDP desktop on :3389")
    write_banner_file(
        "forensic_analysis" if forensic else "assisted_coding",
        extra_lines,
        name=current_box_name(),
    )

    install_extra_packages(extra_packages)

    # Root OpenCode in a dedicated persistent dir on the volume (created if
    # missing) and seed a git repo with an initial commit so OpenCode resolves
    # a real project id instead of falling back to "global" (worktree "/").
    workdir = OPENCODE_SESSIONS_DIR
    uploads_dir = OPENCODE_UPLOADS_DIR
    if forensic:
        from devbox_core.config import FORENSICS_WORKDIR, FORENSICS_UPLOADS_DIR
        workdir = FORENSICS_WORKDIR
        uploads_dir = FORENSICS_UPLOADS_DIR
    os.makedirs(workdir, exist_ok=True)
    if not os.path.isdir(os.path.join(workdir, ".git")):
        subprocess.run(["git", "init", "-q", workdir], check=False)
        subprocess.run(
            [
                "git", "-C", workdir,
                "-c", "user.email=devbox@localhost", "-c", "user.name=devbox",
                "commit", "-q", "--allow-empty", "-m", "init oc-sessions",
            ],
            check=False,
        )

    # Dedicated persistent uploads dir for user-supplied files (e.g. targets for
    # the REA MCP). Lives on the volume, so it survives relaunches.
    os.makedirs(uploads_dir, exist_ok=True)

    _rea_marker = "# devbox rea env"
    if forensic:
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
                _f.write("export PATH=/opt/java/temurin-21/bin:$PATH\n")
      except Exception:
          pass

      os.environ.setdefault("JAVA_HOME", "/opt/java/temurin-21")
      os.environ.setdefault("GHIDRA_INSTALL_DIR", f"/opt/ghidra/ghidra_{GHIDRA_VERSION}_PUBLIC")
      os.environ.setdefault("REA_GHIDRA_STARTUP_TIMEOUT_MS", "120000")
      os.environ.setdefault("REA_MCP_MAX_RESPONSE_BYTES", "52428800")
      os.environ.setdefault("REA_JADX_MCP_JAR", f"/opt/jadx-headless-mcp/jadx-headless-mcp-{JADX_HEADLESS_MCP_VERSION}-all.jar")

    password = os.environ.get("OPENCODE_SERVER_PASSWORD", "")
    auth_note = "🔒 Password auth: enabled" if password else "⚠️ No OPENCODE_SERVER_PASSWORD set — tunnel URL is the only secret"

    # Start SSH (same as SSH boxes)
    subprocess.run(["/usr/sbin/sshd"])

    # Launch a tmux session (3 windows) users can attach to.
    start_tmux_session()

    # Start OpenCode web server in background, rooted at /data so sessions persist
    server_cmd = [
        "opencode", "web",
        "--port", str(OPENCODE_PORT),
        "--hostname", OPENCODE_HOSTNAME,
    ]
    try:
        server_proc = subprocess.Popen(
            server_cmd,
            cwd=workdir,
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

    # Desktop only for the forensics box; the AI Coding box stays headless.
    if forensic:
        prepare_xfce_session()
        forensic_max_bpp = _resolve_rdp_max_bpp("auto", None)
        _configure_xrdp_quality(forensic_max_bpp)
        start_rdp_services()
        print(
            f"[RDP] Forensics desktop ready (max_bpp={forensic_max_bpp}).",
            file=sys.stderr,
        )

    # ExitStack keeps every tunnel open for the whole session; leaving a `with`
    # block closes it. RDP is forwarded only when the desktop runs.
    with contextlib.ExitStack() as tunnels:
        ssh_tunnel = tunnels.enter_context(modal.forward(22, unencrypted=True))
        web_tunnel = tunnels.enter_context(modal.forward(OPENCODE_PORT, unencrypted=True))
        rdp_tunnel = (
            tunnels.enter_context(modal.forward(RDP_PORT, unencrypted=True))
            if forensic else None
        )

        ssh_cmd = f"ssh root@{ssh_tunnel.host} -p {ssh_tunnel.unencrypted_port} -t \"tmux attach -t devbox\""
        web_url = f"http://{web_tunnel.host}:{web_tunnel.unencrypted_port}"
        print("\n" + "=" * 60)
        print("🤖 Your OpenCode Box is ready!")
        print("=" * 60)
        print(f"\n🌐 OpenCode web: {web_url}")
        print(f"   (Open in browser; attach TUI via SSH with `opencode attach {web_url}`)")
        print(f"\n🔐 SSH: {ssh_cmd}")
        print(f"📁 Workdir: {workdir} (persistent)")
        if rdp_tunnel is not None:
            print_rdp_connection(rdp_tunnel)
        activity = "SSH, an open OpenCode tab, or RDP" if forensic else "SSH or an open OpenCode tab"
        print(f"⏰ Idle timeout: {OPENCODE_IDLE_TIMEOUT_SECONDS // 60} minutes ({activity} activity resets it)")
        print(f"{auth_note}")
        print("\n" + "=" * 60)

        idle_time = 0
        check_interval = 15
        while idle_time < OPENCODE_IDLE_TIMEOUT_SECONDS:
            time.sleep(check_interval)
            try:
                checkpoint()
            except Exception:
                pass
            ssh_result = subprocess.run(
                "ps -ef | grep 'sshd: root@' | grep -v grep",
                shell=True, capture_output=True,
            )
            ssh_active = bool(ssh_result.stdout)
            # The web server answers requests with nobody attached, so count
            # connected clients instead of probing for a 200.
            web_clients = count_web_clients(OPENCODE_PORT)
            web_active = web_clients is None or web_clients > 0
            rdp_active = False
            if forensic:
                rdp_sessions = count_rdp_sessions()
                # A failed probe must not count as idle, or the desktop dies
                # under an active user.
                rdp_active = bool(rdp_sessions) or rdp_sessions is None
            active = ssh_active or web_active or rdp_active
            print(
                f"[DEBUG] OpenCode idle check: ssh={ssh_active} web={web_active} "
                f"clients={web_clients} rdp={rdp_active} idle={idle_time}s",
                file=sys.stderr,
            )
            if active:
                idle_time = 0
            else:
                idle_time += check_interval
                remaining = OPENCODE_IDLE_TIMEOUT_SECONDS - idle_time
                print(f"No activity. Shutting down in {remaining}s...", file=sys.stderr)

        print("\nIdle timeout reached. Shutting down.", file=sys.stderr)
    server_proc.terminate()
