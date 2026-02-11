"""
Shared runtime logic for DevBox Launcher.

This module provides common runtime functionality used across different
DevBox types, including persistence setup, backup handling, and idle monitoring.

Author: GoodieHART
"""

import os
import modal
import sys
import time
import subprocess
import atexit
from persistence_utils import setup_persistence, get_persistence_items
from backup_utils import *
from utils import *
from config import IDLE_TIMEOUT_SECONDS


def run_devbox_shared(extra_packages=None, devbox_type="ssh"):
    """Single consolidated function for all SSH DevBoxes."""
    import os
    import subprocess
    
    # 1. Restore backup
    restore_backup()
    
    # 2. Setup persistence
    setup_persistence(get_persistence_items(devbox_type))
    
    # 3. Register backup on exit
    register_custom_backup("/root", "/data/root_full_backup.tar.gz")
    
    # 4. Inject SSH key
    inject_ssh_key()
    
    # 5. Install extra packages
    if extra_packages:
        print(f"Installing extra packages: {', '.join(extra_packages)}...", file=sys.stderr)
        subprocess.run(["apt-get", "update"], check=True)
        subprocess.run(["apt-get", "install", "-y"] + extra_packages, check=True)
    
    # 6. Start SSH and monitor
    subprocess.run(["/usr/sbin/sshd"])
    
    with modal.forward(22, unencrypted=True) as tunnel:
        print(f"\n🚀 Your DevBox is ready!\nssh root@{tunnel.host} -p {tunnel.unencrypted_port}")
        
        idle_time = 0
        while idle_time < IDLE_TIMEOUT_SECONDS:
            time.sleep(15)
            result = subprocess.run("ps -ef | grep 'sshd: root@' | grep -v grep", 
                                  shell=True, capture_output=True)
            if result.stdout:
                idle_time = 0
            else:
                idle_time += 15


def run_rdp_devbox_shared(extra_packages: list[str] = None):
    """
    Shared logic for launching an RDP desktop development environment.
    Sets up public key, persistent dotfiles, installs packages, and runs RDP server.
    """
    import os
    import subprocess
    import time
    
    # Import utilities
    from backup_utils import restore_backup, register_custom_backup
    from persistence_utils import setup_persistence
    from utils import inject_ssh_key
    from config import IDLE_TIMEOUT_SECONDS
    
    # 1. Restore backup
    restore_backup()
    
    # 2. Inject SSH key (for fallback access)
    inject_ssh_key()
    
    # 3. Setup persistence with RDP-specific items
    rdp_items = [
        ".bash_history", ".bashrc", ".profile", ".viminfo", ".vimrc",
        ".gitconfig", ".ssh/config", ".ssh/known_hosts",
        ".config/xfce4", ".local/share/xfce4", ".cache/sessions",
        "Desktop", ".xsession",
    ]
    setup_persistence(rdp_items)
    
    # 4. Register backup
    register_custom_backup("/root", "/data/root_full_backup.tar.gz")
    
    # 5. Install extra packages
    if extra_packages:
        print(f"Installing extra packages: {', '.join(extra_packages)}...", file=sys.stderr)
        subprocess.run(["apt-get", "update"], check=True)
        subprocess.run(["apt-get", "install", "-y"] + extra_packages, check=True)
    
    # 6. Setup XFCE environment
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
    
    # 7. Start RDP services
    subprocess.Popen(["/usr/sbin/xrdp"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.Popen(["/usr/sbin/xrdp-sesman"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    # 8. Port forward and idle monitoring
    with modal.forward(3389, unencrypted=True) as tunnel:
        print(f"\n🖥️ Your RDP Desktop is ready!", file=sys.stderr)
        print(f"Address: {tunnel.host}:{tunnel.unencrypted_port}", file=sys.stderr)
        print(f"Username: root", file=sys.stderr)
        print(f"Password: rdpaccess", file=sys.stderr)
        
        idle_time = 0
        check_interval = 15
        
        while idle_time < IDLE_TIMEOUT_SECONDS:
            time.sleep(check_interval)
            
            # Check for active RDP sessions
            result = subprocess.run(
                "ps aux | grep -c 'xrdp-sesman.*:' | grep -v grep",
                shell=True, capture_output=True, text=True
            )
            
            try:
                active_sessions = int(result.stdout.strip())
                if active_sessions > 0:
                    idle_time = 0
                else:
                    idle_time += check_interval
                    remaining = IDLE_TIMEOUT_SECONDS - idle_time
                    print(f"No active RDP connection. Shutting down in {remaining}s...",
                          file=sys.stderr, end="\r")
            except (ValueError, AttributeError):
                idle_time += check_interval
        
        print(f"\nIdle timeout reached. Shutting down RDP Desktop.", file=sys.stderr)