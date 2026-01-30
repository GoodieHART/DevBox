"""
Persistence utilities for DevBox applications.

Provides configurable persistent storage setup to eliminate code duplication.
"""

import os
import shutil


def setup_persistence(items_to_persist, persistent_storage_dir="/data/.config_persistence"):
    """
    Set up persistent dotfiles and configs using symbolic links.
    
    Args:
        items_to_persist (list): List of files/directories to persist
        persistent_storage_dir (str): Base directory for persistent storage
    """
    # --- Set up persistent dotfiles and desktop configs using symbolic links ---
    print("Linking persistent configuration files...", file=sys.stderr)
    
    os.makedirs(persistent_storage_dir, exist_ok=True)
    
    for item in items_to_persist:
        # Determine paths
        volume_path = os.path.join(persistent_storage_dir, item)
        home_path = os.path.join("/root", item)
        
        # Create directory in volume if needed
        if os.path.dirname(volume_path):
            os.makedirs(os.path.dirname(volume_path), exist_ok=True)
        
        # If a default file/dir exists at destination, remove it to allow symlink
        if os.path.lexists(home_path):
            if os.path.isdir(home_path) and not os.path.islink(home_path):
                shutil.rmtree(home_path)
            else:
                os.remove(home_path)
        
        # Create symbolic link from home directory to persistent volume
        os.symlink(volume_path, home_path)
        print(f"  - Linked {home_path} -> {volume_path}", file=sys.stderr)
    
    print("...done linking files.", file=sys.stderr)


# Standard persistence configurations for different DevBox types
SSH_PERSISTENCE_ITEMS = [
    ".bash_history",
    ".bashrc", 
    ".profile",
    ".viminfo",
    ".vimrc",
    ".gitconfig",
    ".ssh/config",
    ".ssh/known_hosts"
]

RDP_PERSISTENCE_ITEMS = SSH_PERSISTENCE_ITEMS + [
    # Desktop-specific configs
    ".config/xfce4",
    ".local/share/xfce4", 
    ".cache/sessions",
    "Desktop",
    ".xsession"
]

GEMINI_PERSISTENCE_ITEMS = SSH_PERSISTENCE_ITEMS + [
    # Gemini-specific configs
    ".config/gemini"
]

LLM_PERSISTENCE_ITEMS = SSH_PERSISTENCE_ITEMS + [
    # LLM playroom specific configs
    ".config/llm",
    ".models"
]

UNSLOTH_PERSISTENCE_ITEMS = SSH_PERSISTENCE_ITEMS + [
    # Unsloth specific configs
    ".config/unsloth",
    ".models/unsloth"
]


def get_persistence_items(devbox_type="ssh"):
    """
    Get standard persistence items for different DevBox types.
    
    Args:
        devbox_type (str): Type of DevBox ('ssh', 'rdp', 'gemini', 'llm', 'unsloth')
    
    Returns:
        list: Items to persist for the specified DevBox type
    """
    persistence_configs = {
        "ssh": SSH_PERSISTENCE_ITEMS,
        "rdp": RDP_PERSISTENCE_ITEMS,
        "gemini": GEMINI_PERSISTENCE_ITEMS,
        "llm": LLM_PERSISTENCE_ITEMS,
        "unsloth": UNSLOTH_PERSISTENCE_ITEMS
    }
    
    return persistence_configs.get(devbox_type, SSH_PERSISTENCE_ITEMS)