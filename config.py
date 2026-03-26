"""
Configuration constants for DevBox Launcher.

This module centralizes all configuration constants, resource allocations,
and global settings used across DevBox

Author: GoodieHART
"""

# Container will shut down if no one is connected via SSH for this many seconds.
# All Time Values are in seconds
IDLE_TIMEOUT_SECONDS = 300  # 5 minutes

# Version constants
LLAMACPP_VERSION = "b8272" # this will be made dynamic in future

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
    "secrets": None,
    "volumes": None,
    "cpu": 1.0,
    "memory": 2048,
    "timeout": 18000,
}

# RDP-specific resource arguments (higher resources for desktop environment)
CPU_DEVBOX_ARGS_RDP = {
    "secrets": None, 
    "volumes": None,
    "cpu": 1.0,
    "memory": 2048,
    "timeout": 10800,
}

# RDP GPU resource arguments (highest resources)
GPU_DEVBOX_ARGS_RDP = {
    "secrets": None,
    "volumes": None,
    "cpu": 1.5,
    "memory": 4096,
    "timeout": 18000,
}

# Package groups for reusable configurations
CORE_DEV_PACKAGES = [
    "openssh-server",
    "git",
    "nano",
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
    "zlib1g-dev",
    "build-essential",
    "pkg-config",
    "python3-dev",
]

# Function to fill in runtime modal objects
def get_resource_config(config_type="cpu", is_rdp=False, secrets=None, volume=None):
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

  config = base_config.copy()
  config["secrets"] = secrets
  config["volumes"] = {"/data": volume}
  return config