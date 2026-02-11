"""
Shared runtime logic for DevBox Launcher.

This module provides common runtime functionality used across different
DevBox types, including persistence setup, backup handling, and idle monitoring.

Author: GoodieHART
"""

import os
import sys
import time
import subprocess
import atexit
from persistence_utils import setup_persistence, get_persistence_items
from backup_utils import create_backup, register_custom_backup
from config import IDLE_TIMEOUT_SECONDS


def setup_persistence_and_backup(persistence_items, backup_source="/root", backup_file=None):
    """
    Set up persistent storage and register backup for DevBox.
    
    Args:
        persistence_items: List of files/directories to persist
        backup_source: Directory to backup (default: "/root")
        backup_file: Output backup file path (auto-generated if None)
    """
    # Set up comprehensive persistent storage
    print("Setting up comprehensive persistence system...", file=sys.stderr)
    setup_persistence(persistence_items)
    
    # Register backup on exit
    register_custom_backup(backup_source, backup_file)
    
    print("✓ Persistence and backup systems configured", file=sys.stderr)


def setup_ssh_environment():
    """
    Set up SSH environment with key injection and configuration.
    
    Returns:
        bool: True if SSH setup successful, False otherwise
    """
    # Import here to avoid circular dependency
    from utils import inject_ssh_key
    
    print("🔐 Setting up SSH environment...", file=sys.stderr)
    
    # Inject SSH key with comprehensive diagnostics
    if not inject_ssh_key():
        print("❌ SSH setup failed - DevBox will not be accessible", file=sys.stderr)
        return False
    
    print("✓ SSH environment configured successfully", file=sys.stderr)
    return True


def install_extra_packages(extra_packages):
    """
    Install extra apt packages if specified.
    
    Args:
        extra_packages: List of packages to install (None or empty = no extra packages)
    """
    if extra_packages:
        print(f"📦 Installing extra packages: {', '.join(extra_packages)}", file=sys.stderr)
        try:
            subprocess.run(["apt-get", "update"], check=True)
            subprocess.run(["apt-get", "install", "-y"] + extra_packages, check=True)
            print("✓ Extra packages installed successfully", file=sys.stderr)
        except subprocess.CalledProcessError as e:
            print(f"❌ Package installation failed: {e}", file=sys.stderr)
            return False
    return True


def start_ssh_daemon():
    """
    Start SSH daemon with proper configuration.
    """
    print("🚀 Starting SSH daemon...", file=sys.stderr)
    
    # Start SSH daemon in background
    subprocess.Popen(["/usr/sbin/sshd", "-D"])
    
    print("✓ SSH daemon started", file=sys.stderr)
    print(f"📍 DevBox ready! SSH will auto-shutdown after {IDLE_TIMEOUT_SECONDS}s of inactivity", file=sys.stderr)


def monitor_idle_timeout(last_activity_time):
    """
    Monitor for idle timeout and shutdown when inactive.
    
    Args:
        last_activity_time: Timestamp of last SSH activity
    """
    current_time = time.time()
    idle_time = current_time - last_activity_time
    
    if idle_time > IDLE_TIMEOUT_SECONDS:
        print(f"⏰ Idle timeout reached ({idle_time:.0f}s). Shutting down...", file=sys.stderr)
        return True
    
    return False


def handle_devbox_startup(extra_packages, persistence_type="ssh", backup_source="/root"):
    """
    Common DevBox startup workflow.
    
    Args:
        extra_packages: Extra packages to install
        persistence_type: Type of persistence setup ("ssh", "rdp", "llm", etc.)
        backup_source: Source directory for backup
        
    Returns:
        bool: True if startup successful, False otherwise
    """
    print("🚀 Initializing DevBox environment...", file=sys.stderr)
    
    # Step 1: Set up SSH environment
    if not setup_ssh_environment():
        return False
    
    # Step 2: Install extra packages
    if not install_extra_packages(extra_packages):
        return False
    
    # Step 3: Set up persistence and backup
    persistence_items = get_persistence_items(persistence_type)
    setup_persistence_and_backup(persistence_items, backup_source)
    
    # Step 4: Start SSH daemon
    start_ssh_daemon()
    
    print("✓ DevBox initialization complete!", file=sys.stderr)
    return True


# Idle timeout monitoring for SSH connections
IDLE_TIMEOUT_SECONDS = IDLE_TIMEOUT_SECONDS