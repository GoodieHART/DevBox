"""
Docker image definitions for DevBox Launcher.

This module provides centralized image definitions with inheritance patterns
to eliminate code duplication and standardize base configurations.

Author: GoodieHART
"""

import modal
import os
from devbox_core.config import (
    CORE_DEV_PACKAGES,
    EXTENDED_DEV_PACKAGES,
    LLAMACPP_VERSION,
    DOWNLOAD_APT_PACKAGES,
    DOWNLOAD_PIP_PACKAGES,
    NODE_MAJOR_VERSION,
    REA_AGENTS_VERSION,
    JADX_HEADLESS_MCP_VERSION,
    GHIDRA_VERSION,
    GHIDRA_BUILD,
    TEMURIN_JDK_VERSION,
    JADX_VERSION,
    APKTOOL_VERSION,
    OPENCODE_VERSION,
    validate_prohibited_packages,
)

# Absolute path to the directory containing this file (for add_local_file references)
_IMAGES_DIR = os.path.dirname(os.path.abspath(__file__))


def _apt_install(image: modal.Image, *packages: str) -> modal.Image:
    """apt_install with a denylist guard, so a prohibited package is never
    baked into a published DevBox image."""
    validate_prohibited_packages(packages)
    return image.apt_install(*packages)


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
        _apt_install(
            modal.Image.debian_slim(python_version=python_version),
            *CORE_DEV_PACKAGES, *EXTENDED_DEV_PACKAGES, *DOWNLOAD_APT_PACKAGES,
        )
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
        _apt_install(
            modal.Image.debian_slim(python_version=python_version),
            *CORE_DEV_PACKAGES, *DOWNLOAD_APT_PACKAGES,
        )
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
            "  [ -d /data ] && cd /data\n"
            "fi\n"
            "BANNER_EOF",
        )
    )


# Standard DevBox images using inheritance
standard_devbox_image = (
    create_base_devbox_image()
    .add_local_python_source(
        "devbox_core.images", "runtime.shared_runtime", "runtime.utils", "devbox_core.config",
        "runtime.persistence_utils", "runtime.backup_utils", "runtime.cost_tracker", "ui.quotes_loader"
    )
    .add_local_file(os.path.join(_IMAGES_DIR, "..", "ui", "quotes.json"), "/etc/quotes.json")
    .add_local_file(os.path.join(_IMAGES_DIR, "..", "integrations", "tmux.conf"), "/etc/devbox/tmux.conf")
)
cuda_devbox_image = (
    _apt_install(
        modal.Image.from_registry(
            "nvidia/cuda:12.1.1-devel-ubuntu22.04",
            add_python="3.11"
        ),
        *CORE_DEV_PACKAGES,
        "nano",
        "libcudnn9-cuda-12",
        "libcudnn9-dev-cuda-12",
    )
    .run_commands(*get_ssh_setup_commands())
    .pip_install(*DOWNLOAD_PIP_PACKAGES)
    .add_local_python_source(
        "devbox_core.images", "runtime.shared_runtime", "runtime.utils", "devbox_core.config",
        "runtime.persistence_utils", "runtime.backup_utils", "runtime.cost_tracker", "ui.quotes_loader"
    )
    .add_local_file(os.path.join(_IMAGES_DIR, "..", "ui", "quotes.json"), "/etc/quotes.json")
    .add_local_file(os.path.join(_IMAGES_DIR, "..", "integrations", "tmux.conf"), "/etc/devbox/tmux.conf")
)

doc_processing_image = (
    _apt_install(create_base_minimal_image(), "pandoc", "texlive-full")
    .add_local_python_source(
        "devbox_core.images", "runtime.shared_runtime", "runtime.utils", "devbox_core.config",
        "runtime.persistence_utils", "runtime.backup_utils", "runtime.cost_tracker", "ui.quotes_loader"
    )
    .add_local_file(os.path.join(_IMAGES_DIR, "..", "ui", "quotes.json"), "/etc/quotes.json")
    .add_local_file(os.path.join(_IMAGES_DIR, "..", "integrations", "tmux.conf"), "/etc/devbox/tmux.conf")
)

