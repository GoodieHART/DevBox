"""
Persistence utilities for DevBox applications.

Provides configurable persistent storage setup to eliminate code duplication.
"""

import os
import shutil
import sys


def setup_persistence(
    items_to_persist, persistent_storage_dir="/data/.config_persistence",
    home_base="/root",
):
    """
    Set up persistent dotfiles and configs using symbolic links.

    Args:
        items_to_persist (list): List of files/directories to persist
        persistent_storage_dir (str): Base directory for persistent storage
        home_base (str): Home directory to link from (defaults to /root)
    """
    # --- Set up persistent dotfiles and desktop configs using symbolic links ---
    print("Linking persistent configuration files...", file=sys.stderr)

    os.makedirs(persistent_storage_dir, exist_ok=True)

    for item in items_to_persist:
        # Determine paths
        volume_path = os.path.join(persistent_storage_dir, item)
        home_path = os.path.join(home_base, item)

        # Create parent directory in volume if needed
        if os.path.dirname(volume_path):
            os.makedirs(os.path.dirname(volume_path), exist_ok=True)

        # A stale volume entry from an older image may have the wrong type
        # (e.g. empty file where the current image ships a directory).
        # Reconcile only when home exists: a missing home path (fresh boot
        # after a wiped or skipped restore) must never delete volume data.
        if os.path.lexists(home_path) and os.path.lexists(volume_path) and (
            os.path.isdir(home_path) != os.path.isdir(volume_path)
        ):
            if os.path.isdir(volume_path) and not os.path.islink(volume_path):
                shutil.rmtree(volume_path)
            else:
                os.remove(volume_path)

        # Paths in DIRECTORY_PERSISTENCE_ITEMS must always be directories:
        # older images left empty-file placeholders that break tools
        # expecting directories (e.g. opencode mkdir log).
        if item in DIRECTORY_PERSISTENCE_ITEMS and os.path.lexists(volume_path) and not os.path.isdir(volume_path):
            os.remove(volume_path)

        # Ensure the target exists before creating symlink
        if not os.path.exists(volume_path):
            if item in DIRECTORY_PERSISTENCE_ITEMS or os.path.isdir(home_path):
                os.makedirs(volume_path, exist_ok=True)
            else:
                # Create empty file at target location
                open(volume_path, "a").close()

        # If a default file/dir exists at destination, remove it to allow symlink
        if os.path.lexists(home_path):
            if os.path.isdir(home_path) and not os.path.islink(home_path):
                shutil.rmtree(home_path)
            else:
                os.remove(home_path)

        # Ensure parent directory exists at home_path before symlinking
        os.makedirs(os.path.dirname(home_path), exist_ok=True)

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
    ".ssh/known_hosts",
]

RDP_PERSISTENCE_ITEMS = SSH_PERSISTENCE_ITEMS + [
    # Desktop-specific configs
    ".config/xfce4",
    ".local/share/xfce4",
    ".cache/sessions",
    "Desktop",
]

GEMINI_PERSISTENCE_ITEMS = SSH_PERSISTENCE_ITEMS + [
    # Gemini-specific configs
    ".config/gemini"
]

LLM_PERSISTENCE_ITEMS = SSH_PERSISTENCE_ITEMS + [
    # LLM playroom specific configs
    ".config/llm",
    ".models",
]

UNSLOTH_PERSISTENCE_ITEMS = SSH_PERSISTENCE_ITEMS + [
    # Unsloth specific configs
    ".config/unsloth",
    ".models/unsloth",
]

OPENCODE_PERSISTENCE_ITEMS = SSH_PERSISTENCE_ITEMS + [
    # OpenCode server state — persisted so sessions/auth survive restarts.
    # Worktrees themselves live in /data (already persistent), these are configs.
    ".config/opencode",
    ".local/share/opencode",
    ".cache/opencode",
]

FORENSICS_PERSISTENCE_ITEMS = OPENCODE_PERSISTENCE_ITEMS

ASSISTED_CODING_PERSISTENCE_ITEMS = GEMINI_PERSISTENCE_ITEMS + [
    ".config/opencode",
    ".local/share/opencode",
    ".cache/opencode",
]

# Every persistence item that is not one of the SSH dotfiles is a directory.
# Keeping this list derived from the item lists (instead of hard-coding only
# the OpenCode paths) prevents setup_persistence() from creating empty *files*
# for directories such as ~/.config/xfce4 when they are absent from a fresh
# container, which later broke `mkdir -p` on the resulting file symlink.
DIRECTORY_PERSISTENCE_ITEMS = frozenset(
    item
    for items in (
        RDP_PERSISTENCE_ITEMS,
        GEMINI_PERSISTENCE_ITEMS,
        LLM_PERSISTENCE_ITEMS,
        UNSLOTH_PERSISTENCE_ITEMS,
        OPENCODE_PERSISTENCE_ITEMS,
        ASSISTED_CODING_PERSISTENCE_ITEMS,
    )
    for item in items
    if item not in SSH_PERSISTENCE_ITEMS
)


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
        "assisted_coding": ASSISTED_CODING_PERSISTENCE_ITEMS,
        "llm": LLM_PERSISTENCE_ITEMS,
        "unsloth": UNSLOTH_PERSISTENCE_ITEMS,
        "opencode": OPENCODE_PERSISTENCE_ITEMS,
        "forensic_analysis": FORENSICS_PERSISTENCE_ITEMS,
    }

    return persistence_configs.get(devbox_type, SSH_PERSISTENCE_ITEMS)
