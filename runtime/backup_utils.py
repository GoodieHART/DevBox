"""
Backup utilities for DevBox applications.

Provides configurable backup functionality for different directories and use cases.
"""

import subprocess
import sys
import atexit


def create_backup(source_dir="/root", backup_file=None, exclude_patterns=None):
    """
    Create a compressed backup of specified directory.
    
    Args:
        source_dir (str): Directory to backup (default: "/root")
        backup_file (str): Output backup file path (auto-generated if None)
        exclude_patterns (list): Patterns to exclude from backup
    """
    if backup_file is None:
        if source_dir == "/root":
            backup_file = "/data/root_full_backup.tar.gz"
        elif "unsloth" in source_dir:
            backup_file = "/data/llama_backup.tar.gz"
        else:
            backup_file = f"/data/{source_dir.replace('/', '_')}_backup.tar.gz"
    
    if exclude_patterns is None:
        exclude_patterns = ["lost+found"]  # System directory
    
    try:
        print(f"Creating backup of {source_dir}...", file=sys.stderr)
        
        # Build tar command
        tar_cmd = ["tar", "-czf", backup_file]
        for pattern in exclude_patterns:
            tar_cmd.extend(["--exclude", pattern])
        tar_cmd.extend(["-C", source_dir, "."])
        
        # Execute backup
        subprocess.run(tar_cmd, check=True, capture_output=True)
        
        print(f"Backup saved to {backup_file}", file=sys.stderr)
        return backup_file
        
    except Exception as e:
        print(f"Warning: Backup failed - {e}", file=sys.stderr)
        return None


def register_root_backup():
    """Register root backup function to run on exit."""
    atexit.register(lambda: create_backup("/root"))


def register_llama_backup():
    """Register llama backup function to run on exit."""
    atexit.register(lambda: create_backup("/opt/models/unsloth", "/data/llama_backup.tar.gz"))


def register_custom_backup(source_dir, backup_file=None, exclude_patterns=None):
    """
    Register custom backup function to run on exit.
    
    Args:
        source_dir (str): Directory to backup
        backup_file (str): Output backup file path (optional)
        exclude_patterns (list): Patterns to exclude (optional)
    """
    backup_func = lambda: create_backup(source_dir, backup_file, exclude_patterns)
    atexit.register(backup_func)


def restore_backup(backup_file="/data/root_full_backup.tar.gz", restore_dir="/"):
    """
    Restore previous session backup if available.
    
    Args:
        backup_file: Path to backup file
        restore_dir: Directory to restore to (default: /)
    """
    import os
    import subprocess
    
    if os.path.exists(backup_file):
        print("Restoring previous session data...", file=sys.stderr)
        try:
            # Clean restore directory (preserve only essential system files)
            subprocess.run([
                "find", "/root", "-mindepth", "1", "-maxdepth", "1",
                "!", "-name", "lost+found",
                "-exec", "rm", "-rf", "{}", "+"
            ], check=False)
            
            # Extract backup
            subprocess.run(["tar", "-xzf", backup_file, "-C", restore_dir], check=True)
            print("Session data restored successfully!", file=sys.stderr)
            
        except Exception as e:
            print(f"Warning: Restore failed - {e}, continuing with clean environment", file=sys.stderr)
            