assisted_coding_image = (
    create_base_minimal_image()
    .run_commands(
        f"curl -fsSL https://deb.nodesource.com/setup_{NODE_MAJOR_VERSION}.x | bash -",
        "apt-get install -y nodejs",
        "mkdir -p /root/.config/opencode /root/.local/share/opencode /root/.cache/opencode",
        # Install OpenCode and Gemini CLI
        "npm install -g @google/gemini-cli",
        f"curl -fsSL https://opencode.ai/install | bash -s -- --version {OPENCODE_VERSION}",
        "ln -sf /root/.opencode/bin/opencode /usr/local/bin/opencode",
        *get_ssh_setup_commands()
    )
    .add_local_python_source(
        "devbox_core.images", "runtime.shared_runtime", "runtime.utils", "devbox_core.config",
        "runtime.persistence_utils", "runtime.backup_utils", "runtime.cost_tracker", "ui.quotes_loader"
    )
    .add_local_file(os.path.join(_IMAGES_DIR, "..", "ui", "quotes.json"), "/etc/quotes.json")
    .add_local_file(os.path.join(_IMAGES_DIR, "..", "integrations", "opencode-coding.json"), "/etc/devbox/opencode.json")
    .add_local_file(os.path.join(_IMAGES_DIR, "..", "integrations", "opencode-coding.json"), "/etc/devbox/opencode-coding.json")
    .add_local_file(os.path.join(_IMAGES_DIR, "..", "integrations", "tmux.conf"), "/etc/devbox/tmux.conf")
)

forensic_analysis_image = (
    _apt_install(create_base_minimal_image(), "git", "gdb", "binwalk", "tshark", "wabt", "unzip", "binutils")
    .pip_install(*DOWNLOAD_PIP_PACKAGES, "volatility3")
    .run_commands(
        f"curl -fsSL https://deb.nodesource.com/setup_{NODE_MAJOR_VERSION}.x | bash -",
        "apt-get install -y nodejs",
        f"npm install -g rea-agents@{REA_AGENTS_VERSION}",
        "mkdir -p /root/.config/opencode /root/.local/share/opencode /root/.cache/opencode",
        "curl -fsSL https://opencode.ai/install | bash",
        "ln -sf /root/.opencode/bin/opencode /usr/local/bin/opencode",
        "mkdir -p /opt/java",
        f"curl -fsSL -o /tmp/temurin21.tar.gz https://github.com/adoptium/temurin21-binaries/releases/download/jdk-{TEMURIN_JDK_VERSION.replace('+', '%2B')}/OpenJDK21U-jdk_x64_linux_hotspot_{TEMURIN_JDK_VERSION.split('+')[0]}_{TEMURIN_JDK_VERSION.split('+')[1]}.tar.gz",
        "tar -xzf /tmp/temurin21.tar.gz -C /opt/java",
        f"ln -sfn /opt/java/jdk-{TEMURIN_JDK_VERSION} /opt/java/temurin-21",
        "rm -f /tmp/temurin21.tar.gz",
        "mkdir -p /opt/ghidra",
        f"curl -fsSL -o /tmp/ghidra.zip https://github.com/NationalSecurityAgency/ghidra/releases/download/Ghidra_{GHIDRA_VERSION}_build/ghidra_{GHIDRA_VERSION}_PUBLIC_{GHIDRA_BUILD}.zip",
        "unzip -q /tmp/ghidra.zip -d /opt/ghidra",
        "rm -f /tmp/ghidra.zip",
        f"curl -fsSL -o /tmp/jadx.zip https://github.com/skylot/jadx/releases/download/v{JADX_VERSION}/jadx-{JADX_VERSION}.zip",
        "mkdir -p /opt/jadx && unzip -q /tmp/jadx.zip -d /opt/jadx && rm -f /tmp/jadx.zip && ln -sf /opt/jadx/bin/jadx /usr/local/bin/jadx",
        f"mkdir -p /opt/jadx-headless-mcp && curl -fsSL -o /opt/jadx-headless-mcp/jadx-headless-mcp-{JADX_HEADLESS_MCP_VERSION}-all.jar https://github.com/1013503897/jadx-headless-mcp/releases/download/v{JADX_HEADLESS_MCP_VERSION}/jadx-headless-mcp-{JADX_HEADLESS_MCP_VERSION}-all.jar",
        f"curl -fsSL -o /usr/local/bin/apktool.jar https://github.com/iBotPeaches/Apktool/releases/download/v{APKTOOL_VERSION}/apktool_{APKTOOL_VERSION}.jar",
        "printf '#!/bin/sh\\nexec java -jar /usr/local/bin/apktool.jar \"$@\"\\n' > /usr/local/bin/apktool && chmod +x /usr/local/bin/apktool",
        f"cat > /etc/profile.d/rea.sh << 'REA_EOF'\nexport JAVA_HOME=/opt/java/temurin-21\nexport GHIDRA_INSTALL_DIR=/opt/ghidra/ghidra_{GHIDRA_VERSION}_PUBLIC\nexport REA_GHIDRA_STARTUP_TIMEOUT_MS=120000\nexport REA_MCP_MAX_RESPONSE_BYTES=52428800\nexport REA_JADX_MCP_JAR=/opt/jadx-headless-mcp/jadx-headless-mcp-{JADX_HEADLESS_MCP_VERSION}-all.jar\nexport PATH=/opt/java/temurin-21/bin:/opt/jadx/bin:$PATH\nREA_EOF",
         "chmod 644 /etc/profile.d/rea.sh",
         "bash -c 'source /etc/profile.d/rea.sh; rea setup --client opencode --yes'",
         "mkdir -p /opt/forensic_analysis/volatility3/symbols",
         "curl -fsSL https://downloads.volatilityfoundation.org/volatility3/symbols/windows.zip -o /tmp/windows.zip",
         "curl -fsSL https://downloads.volatilityfoundation.org/volatility3/symbols/linux.zip -o /tmp/linux.zip",
         "curl -fsSL https://downloads.volatilityfoundation.org/volatility3/symbols/mac.zip -o /tmp/mac.zip",
         "unzip -q /tmp/windows.zip -d /opt/forensic_analysis/volatility3/symbols",
         "unzip -q /tmp/linux.zip -d /opt/forensic_analysis/volatility3/symbols",
         "unzip -q /tmp/mac.zip -d /opt/forensic_analysis/volatility3/symbols",
         "rm -f /tmp/windows.zip /tmp/linux.zip /tmp/mac.zip",
        *get_ssh_setup_commands()
    )
    .add_local_python_source(
        "devbox_core.images", "runtime.shared_runtime", "runtime.utils", "devbox_core.config",
        "runtime.persistence_utils", "runtime.backup_utils", "runtime.cost_tracker", "ui.quotes_loader"
    )
    .add_local_file(os.path.join(_IMAGES_DIR, "..", "ui", "quotes.json"), "/etc/quotes.json")
    .add_local_file(os.path.join(_IMAGES_DIR, "..", "integrations", "opencode.json"), "/etc/devbox/opencode.json")
    .add_local_file(os.path.join(_IMAGES_DIR, "..", "integrations", "tmux.conf"), "/etc/devbox/tmux.conf")
)

