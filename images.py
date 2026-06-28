"""
Docker image definitions for DevBox Launcher.

This module provides centralized image definitions with inheritance patterns
to eliminate code duplication and standardize base configurations.

Author: GoodieHART
"""

import modal
from config import CORE_DEV_PACKAGES, EXTENDED_DEV_PACKAGES, LLAMACPP_VERSION, DOWNLOAD_APT_PACKAGES, DOWNLOAD_PIP_PACKAGES

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
        .apt_install(*CORE_DEV_PACKAGES, *EXTENDED_DEV_PACKAGES, *DOWNLOAD_APT_PACKAGES)
        .pip_install(*DOWNLOAD_PIP_PACKAGES)
        .run_commands(
            *get_ssh_setup_commands(),
            # Install Starship prompt (pinned version)
            "curl -sSLO https://github.com/starship/starship/releases/download/v1.22.1/starship-x86_64-unknown-linux-gnu.tar.gz",
            "tar -xzf starship-x86_64-unknown-linux-gnu.tar.gz -C /usr/local/bin/",
            "rm starship-x86_64-unknown-linux-gnu.tar.gz",
            # Create starship init script (interactive only)
            "printf '%s\\n' 'if command -v starship &> /dev/null && [ -t 0 ]; then' '  eval \"$(starship init bash)\"' 'fi' > /etc/profile.d/starship.sh",
            # Create devbox-banner display script
            "cat > /etc/profile.d/devbox-banner.sh << 'BANNER_EOF'\n"
            "if [ -t 0 ] && [ -f /etc/devbox-banner ]; then\n"
            "  clear\n"
            "  cat /etc/devbox-banner\n"
            "  echo\n"
            "  python3 -c \"from quotes_loader import get_random_quote; q = get_random_quote(); print(q['text']); print('- ' + q['author'])\" 2>/dev/null || true\n"
            "  [ -d /data ] && cd /data\n"
            "fi\n"
            "BANNER_EOF",
        )
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
        .apt_install(*CORE_DEV_PACKAGES, *DOWNLOAD_APT_PACKAGES)
        .pip_install(*DOWNLOAD_PIP_PACKAGES)
        .run_commands(
            *get_ssh_setup_commands(),
            # Install Starship prompt (pinned version)
            "curl -sSLO https://github.com/starship/starship/releases/download/v1.22.1/starship-x86_64-unknown-linux-gnu.tar.gz",
            "tar -xzf starship-x86_64-unknown-linux-gnu.tar.gz -C /usr/local/bin/",
            "rm starship-x86_64-unknown-linux-gnu.tar.gz",
            # Create starship init script (interactive only)
            "printf '%s\\n' 'if command -v starship &> /dev/null && [ -t 0 ]; then' '  eval \"$(starship init bash)\"' 'fi' > /etc/profile.d/starship.sh",
            # Create devbox-banner display script
            "cat > /etc/profile.d/devbox-banner.sh << 'BANNER_EOF'\n"
            "if [ -t 0 ] && [ -f /etc/devbox-banner ]; then\n"
            "  clear\n"
            "  cat /etc/devbox-banner\n"
            "  echo\n"
            "  python3 -c \"from quotes_loader import get_random_quote; q = get_random_quote(); print(q['text']); print('- ' + q['author'])\" 2>/dev/null || true\n"
            "  [ -d /data ] && cd /data\n"
            "fi\n"
            "BANNER_EOF",
        )
    )


# Standard DevBox images using inheritance
standard_devbox_image = (
    create_base_devbox_image()
    .add_local_python_source(
        "images", "shared_runtime", "utils", "config",
        "persistence_utils", "backup_utils", "quotes_loader"
    )
    .add_local_file("quotes.json", "/etc/quotes.json")
)
cuda_devbox_image = (
    modal.Image.from_registry(
        "nvidia/cuda:12.1.1-devel-ubuntu22.04",
        add_python="3.11"
    )
    .apt_install(
        *CORE_DEV_PACKAGES,
        "nano",
        "libcudnn9-cuda-12", 
        "libcudnn9-dev-cuda-12",
    )
    .run_commands(*get_ssh_setup_commands())
    .pip_install(*DOWNLOAD_PIP_PACKAGES)
    .add_local_python_source(
        "images", "shared_runtime", "utils", "config",
        "persistence_utils", "backup_utils", "quotes_loader"
    )
    .add_local_file("quotes.json", "/etc/quotes.json")
)

