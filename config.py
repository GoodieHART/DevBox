"""
Configuration constants for DevBox Launcher.

This module centralizes all configuration constants, resource allocations,
and global settings used across the DevBox application.

Author: DevBox Launcher
"""

# Auto-shutdown configuration
# Container will shut down if no one is connected via SSH for this many seconds.
IDLE_TIMEOUT_SECONDS = 300  # 5 minutes

# Version constants
LLAMACPP_VERSION = "b7898"  # Latest stable release

# Resource configurations for different DevBox types
# These will be filled with actual Modal objects during runtime

# CPU-only DevBox resource arguments
CPU_DEVBOX_ARGS = {
    "secrets": None,  # Will be filled with modal.Secret.from_name("ssh-public-key")
    "volumes": None,  # Will be filled with dev_volume
    "cpu": 0.5,
    "memory": 1024,
    "timeout": 3600,
}

# Standard GPU DevBox resource arguments
GPU_DEVBOX_ARGS = {
    "secrets": None,  # Will be filled with modal.Secret.from_name("ssh-public-key")
    "volumes": None,  # Will be filled with dev_volume
    "cpu": 1.0,
    "memory": 2048,
    "timeout": 28800,  # 8 hours
}

# RDP-specific resource arguments (higher resources for desktop environment)
CPU_DEVBOX_ARGS_RDP = {
    "secrets": None,  # Will be filled with modal.Secret.from_name("ssh-public-key")
    "volumes": None,  # Will be filled with dev_volume
    "cpu": 1.0,  # Higher CPU for desktop environment
    "memory": 2048,  # Double memory for XFCE + RDP
    "timeout": 3600,  # 1 hour
}

# RDP GPU resource arguments (highest resources)
GPU_DEVBOX_ARGS_RDP = {
    "secrets": None,  # Will be filled with modal.Secret.from_name("ssh-public-key")
    "volumes": None,  # Will be filled with dev_volume
    "cpu": 1.5,  # Higher CPU for GPU + desktop
    "memory": 4096,  # Higher memory for GPU + desktop
    "timeout": 28800,  # 8 hours
}

# GPU type mappings
GPU_TYPES = {
    "t4": "NVIDIA T4 - Cost-effective, good for inference",
    "l4": "NVIDIA L4 - Newer, more performant than T4",
    "a10g": "NVIDIA A10G - Higher performance, more VRAM",
    "l40s": "NVIDIA L40S - High-end AI workload GPU"
}

# Package groups for reusable configurations
CORE_DEV_PACKAGES = [
    "openssh-server",
    "git", 
    "neovim",
    "curl",
    "wget",
    "unzip",
    "procps",
]

EXTENDED_DEV_PACKAGES = [
    "clang",
    "cmake",
    "htop",
    "nano",
    "zlib1g-dev",
    "build-essential",
    "pkg-config",
    "python3-dev",
]

# Function to fill in runtime modal objects
def get_resource_config(config_type="cpu", gpu_type=None, is_rdp=False):
    """
    Get complete resource configuration for DevBox type.
    
    Args:
        config_type: "cpu" or "gpu"
        gpu_type: GPU type if config_type="gpu" (t4, l4, a10g, l40s)
        is_rdp: Whether this is for RDP environment
        
    Returns:
        dict: Complete configuration with Modal objects
    """
    if config_type == "cpu":
        base_config = CPU_DEVBOX_ARGS_RDP if is_rdp else CPU_DEVBOX_ARGS
    elif config_type == "gpu":
        base_config = GPU_DEVBOX_ARGS_RDP if is_rdp else GPU_DEVBOX_ARGS
    else:
        raise ValueError(f"Unknown config_type: {config_type}")
    
    # Add Modal objects (these need to be imported from the main module)
    config = base_config.copy()
    if config["secrets"] is None:
        config["secrets"] = ["modal.Secret.from_name('ssh-public-key')"]
    if config["volumes"] is None:
        config["volumes"] = {"/data": None}  # Will be filled with actual volume
    
    return config