llm_playroom_image = (
    _apt_install(
        create_base_minimal_image(),
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
        "devbox_core.images", "runtime.shared_runtime", "runtime.utils", "devbox_core.config",
        "runtime.persistence_utils", "runtime.backup_utils", "runtime.cost_tracker", "ui.quotes_loader"
    )
    .add_local_file(os.path.join(_IMAGES_DIR, "..", "ui", "quotes.json"), "/etc/quotes.json")
    .add_local_file(os.path.join(_IMAGES_DIR, "..", "integrations", "tmux.conf"), "/etc/devbox/tmux.conf")
)

llamacpp_cpu_image = (
    _apt_install(
        create_base_minimal_image(),
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
        "devbox_core.images", "runtime.shared_runtime", "runtime.utils", "devbox_core.config",
        "runtime.persistence_utils", "runtime.backup_utils", "runtime.cost_tracker", "integrations.exa_helper", "integrations.exa_proxy", "ui.quotes_loader",
        "runtime.llamacpp_runtime", "devbox_core.llamacpp_models"
    )
    .add_local_file(os.path.join(_IMAGES_DIR, "..", "ui", "quotes.json"), "/etc/quotes.json")
    .add_local_file(os.path.join(_IMAGES_DIR, "..", "integrations", "tmux.conf"), "/etc/devbox/tmux.conf")
)