doc_processing_image = (
    create_base_minimal_image()
    .apt_install("pandoc", "texlive-full")
    .add_local_python_source(
        "images", "shared_runtime", "utils", "config",
        "persistence_utils", "backup_utils", "quotes_loader"
    )
    .add_local_file("quotes.json", "/etc/quotes.json")
)

assisted_coding_image = (
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
    .add_local_python_source(
        "images", "shared_runtime", "utils", "config",
        "persistence_utils", "backup_utils", "quotes_loader"
    )
    .add_local_file("quotes.json", "/etc/quotes.json")
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
    .add_local_python_source(
        "images", "shared_runtime", "utils", "config",
        "persistence_utils", "backup_utils", "quotes_loader"
    )
    .add_local_file("quotes.json", "/etc/quotes.json")
)

llamacpp_cpu_image = (
    create_base_minimal_image()
    .apt_install(
        "libssl3",
        "libcurl4", 
        "zlib1g",
    )
    .pip_install(
        "exa-py",       
        "openai",
        "httpx", 
        "hf",
        "huggingface_hub",
        "hf_transfer",
    )
    .run_commands(
        # Download and extract prebuilt llama.cpp binaries
        f"curl -L -o /tmp/llama.tar.gz https://github.com/ggml-org/llama.cpp/releases/download/{LLAMACPP_VERSION}/llama-{LLAMACPP_VERSION}-bin-ubuntu-x64.tar.gz",
        "mkdir -p /opt/llama.cpp",
        "tar -xzf /tmp/llama.tar.gz -C /opt/llama.cpp --strip-components=1",
        "rm /tmp/llama.tar.gz",
        
        # symlinks for easy access
        "ln -sf /opt/llama.cpp/llama-cli /usr/local/bin/llama-cli",
        "ln -sf /opt/llama.cpp/llama-server /usr/local/bin/llama-server",
        "ln -sf /opt/llama.cpp/llama-bench /usr/local/bin/llama-bench",
        "ln -sf /opt/llama.cpp/llama-mtmd-cli /usr/local/bin/llama-mtmd-cli",
        
        *get_ssh_setup_commands()
    )
    .add_local_python_source(
        "images", "shared_runtime", "utils", "config",
        "persistence_utils", "backup_utils", "exa_helper", "exa_proxy", "quotes_loader"
    )
    .add_local_file("quotes.json", "/etc/quotes.json")
)

rdp_devbox_image = (
    create_base_devbox_image()
    .apt_install(
        "xrdp",
        "xfce4", 
        "xfce4-goodies",
        "xorgxrdp",
        "dbus-x11",
        "xorg",
        "tightvncserver",
    )
    .run_commands(
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
    .add_local_python_source(
        "images", "shared_runtime", "utils", "config",
        "persistence_utils", "backup_utils"
    )
)

forensic_analysis_image =  (
   create_base_minimal_image()
  .pip_install(*DOWNLOAD_PIP_PACKAGES, "volatility3")
  .run_commands(
    "mkdir -p /opt/forensic_analysis",
    "mkdir -p /opt/forensic_analysis/volatility3/symbols",
    
    "curl https://downloads.volatilityfoundation.org/volatility3/symbols/windows.zip -o /tmp/windows.zip",
    "curl https://downloads.volatilityfoundation.org/volatility3/symbols/linux.zip -o /tmp/linux.zip",
    "curl https://downloads.volatilityfoundation.org/volatility3/symbols/mac.zip -o /tmp/mac.zip",
    
    "unzip /tmp/windows.zip -d /opt/forensic_analysis/volatility3/symbols",
    "unzip /tmp/linux.zip -d /opt/forensic_analysis/volatility3/symbols",
    "unzip /tmp/mac.zip -d /opt/forensic_analysis/volatility3/symbols",
    # symbols ought to be moved to volatility's execution directory
    *get_ssh_setup_commands()
    )
    .add_local_python_source(
        "images", "shared_runtime", "utils", "config",
        "persistence_utils", "backup_utils", "quotes_loader"
    )
    .add_local_file("quotes.json", "/etc/quotes.json")
)
