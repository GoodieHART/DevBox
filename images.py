"""
Docker image definitions for DevBox Launcher.

This module provides centralized image definitions with inheritance patterns
to eliminate code duplication and standardize base configurations.

Author: GoodieHART
"""

import modal
from config import CORE_DEV_PACKAGES, EXTENDED_DEV_PACKAGES

LLAMACPP_VERSION = "b7898"

def get_ssh_setup_commands():
    """
    Get standardized SSH setup commands for all DevBox images.
    
    Returns:
        list: SSH configuration commands
    """
    return [
        "mkdir -p /root/.ssh",
        "chmod 700 /root/.ssh", 
        "touch /root/.ssh/authorized_keys",
        "chmod 600 /root/.ssh/authorized_keys",
        "mkdir -p /var/run/sshd",
        # Configure SSH to allow key-based auth and disable password auth
        "echo 'PubkeyAuthentication yes' >> /etc/ssh/sshd_config",
        "echo 'PasswordAuthentication no' >> /etc/ssh/sshd_config",
        "echo 'PermitRootLogin prohibit-password' >> /etc/ssh/sshd_config",
        "echo 'AuthorizedKeysFile .ssh/authorized_keys' >> /etc/ssh/sshd_config",
    ]


def create_base_devbox_image(python_version="3.10"):
    """
    Create base DevBox image with common development tools and SSH setup.
    
    Args:
        python_version: Python version to install (default: "3.10")
        
    Returns:
        modal.Image: Base DevBox image with SSH and core tools
    """
    return (
        modal.Image.debian_slim(python_version=python_version)
        .apt_install(*CORE_DEV_PACKAGES, *EXTENDED_DEV_PACKAGES)
        .run_commands(*get_ssh_setup_commands())
    )


def create_base_minimal_image(python_version="3.10"):
    """
    Create minimal base image with SSH setup only.
    
    Args:
        python_version: Python version to install (default: "3.10")
        
    Returns:
        modal.Image: Minimal base image with SSH only
    """
    return (
        modal.Image.debian_slim(python_version=python_version)
        .apt_install(*CORE_DEV_PACKAGES)
        .run_commands(*get_ssh_setup_commands())
    )


# Standard DevBox images using inheritance
standard_devbox_image = create_base_devbox_image()

cuda_devbox_image = (
    modal.Image.from_registry(
        "nvidia/cuda:12.1.1-devel-ubuntu22.04",
        add_python="3.11"
    )
    .apt_install(
        *CORE_DEV_PACKAGES,  # SSH and core tools
        "nano",
        "libcudnn9-cuda-12", 
        "libcudnn9-dev-cuda-12",
    )
    .run_commands(*get_ssh_setup_commands())
)

doc_processing_image = (
    create_base_minimal_image()
    .apt_install("pandoc", "texlive-full")
)

gemini_cli_image = (
    create_base_minimal_image()
    .run_commands(
        # Install Node.js 20.x
        "curl -fsSL https://deb.nodesource.com/setup_20.x | bash -",
        "apt-get install -y nodejs",
        # Install OpenCode and Gemini CLI
        "npm install -g @google/gemini-cli",
        "curl -fsSL https://opencode.ai/install | bash",
        *get_ssh_setup_commands()
    )
)

llm_playroom_image = (
    create_base_minimal_image()
    .apt_install(
        "pciutils",
        "lshw", 
        "zstd",
    )
    .run_commands(
        # Install Ollama
        "curl -fsSL https://ollama.com/install.sh | bash",
        *get_ssh_setup_commands()
    )
)

llamacpp_cpu_image = (
    create_base_minimal_image()
    .apt_install(
        "libssl3",
        "libcurl4", 
        "zlib1g",
    )
    .run_commands(
        # Download and extract prebuilt llama.cpp binaries (CPU only)
        f"curl -L -o /tmp/llama.tar.gz https://github.com/ggml-org/llama.cpp/releases/download/{LLAMACPP_VERSION}/llama-{LLAMACPP_VERSION}-bin-ubuntu-x64.tar.gz",
        "mkdir -p /opt/llama.cpp",
        "tar -xzf /tmp/llama.tar.gz -C /opt/llama.cpp --strip-components=1",
        "rm /tmp/llama.tar.gz",
        
        # Create symlinks for easy access
        "ln -sf /opt/llama.cpp/bin/llama-cli /usr/local/bin/llama-cli",
        "ln -sf /opt/llama.cpp/bin/llama-server /usr/local/bin/llama-server",
        "ln -sf /opt/llama.cpp/bin/llama-bench /usr/local/bin/llama-bench",
        "mkdir -p /opt/models/llama.cpp",
        *get_ssh_setup_commands()
    )
)

rdp_devbox_image = (
    create_base_devbox_image()
    .apt_install(
        # RDP/Desktop packages
        "xrdp",
        "xfce4", 
        "xfce4-goodies",
        "xorgxrdp",
        "dbus-x11",
        "xorg",
        "tightvncserver",
    )
    .run_commands(
        # RDP setup
        "mkdir -p /var/run/xrdp",
        "chmod 755 /etc/xrdp",
        # Create XFCE environment wrapper for proper XDG setup
        "echo '#!/bin/bash' > /usr/local/bin/startxfce4-wrapper",
        "echo '# XFCE RDP Wrapper with proper environment' >> /usr/local/bin/startxfce4-wrapper",
        "echo '' >> /usr/local/bin/startxfce4-wrapper",
        "echo 'export XDG_CONFIG_DIRS=/etc/xdg' >> /usr/local/bin/startxfce4-wrapper",
        "echo 'export XDG_DATA_DIRS=/usr/local/share:/usr/share' >> /usr/local/bin/startxfce4-wrapper",
        "echo 'export XDG_RUNTIME_DIR=/tmp/xdg-runtime' >> /usr/local/bin/startxfce4-wrapper",
        "echo '' >> /usr/local/bin/startxfce4-wrapper",
        "echo '# Ensure runtime directory exists' >> /usr/local/bin/startxfce4-wrapper",
        "echo 'mkdir -p /tmp/xdg-runtime' >> /usr/local/bin/startxfce4-wrapper",
        "echo 'chmod 700 /tmp/xdg-runtime' >> /usr/local/bin/startxfce4-wrapper",
        "echo '' >> /usr/local/bin/startxfce4-wrapper",
        "echo '# Start XFCE with proper environment' >> /usr/local/bin/startxfce4-wrapper",
        "echo 'exec startxfce4' >> /usr/local/bin/startxfce4-wrapper",
        "chmod +x /usr/local/bin/startxfce4-wrapper",
        # Configure XFCE session using wrapper
        "printf '#!/bin/sh\\n/usr/local/bin/startxfce4-wrapper\\n' > /etc/skel/.xsession",
        "chmod +x /etc/skel/.xsession",
        # Create basic XFCE config directory structure
        "mkdir -p /etc/skel/.config/xfce4",
        "mkdir -p /etc/skel/.cache/sessions",
        # Set root password for RDP (needed for desktop)
        'echo "root:devbox123" | chpasswd',
        *get_ssh_setup_commands()
    )
)