rdp_devbox_image = (
    _apt_install(
        create_base_devbox_image(),
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
        # Debian bookworm backports provides PipeWire xrdp audio modules.
        "echo 'deb http://deb.debian.org/debian bookworm-backports main contrib non-free' > /etc/apt/sources.list.d/bookworm-backports.list",
        "apt-get update",
        "apt-get install -y -t bookworm-backports pipewire pipewire-pulse wireplumber pipewire-alsa pipewire-module-xrdp",
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
        "echo '' >> /usr/local/bin/startxfce4-wrapper",
        "echo '# Start PipeWire for RDP audio output only' >> /usr/local/bin/startxfce4-wrapper",
        "echo 'if ! pgrep -u root -x pipewire >/dev/null 2>&1; then' >> /usr/local/bin/startxfce4-wrapper",
        "echo '  pipewire >/tmp/pipewire.log 2>&1 &' >> /usr/local/bin/startxfce4-wrapper",
        "echo 'fi' >> /usr/local/bin/startxfce4-wrapper",
        "echo 'if ! pgrep -u root -x wireplumber >/dev/null 2>&1; then' >> /usr/local/bin/startxfce4-wrapper",
        "echo '  wireplumber >/tmp/wireplumber.log 2>&1 &' >> /usr/local/bin/startxfce4-wrapper",
        "echo 'fi' >> /usr/local/bin/startxfce4-wrapper",
        "echo 'if ! pgrep -u root -x pipewire-pulse >/dev/null 2>&1; then' >> /usr/local/bin/startxfce4-wrapper",
        "echo '  pipewire-pulse >/tmp/pipewire-pulse.log 2>&1 &' >> /usr/local/bin/startxfce4-wrapper",
        "echo 'fi' >> /usr/local/bin/startxfce4-wrapper",
        "echo 'sleep 0.5' >> /usr/local/bin/startxfce4-wrapper",
        "echo 'exec startxfce4' >> /usr/local/bin/startxfce4-wrapper",
        "chmod +x /usr/local/bin/startxfce4-wrapper",
        # Configure XFCE session using wrapper
        "printf '#!/bin/sh\\nexec /usr/local/bin/startxfce4-wrapper\\n' > /etc/skel/.xsession",
        "chmod +x /etc/skel/.xsession",
        # /etc/skel only reaches *new* users, so root keeps its own launcher.
        # This one is also re-installed at runtime, after the backup restore.
        "printf '#!/bin/sh\\nexec /usr/local/bin/startxfce4-wrapper\\n' > /root/.xsession",
        "chmod +x /root/.xsession",
        # Create basic XFCE config directory structure
        "mkdir -p /etc/skel/.config/xfce4",
        "mkdir -p /etc/skel/.cache/sessions",
        # Output-only xrdp audio: do not load module-xrdp-source.
        '''cat > /etc/xrdp/load_pw_modules.sh <<'EOF'
#!/bin/sh
if ! command -v pw-cli >/dev/null; then
  echo 'pw-cli not found, exiting'
  exit 0
fi
if ! pw-cli quit >/dev/null 2>&1; then
  echo 'PipeWire server is not running, exiting'
  exit 0
fi
if [ -n "$XRDP_SESSION" -a -n "$XRDP_SOCKET_PATH" ]; then
  OBJECT_IDS=$(pw-cli ls Node 2>/dev/null | sed -e 's/^[^a-z]//' | grep -w '^id' | sed -e 's/^[^0-9]*//' -e 's/[^0-9]/-/' | cut -d- -f1)
  for OBJECT_ID in $OBJECT_IDS; do
    NODE_NAME=$(pw-cli info $OBJECT_ID 2>/dev/null | grep -w 'node.name' | cut -d '"' -f2)
    if [ "$NODE_NAME" = 'xrdp-sink' ]; then
      pw-cli destroy $OBJECT_ID >/dev/null 2>&1
    fi
  done
  export PIPEWIRE_LOG_SYSTEMD=false
  export PIPEWIRE_DEBUG=1
  QUANTUMVAL=2048
  QUANTUMVAL2=$((QUANTUMVAL * 2))
  pw-cli -m -d load-module libpipewire-module-xrdp sink.node.latency=$QUANTUMVAL sink.stream.props={node.name=xrdp-sink} >/dev/null 2>&1 &
  sleep 1
  pw-metadata -n settings 0 clock.force-quantum $QUANTUMVAL >/dev/null 2>&1
  pw-metadata -n settings 0 default.clock.force-quantum $QUANTUMVAL2 >/dev/null 2>&1
  pw-metadata -n settings 0 default.clock.quantum $QUANTUMVAL2 >/dev/null 2>&1
  pw-metadata -n settings 0 default.clock.min-quantum $QUANTUMVAL2 >/dev/null 2>&1
  pw-metadata -n settings 0 default.clock.rate 44100 >/dev/null 2>&1
  if command -v pactl >/dev/null; then
    pactl set-default-sink xrdp-sink >/dev/null 2>&1
  fi
fi
exit 0
EOF
''',
        "chmod +x /etc/xrdp/load_pw_modules.sh",
        # Set root password for RDP (needed for desktop)
        'echo "root:devbox123" | chpasswd',
        *get_ssh_setup_commands()
    )
    .add_local_python_source(
        "devbox_core.images", "runtime.shared_runtime", "runtime.utils", "devbox_core.config",
        "runtime.persistence_utils", "runtime.backup_utils", "runtime.cost_tracker", "ui.quotes_loader"
    )
    .add_local_file(os.path.join(_IMAGES_DIR, "..", "ui", "quotes.json"), "/etc/quotes.json")
    .add_local_file(os.path.join(_IMAGES_DIR, "..", "integrations", "tmux.conf"), "/etc/devbox/tmux.conf")
)
