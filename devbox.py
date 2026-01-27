import modal
import subprocess
import sys
import time
import random
import platform
import os

try:
    from ui_utils import create_box, show_spinner
except ImportError:
    sys.stderr.write("Warning: ui_utils module not found. Using fallback functions.\n")
    
    def create_box(content, title="", width=60):
        lines = content.split("\n")
        max_len = max(len(line) for line in lines) if lines else 0
        box_width = max(max_len + 4, width)
        if title:
            title_len = len(title) + 2
            left_padding = (box_width - title_len) // 2
            right_padding = box_width - title_len - left_padding
            top_border = "╔" + "═" * left_padding + f" {title} " + "═" * right_padding + "╗"
        else:
            top_border = "╔" + "═" * box_width + "╗"
        print(top_border)
        for line in lines:
            padded_line = line.ljust(max_len)
            print(f"║ {padded_line} ║")
        bottom_border = "╚" + "═" * box_width + "╝"
        print(bottom_border)
    
    def show_spinner(message="Loading", duration=2):
        spinner_chars = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        start_time = time.time()
        i = 0
        while time.time() - start_time < duration:
            char = spinner_chars[i % len(spinner_chars)]
            spinner_text = f"{char} {message}..."
            print(f"\r{spinner_text}", end="", flush=True)
            time.sleep(0.1)
            i += 1
        clear_length = len(message) + 10
        print(f"\r{' ' * clear_length}\r", end="", flush=True)

try:
    from quotes_loader import get_random_quote, format_quote
except ImportError:
    sys.stderr.write("Warning: quotes_loader module not found. Using fallback quotes.\n")
    
    def get_random_quote():
        fallback_quotes = [
            {"text": "Code is like humor. When you have to explain it, it's bad.", "author": "Cory House"},
            {"text": "First, solve the problem. Then, write the code.", "author": "John Johnson"},
            {"text": "Make it work, make it right, make it fast.", "author": "Kent Beck"}
        ]
        return random.choice(fallback_quotes)
    
    def format_quote(quote):
        return f'"{quote["text"]}"\n\n— {quote["author"]}'


# System info functions
def get_system_info():
    try:
        cpu_count = os.cpu_count() or 1
        return f"CPU: {cpu_count} cores"
    except:
        return "CPU: Unknown"


def display_system_info():
    info = get_system_info()
    system_box = f"""
🖥️  Local System:
{info}
🐍 Python: {platform.python_version()}
💻 Platform: {platform.system()} {platform.release()}
"""
    create_box(system_box, "🖥️  SYSTEM CAPABILITIES")


# 1. Configuration for the auto-shutdown mechanism.
# Container will shut down if no one is connected via SSH for this many seconds.
IDLE_TIMEOUT_SECONDS = 300  # 5 minutes

# 2. Define base images.
# Standard image for CPU-only tasks.
standard_devbox_image = (
    modal.Image.debian_slim(python_version="3.10")
    .apt_install(
        "openssh-server",
        "clang",
        "cmake",
        "htop",
        "nano",
        "git",
        "neovim",
        "curl",
        "wget",
        "unzip",
        "procps",
        "zlib1g-dev",
        "build-essential",
        "pkg-config",
        "python3-dev",
    )  # Good default tools
    .run_commands(
        "mkdir -p /root/.ssh",
        "chmod 700 /root/.ssh",
        "touch /root/.ssh/authorized_keys",
        "chmod 600 /root/.ssh/authorized_keys",
        "mkdir -p /var/run/sshd",
    )
)

# CUDA image for GPU tasks, based on an official NVIDIA image.
cuda_devbox_image = (
    modal.Image.from_registry("nvidia/cuda:12.1.1-devel-ubuntu22.04", add_python="3.11")
    .apt_install(
        "openssh-server",
        "git",
        "neovim",
        "curl",
        "wget",
        "unzip",
        "procps",
        "zlib1g-dev",
        "build-essential",
        "htop",
        "pkg-config",
        "python3-dev",
        "libcudnn9-cuda-12",
        "libcudnn9-dev-cuda-12",
        "nano",  # Specify CUDA 12 version for cuDNN
    )
    .run_commands(
        "mkdir -p /root/.ssh",
        "chmod 700 /root/.ssh",
        "touch /root/.ssh/authorized_keys",
        "chmod 600 /root/.ssh/authorized_keys",
        "mkdir -p /var/run/sshd",
    )
)

# NEW: Define a dedicated image for document processing with Pandoc and LaTeX.
# This is a larger image but avoids lengthy installs on startup.
doc_processing_image = (
    modal.Image.debian_slim()
    .apt_install(
        "openssh-server",
        "git",
        "procps",
        "pandoc",  # The document converter
        "texlive-full",  # A comprehensive LaTeX distribution for high-quality PDFs
    )
    .run_commands(
        "mkdir -p /root/.ssh",
        "chmod 700 /root/.ssh",
        "touch /root/.ssh/authorized_keys",
        "chmod 600 /root/.ssh/authorized_keys",
        "mkdir -p /var/run/sshd",
    )
)

# NEW: Define a dedicated image for the Gemini CLI.
gemini_cli_image = (
    modal.Image.debian_slim()
    .apt_install(
        "openssh-server",
        "git",
        "htop",
        "curl",
        "wget",
        "unzip",
        "procps",
        "nano",
        "neovim",
    )
    .run_commands(
        # Install Node.js 20.x from NodeSource
        "curl -fsSL https://deb.nodesource.com/setup_20.x | bash -",
        "apt-get install -y nodejs",
        # Install Gemini CLI globally
        "npm install -g @google/gemini-cli",
        # Install OpenCode
        "curl -fsSL https://opencode.ai/install | bash",
        # Standard SSH setup
        "mkdir -p /root/.ssh",
        "chmod 700 /root/.ssh",
        "touch /root/.ssh/authorized_keys",
        "chmod 600 /root/.ssh/authorized_keys",
        "mkdir -p /var/run/sshd",
        "mkdir -p /root/.gemini/",
        "chmod +x /root/.gemini/",
    )
)

# NEW: Define a dedicated image for the LLM Playroom with Ollama.
llm_playroom_image = (
    modal.Image.debian_slim(python_version="3.10")
    .apt_install([
        "openssh-server", "curl", "wget", "unzip", "procps", "nano", "neovim",
        "pciutils", "lshw"  # For GPU detection in Ollama (pciutils provides lspci)
    ])
    .run_commands([
        "curl -fsSL https://ollama.ai/install.sh | sh",
        "mkdir -p /root/.ssh && chmod 700 /root/.ssh",
        "touch /root/.ssh/authorized_keys && chmod 600 /root/.ssh/authorized_keys",
        "mkdir -p /var/run/sshd",

    ])
)

# NEW: Define a dedicated image for RDP Desktop access with XFCE.
rdp_devbox_image = (
    modal.Image.debian_slim(python_version="3.10")
    .apt_install([
        # RDP Server & Desktop Environment
        "xrdp", "xfce4", "xfce4-goodies", "xorgxrdp",
        # Desktop Dependencies
        "dbus-x11", "xorg", "tightvncserver",
        # Development Tools (following standard pattern)
        "clang", "cmake", "htop", "nano", "git", "neovim",
        "curl", "wget", "unzip", "procps", "zlib1g-dev",
        "build-essential", "pkg-config", "python3-dev",
    ])
    .run_commands([
        # SSH setup (for potential admin access)
        "mkdir -p /root/.ssh",
        "chmod 700 /root/.ssh",
        "touch /root/.ssh/authorized_keys",
        "chmod 600 /root/.ssh/authorized_keys",
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
        # Set RDP password for root user (simple password for container use)
        "echo 'root:rdpaccess' | chpasswd",
    ])
)


app = modal.App(
    name="personal-devbox-launcher",
    # The base image is no longer attached to the app directly
)

# 2. Define the persistent Volume.
# This will be mounted in the container for persistent storage.
dev_volume = modal.Volume.from_name("my-dev-volume", create_if_missing=True)


# 3. The remote function now accepts a list of packages to install.
def run_devbox_shared(extra_packages: list[str] | None = None):
    """
    Shared logic for launching a personal development environment.
    Sets up public key, persistent dotfiles, installs packages, and runs sshd.
    Includes comprehensive backup of /root directory.
    """
    import os
    import shutil
    import subprocess
    import atexit

    # Inject your public key from the secret.
    pubkey = os.environ["PUBKEY"]
    # We use 'a' (append) mode to be safe, though it will be fresh on first run.
    with open("/root/.ssh/authorized_keys", "a") as f:
        if pubkey not in open("/root/.ssh/authorized_keys").read():
            f.write(pubkey + "\n")

    # --- Set up comprehensive persistent storage ---
    print("Setting up comprehensive persistence system...", file=sys.stderr)

    # Check for and restore previous full backup if available
    backup_file = "/data/root_full_backup.tar.gz"
    if os.path.exists(backup_file):
        print("Restoring previous session data...", file=sys.stderr)
        try:
            # Clean current /root directory (preserve only essential system files)
            subprocess.run([
                "find", "/root", "-mindepth", "1", "-maxdepth", "1",
                "!", "-name", "lost+found",
                "-exec", "rm", "-rf", "{}", "+"
            ], check=False)

            # Extract the full backup
            subprocess.run([
                "tar", "-xzf", backup_file, "-C", "/"
            ], check=True)

            print("Session data restored successfully!", file=sys.stderr)

        except Exception as e:
            print(f"Warning: Restore failed - {e}, continuing with clean environment", file=sys.stderr)

    # We create a directory on the persistent volume to store the real files.
    persistent_storage_dir = "/data/.config_persistence"
    os.makedirs(persistent_storage_dir, exist_ok=True)

    items_to_persist = [
        # Critical configs (immediate symlinks for performance)
        ".bash_history",
        ".bashrc",
        ".profile",
        ".viminfo",
        ".vimrc",
        ".gitconfig",
        ".ssh/config",
        ".ssh/known_hosts",

        # Application data directories
        ".local",
        ".config",
        ".vscode",
        ".vscode-insiders",
        ".npm",
        ".gemini",
        ".ollama",
        ".docker",
        ".kube",
        ".aws",
        ".azure",

        # User content directories
        "Desktop",
        "Documents",
        "Downloads",
        "Pictures",
        "Videos",
        "Music",

        # Development workspaces
        "workspace",
        "projects",
        "code",
        "repos",
        "work",

        # Browser data
        ".mozilla",
        ".google-chrome",
        ".chromium",

        # IDE and editor configs
        ".jetbrains",
        ".eclipse",
        ".atom",
        ".sublime-text",

        # Package manager caches and configs
        ".yarn",
        ".pip",
        ".cargo",
        ".rustup",
    ]

    for item in items_to_persist:
        home_path = f"/root/{item}"
        volume_path = f"{persistent_storage_dir}/{item}"

        # Ensure parent directory of the link exists in the home directory (e.g., /root/.ssh).
        # The base image already creates /root/.ssh, but this makes it more robust.
        os.makedirs(os.path.dirname(home_path), exist_ok=True)

        # Ensure parent directory for the target file exists on the volume.
        os.makedirs(os.path.dirname(volume_path), exist_ok=True)

        # If a default file/dir exists at the destination in the container, remove it
        # to allow the symlink to be created.
        if os.path.lexists(home_path):
            if os.path.isdir(home_path) and not os.path.islink(home_path):
                shutil.rmtree(home_path)
            else:
                os.remove(home_path)

        # Create the symbolic link from the home directory to the persistent volume.
        os.symlink(volume_path, home_path)
        print(f"  - Linked {home_path} -> {volume_path}", file=sys.stderr)

    print("...done linking files.", file=sys.stderr)
    # --- End of persistence setup ---

    # Register comprehensive backup on shutdown
    def create_root_backup():
        """Create comprehensive backup of /root directory on shutdown."""
        try:
            print("Creating comprehensive /root backup...", file=sys.stderr)
            backup_file = "/data/root_full_backup.tar.gz"

            # Create compressed backup of entire /root directory
            # Minimal exclusions to preserve everything
            subprocess.run([
                "tar", "-czf", backup_file,
                "--exclude=lost+found",  # System directory
                "-C", "/root", "."
            ], check=True, capture_output=True)

            print(f"Backup saved to {backup_file}", file=sys.stderr)

        except Exception as e:
            print(f"Warning: Backup failed - {e}", file=sys.stderr)

    # Register the backup function to run on exit
    atexit.register(create_root_backup)

    # 4. Dynamically install requested tools.
    if extra_packages:
        print(
            f"Installing extra packages: {', '.join(extra_packages)}...",
            file=sys.stderr,
        )
        # It's good practice to update apt lists before installing.
        update_cmd = ["apt-get", "update"]
        install_cmd = ["apt-get", "install", "-y"] + extra_packages

        subprocess.run(update_cmd, check=True)
        subprocess.run(install_cmd, check=True)
        print("Extra packages installed.", file=sys.stderr)

    # Start the SSH daemon.
    subprocess.run(["/usr/sbin/sshd"])

    # Forward the SSH port and print the connection command.
    with modal.forward(22, unencrypted=True) as tunnel:
        ssh_command = f"ssh root@{tunnel.host} -p {tunnel.unencrypted_port}"
        print("\n🚀 Your DevBox is ready!", file=sys.stderr)
        print("Paste this command into your terminal:\n", file=sys.stderr)
        print(ssh_command)

        idle_time = 0
        check_interval = 15
        print(
            f"\nContainer will shut down after {IDLE_TIMEOUT_SECONDS // 60} minutes of inactivity.",
            file=sys.stderr,
        )

        # Loop to check for active connections
        while idle_time < IDLE_TIMEOUT_SECONDS:
            time.sleep(check_interval)
            # Check for active SSH user sessions.
            result = subprocess.run(
                "ps -ef | grep 'sshd: root@' | grep -v grep",
                shell=True,
                capture_output=True,
            )

            if result.stdout:  # If there is any output, a user is connected.
                idle_time = 0  # Reset the idle timer.
            else:
                idle_time += check_interval
                remaining = IDLE_TIMEOUT_SECONDS - idle_time
                print(
                    f"No active SSH connection. Shutting down in {remaining}s...",
                    file=sys.stderr,
                    end="\r",
                )

        print(
            f"\nIdle timeout of {IDLE_TIMEOUT_SECONDS}s reached. Shutting down instance.",
            file=sys.stderr,
        )


def run_rdp_devbox_shared(extra_packages: list[str] = None):
    """
    Shared logic for launching an RDP desktop development environment.
    Sets up public key, persistent dotfiles, installs packages, and runs RDP server.
    Includes comprehensive backup of /root directory.
    """
    import os
    import shutil
    import subprocess
    import sys
    import time
    import atexit

    # Inject your public key from the secret (for potential SSH fallback).
    pubkey = os.environ["PUBKEY"]
    with open("/root/.ssh/authorized_keys", "a") as f:
        if pubkey not in open("/root/.ssh/authorized_keys").read():
            f.write(pubkey + "\n")

    # --- Set up persistent dotfiles and desktop configs using symbolic links ---
    print("Linking persistent configuration files...", file=sys.stderr)

    persistent_storage_dir = "/data/.config_persistence"
    os.makedirs(persistent_storage_dir, exist_ok=True)

    items_to_persist = [
        # Terminal configs (same as SSH boxes)
        ".bash_history",
        ".bashrc",
        ".profile",
        ".viminfo",
        ".vimrc",
        ".gitconfig",
        ".ssh/config",
        ".ssh/known_hosts",
        # Desktop-specific configs
        ".config/xfce4",
        ".local/share/xfce4",
        ".cache/sessions",
        "Desktop",
        ".xsession",
    ]

    for item in items_to_persist:
        home_path = f"/root/{item}"
        volume_path = f"{persistent_storage_dir}/{item}"

        # Ensure parent directory of the link exists in the home directory
        os.makedirs(os.path.dirname(home_path), exist_ok=True)

        # Ensure parent directory for the target file exists on the volume
        os.makedirs(os.path.dirname(volume_path), exist_ok=True)

        # If a default file/dir exists at the destination, remove it to allow the symlink
        if os.path.lexists(home_path):
            if os.path.isdir(home_path) and not os.path.islink(home_path):
                shutil.rmtree(home_path)
            else:
                os.remove(home_path)

        # Create the symbolic link from the home directory to the persistent volume
        os.symlink(volume_path, home_path)
        print(f"  - Linked {home_path} -> {volume_path}", file=sys.stderr)

    print("...done linking files.", file=sys.stderr)
    # --- End of persistence setup ---

    # Register comprehensive backup on shutdown
    def create_root_backup():
        """Create comprehensive backup of /root directory on shutdown."""
        try:
            print("Creating comprehensive /root backup...", file=sys.stderr)
            backup_file = "/data/root_full_backup.tar.gz"

            # Create compressed backup of entire /root directory
            # Minimal exclusions to preserve everything
            subprocess.run([
                "tar", "-czf", backup_file,
                "--exclude=lost+found",  # System directory
                "-C", "/root", "."
            ], check=True, capture_output=True)

            print(f"Backup saved to {backup_file}", file=sys.stderr)

        except Exception as e:
            print(f"Warning: Backup failed - {e}", file=sys.stderr)

    # Register the backup function to run on exit
    atexit.register(create_root_backup)

    # Dynamically install requested tools
    if extra_packages:
        print(
            f"Installing extra packages: {', '.join(extra_packages)}...",
            file=sys.stderr,
        )
        update_cmd = ["apt-get", "update"]
        install_cmd = ["apt-get", "install", "-y"] + extra_packages

        subprocess.run(update_cmd, check=True)
        subprocess.run(install_cmd, check=True)
        print("Extra packages installed.", file=sys.stderr)

    # Start D-Bus daemon for xfconfd (critical for XFCE)
    subprocess.Popen(["dbus-daemon", "--system", "--fork"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # Clean potentially corrupted XFCE config directories
    subprocess.run(["rm", "-rf", "/root/.config/xfce4"], check=False)
    subprocess.run(["rm", "-rf", "/root/.cache/sessions"], check=False)
    subprocess.run(["mkdir", "-p", "/root/.config/xfce4"], check=True)
    subprocess.run(["mkdir", "-p", "/root/.cache/sessions"], check=True)

    # Set proper permissions
    subprocess.run(["chown", "-R", "root:root", "/root/.config"], check=False)
    subprocess.run(["chown", "-R", "root:root", "/root/.cache"], check=False)

    # Set up XDG environment variables for XFCE
    os.environ.setdefault('XDG_CONFIG_DIRS', '/etc/xdg')
    os.environ.setdefault('XDG_DATA_DIRS', '/usr/local/share:/usr/share')
    os.environ.setdefault('XDG_RUNTIME_DIR', '/tmp/xdg-runtime')

    # Ensure runtime directory exists
    os.makedirs('/tmp/xdg-runtime', exist_ok=True)
    os.chmod('/tmp/xdg-runtime', 0o700)

    # Start the RDP service (direct daemon startup for containers)
    # Start both xrdp daemon and session manager in background
    subprocess.Popen(["/usr/sbin/xrdp"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.Popen(["/usr/sbin/xrdp-sesman"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # Forward the RDP port and print the connection command
    with modal.forward(3389, unencrypted=True) as tunnel:
        rdp_address = f"{tunnel.host}:{tunnel.unencrypted_port}"
        print("\n🖥️ Your RDP Desktop is ready!", file=sys.stderr)
        print("Connect using any RDP client (Windows Remote Desktop, Remmina, etc.):", file=sys.stderr)
        print(f"Address: {rdp_address}", file=sys.stderr)
        print("Username: root", file=sys.stderr)
        print("Password: rdpaccess", file=sys.stderr)

        idle_time = 0
        check_interval = 15
        print(
            f"\nContainer will shut down after {IDLE_TIMEOUT_SECONDS // 60} minutes of inactivity.",
            file=sys.stderr,
        )

        # Loop to check for active RDP connections
        while idle_time < IDLE_TIMEOUT_SECONDS:
            time.sleep(check_interval)

            # Check for active RDP sessions by looking for xrdp processes with connections
            # This is a simplified check - could be enhanced with more sophisticated session detection
            result = subprocess.run(
                "ps aux | grep -c 'xrdp-sesman.*:' | grep -v grep",
                shell=True,
                capture_output=True,
                text=True
            )

            try:
                active_sessions = int(result.stdout.strip())
                if active_sessions > 0:  # If there are active RDP sessions
                    idle_time = 0  # Reset the idle timer
                else:
                    idle_time += check_interval
                    remaining = IDLE_TIMEOUT_SECONDS - idle_time
                    print(
                        f"No active RDP connection. Shutting down in {remaining}s...",
                        file=sys.stderr,
                        end="\r",
                    )
            except (ValueError, AttributeError):
                # If we can't parse the output, assume no active sessions
                idle_time += check_interval
                remaining = IDLE_TIMEOUT_SECONDS - idle_time
                print(
                    f"No active RDP connection. Shutting down in {remaining}s...",
                    file=sys.stderr,
                    end="\r",
                )

        print(
            f"\nIdle timeout of {IDLE_TIMEOUT_SECONDS}s reached. Shutting down RDP Desktop.",
            file=sys.stderr,
        )


# Common arguments for the devbox functions
cpu_devbox_args = dict(
    secrets=[modal.Secret.from_name("ssh-public-key")],
    volumes={"/data": dev_volume},
    cpu=0.5,
    memory=1024,
    timeout=3600,
)

gpu_devbox_args = dict(
    secrets=[modal.Secret.from_name("ssh-public-key")],
    volumes={"/data": dev_volume},
    cpu=1.0,
    memory=2048,
    timeout=28800,
)

# RDP-specific resource arguments (higher resources for desktop environment)
cpu_devbox_args_rdp = dict(
    secrets=[modal.Secret.from_name("ssh-public-key")],
    volumes={"/data": dev_volume},
    cpu=1.0,  # Higher CPU for desktop environment
    memory=2048,  # Double memory for XFCE + RDP
    timeout=3600,
)

gpu_devbox_args_rdp = dict(
    secrets=[modal.Secret.from_name("ssh-public-key")],
    volumes={"/data": dev_volume},
    cpu=1.5,  # Higher CPU for GPU + desktop
    memory=4096,  # Higher memory for GPU + desktop
    timeout=28800,
)


@app.function(
    image=standard_devbox_image,
    secrets=[modal.Secret.from_name("ssh-public-key")],
    volumes={"/data": dev_volume},
    cpu=0.5,
    memory=1024,
    timeout=3600,
)
def launch_devbox(extra_packages: list[str] | None = None):
    """Launches a non-GPU personal development environment."""
    run_devbox_shared(extra_packages)


@app.function(image=cuda_devbox_image, gpu="t4", **gpu_devbox_args)
def launch_devbox_t4(extra_packages: list[str] | None = None):
    """Launches a T4 GPU-powered personal development environment."""
    run_devbox_shared(extra_packages)


@app.function(image=cuda_devbox_image, gpu="l4", **gpu_devbox_args)
def launch_devbox_l4(extra_packages: list[str] | None = None):
    """Launches an L4 GPU-powered personal development environment."""
    run_devbox_shared(extra_packages)


@app.function(image=cuda_devbox_image, gpu="a10g", **gpu_devbox_args)
def launch_devbox_a10g(extra_packages: list[str] | None = None):
    """Launches an A10G GPU-powered personal development environment."""
    run_devbox_shared(extra_packages)


# NEW: Add a dedicated function for the document processing environment.
@app.function(
    image=doc_processing_image,  # Use the new, dedicated image
    secrets=[modal.Secret.from_name("ssh-public-key")],
    volumes={"/data": dev_volume},
    cpu=1,  # More CPU for potentially heavy pandoc jobs
    memory=4096,  # More memory for texlive
    timeout=28000,
)
def launch_doc_processor():
    """
    Launches a dev environment specifically for document processing.
    Pandoc and a full TeX Live distribution are pre-installed.
    """
    import os

    # Inject your public key from the secret.
    pubkey = os.environ["PUBKEY"]
    with open("/root/.ssh/authorized_keys", "a") as f:
        if pubkey not in open("/root/.ssh/authorized_keys").read():
            f.write(pubkey + "\n")

    # Start the SSH daemon.
    subprocess.run(["/usr/sbin/sshd"])

    # Forward the SSH port and print the connection command.
    with modal.forward(22, unencrypted=True) as tunnel:
        ssh_command = f"ssh root@{tunnel.host} -p {tunnel.unencrypted_port}"
        print("\n📄 Your Document Processing Box is ready!", file=sys.stderr)
        print("It comes with Pandoc and a full TeX Live installation.", file=sys.stderr)
        print("Paste this command into your terminal:\n", file=sys.stderr)
        print(ssh_command)

        idle_time = 0
        check_interval = 15
        print(
            f"\nContainer will shut down after {IDLE_TIMEOUT_SECONDS // 60} minutes of inactivity.",
            file=sys.stderr,
        )

        # Loop to check for active connections
        while idle_time < IDLE_TIMEOUT_SECONDS:
            time.sleep(check_interval)
            result = subprocess.run(
                "ps -ef | grep 'sshd: root@' | grep -v grep",
                shell=True,
                capture_output=True,
            )

            if result.stdout:
                idle_time = 0
            else:
                idle_time += check_interval
                remaining = IDLE_TIMEOUT_SECONDS - idle_time
                print(
                    f"No active SSH connection. Shutting down in {remaining}s...",
                    file=sys.stderr,
                    end="\r",
                )

        print(
            f"\nIdle timeout of {IDLE_TIMEOUT_SECONDS}s reached. Shutting down instance.",
            file=sys.stderr,
        )


# NEW: Add a dedicated function for the Gemini CLI environment.
@app.function(
    image=gemini_cli_image,  # Use the new, dedicated image
    secrets=[
        modal.Secret.from_name("ssh-public-key"),
        modal.Secret.from_name("gemini-api-key"),  # New secret for Gemini API key
    ],
    volumes={"/data": dev_volume},
    cpu=0.5,
    memory=1024,
    timeout=28800,
)
def launch_gemini_cli_box():
    """
    Launches a dev environment specifically for the Gemini CLI.
    Gemini CLI is pre-installed, and configuration is persisted.
    """
    import os
    import shutil

    # Inject your public key from the secret.
    pubkey = os.environ["PUBKEY"]
    with open("/root/.ssh/authorized_keys", "a") as f:
        if pubkey not in open("/root/.ssh/authorized_keys").read():
            f.write(pubkey + "\n")

    # --- Set up persistent dotfiles and .gemini config using symbolic links ---
    print("Linking persistent configuration files...", file=sys.stderr)

    persistent_storage_dir = "/data/.config_persistence"
    os.makedirs(persistent_storage_dir, exist_ok=True)

    items_to_persist = [
        ".bash_history",
        ".bashrc",
        ".opentrader",
        ".opencode",
        ".profile",
        ".viminfo",
        ".vimrc",
        ".gitconfig",
        ".ssh/config",
        ".ssh/known_hosts",
        # Gemini CLI specific persistence: symlink the entire directory
        ".gemini",
    ]

    for item in items_to_persist:
        home_path = f"/root/{item}"
        volume_path = f"{persistent_storage_dir}/{item}"

        os.makedirs(os.path.dirname(home_path), exist_ok=True)
        os.makedirs(os.path.dirname(volume_path), exist_ok=True)

        if os.path.lexists(home_path):
            if os.path.isdir(home_path) and not os.path.islink(home_path):
                shutil.rmtree(home_path)
            else:
                os.remove(home_path)

        os.symlink(volume_path, home_path)
        print(f"  - Linked {home_path} -> {volume_path}", file=sys.stderr)

    print("...done linking files.", file=sys.stderr)
    # --- End of persistence setup ---

    # Set GEMINI_API_KEY environment variable from Modal Secret
    # The secret is already attached, so it's available in os.environ
    # No explicit action needed here, as gemini-cli will pick it up.

    # Start the SSH daemon.
    subprocess.run(["/usr/sbin/sshd"])

    # Forward the SSH port and print the connection command.
    with modal.forward(22, unencrypted=True) as tunnel:
        ssh_command = f"ssh root@{tunnel.host} -p {tunnel.unencrypted_port}"
        print("\n✨ Your Gemini CLI Box is ready!", file=sys.stderr)
        print("Gemini CLI is pre-installed and configured.", file=sys.stderr)
        print("Paste this command into your terminal:\n", file=sys.stderr)
        print(ssh_command)

        idle_time = 0
        check_interval = 15
        print(
            f"\nContainer will shut down after {IDLE_TIMEOUT_SECONDS // 60} minutes of inactivity.",
            file=sys.stderr,
        )

        # Loop to check for active connections
        while idle_time < IDLE_TIMEOUT_SECONDS:
            time.sleep(check_interval)
            result = subprocess.run(
                "ps -ef | grep 'sshd: root@' | grep -v grep",
                shell=True,
                capture_output=True,
            )

            if result.stdout:
                idle_time = 0
            else:
                idle_time += check_interval
                remaining = IDLE_TIMEOUT_SECONDS - idle_time
                print(
                    f"No active SSH connection. Shutting down in {remaining}s...",
                    file=sys.stderr,
                    end="\r",
                )

        print(
            f"\nIdle timeout of {IDLE_TIMEOUT_SECONDS}s reached. Shutting down instance.",
            file=sys.stderr,
        )


# NEW: LLM Playroom with Ollama and DeepSeek R1
@app.function(
    image=llm_playroom_image,
    secrets=[modal.Secret.from_name("ssh-public-key")],
    volumes={"/data": dev_volume},
    gpu="L40S",
    cpu=1.0,
    memory=4096,
    timeout=600,  # 10 minutes max
    enable_memory_snapshot=True,
    experimental_options={"enable_gpu_snapshot": True},  # Enable GPU snapshots for sub-second cold starts
)
def launch_llm_playroom():
    """
    Launches a dev environment specifically for the LLM Playroom with Ollama and DeepSeek R1.
    """
    import os
    import shutil

    # Inject your public key from the secret.
    pubkey = os.environ["PUBKEY"]
    with open("/root/.ssh/authorized_keys", "a") as f:
        if pubkey not in open("/root/.ssh/authorized_keys").read():
            f.write(pubkey + "\n")

    # --- Set up persistent dotfiles using symbolic links ---
    print("Linking persistent configuration files...", file=sys.stderr)

    persistent_storage_dir = "/data/.config_persistence"
    os.makedirs(persistent_storage_dir, exist_ok=True)

    items_to_persist = [
        ".bash_history",
        ".bashrc",
        ".profile",
        ".viminfo",
        ".vimrc",
        ".gitconfig",
        ".ssh/config",
        ".ssh/known_hosts",
    ]

    for item in items_to_persist:
        home_path = f"/root/{item}"
        volume_path = f"{persistent_storage_dir}/{item}"

        os.makedirs(os.path.dirname(home_path), exist_ok=True)
        os.makedirs(os.path.dirname(volume_path), exist_ok=True)

        if os.path.lexists(home_path):
            if os.path.isdir(home_path) and not os.path.islink(home_path):
                shutil.rmtree(home_path)
            else:
                os.remove(home_path)

        os.symlink(volume_path, home_path)
        print(f"  - Linked {home_path} -> {volume_path}", file=sys.stderr)

    print("...done linking files.", file=sys.stderr)

    # Start the SSH daemon.
    subprocess.run(["/usr/sbin/sshd"])

    # Forward the SSH port and print the connection command.
    with modal.forward(22, unencrypted=True) as tunnel:
        ssh_command = f"ssh root@{tunnel.host} -p {tunnel.unencrypted_port}"
        print("\n🧠 Your LLM Playroom is ready!", file=sys.stderr)
        print("🚀 GPU: NVIDIA L40S detected - ready for AI workloads", file=sys.stderr)
        print("📝 To get started:", file=sys.stderr)
        print("   1. Connect via SSH below", file=sys.stderr)
        print("   2. Run: ollama pull deepseek-r1:8b (first time only)", file=sys.stderr)
        print("   3. Run: ollama run deepseek-r1:8b", file=sys.stderr)
        print("⏰ Auto-shutdown: 2min idle, 10min max session", file=sys.stderr)
        print("\n" + "="*50, file=sys.stderr)
        print("SSH Command:", file=sys.stderr)
        print(ssh_command, file=sys.stderr)
        print("="*50, file=sys.stderr)

        # Start Ollama server after printing SSH command
        subprocess.run(["ollama", "serve"], check=True)

        idle_time = 0
        check_interval = 15
        idle_timeout = 120  # 2 minutes for playroom

        while idle_time < idle_timeout:
            time.sleep(check_interval)
            result = subprocess.run(
                "ps -ef | grep 'sshd: root@' | grep -v grep",
                shell=True,
                capture_output=True,
            )

            if result.stdout:
                idle_time = 0
            else:
                idle_time += check_interval
                remaining = idle_timeout - idle_time
                print(
                    f"No active SSH connection. Shutting down in {remaining}s...",
                    file=sys.stderr,
                    end="\r",
                )

        print(
            f"\n⏰ Session ended - idle timeout ({idle_timeout}s) reached.", file=sys.stderr
        )
        print("💰 Cost saved by auto-shutdown! Thanks for using LLM Playroom.", file=sys.stderr)
        import os
        import shutil

        # Inject your public key from the secret.
        pubkey = os.environ["PUBKEY"]
        with open("/root/.ssh/authorized_keys", "a") as f:
            if pubkey not in open("/root/.ssh/authorized_keys").read():
                f.write(pubkey + "\n")

        # --- Set up persistent dotfiles using symbolic links ---
        print("Linking persistent configuration files...", file=sys.stderr)

        persistent_storage_dir = "/data/.config_persistence"
        os.makedirs(persistent_storage_dir, exist_ok=True)

    items_to_persist = [
        ".bash_history",
        ".bashrc",
        ".profile",
        ".viminfo",
        ".vimrc",
        ".gitconfig",
        ".ssh/config",
        ".ssh/known_hosts",
        ".ollama",  # Persistent Ollama models and config
    ]

    for item in items_to_persist:
        home_path = f"/root/{item}"
        volume_path = f"{persistent_storage_dir}/{item}"

        os.makedirs(os.path.dirname(home_path), exist_ok=True)
        os.makedirs(os.path.dirname(volume_path), exist_ok=True)

        if os.path.lexists(home_path):
            if os.path.isdir(home_path) and not os.path.islink(home_path):
                shutil.rmtree(home_path)
            else:
                os.remove(home_path)

        os.symlink(volume_path, home_path)
        print(f"  - Linked {home_path} -> {volume_path}", file=sys.stderr)

        print("...done linking files.", file=sys.stderr)

        # Start the SSH daemon.
        subprocess.run(["/usr/sbin/sshd"])

        # Forward the SSH port and print the connection command.
        with modal.forward(22, unencrypted=True) as tunnel:
            ssh_command = f"ssh root@{tunnel.host} -p {tunnel.unencrypted_port}"
            print("\n🧠 Your LLM Playroom is ready!", file=sys.stderr)
            print("DeepSeek R1 (8B distilled) is loaded and ready.", file=sys.stderr)
            print("Paste this command into your terminal:\n", file=sys.stderr)
            print(ssh_command)

            idle_time = 0
            check_interval = 15
            idle_timeout = 120  # 2 minutes for playroom

            while idle_time < idle_timeout:
                time.sleep(check_interval)
                result = subprocess.run(
                    "ps -ef | grep 'sshd: root@' | grep -v grep",
                    shell=True,
                    capture_output=True,
                )

                if result.stdout:
                    idle_time = 0
                else:
                    idle_time += check_interval
                    remaining = idle_timeout - idle_time
                    print(
                        f"No active SSH connection. Shutting down in {remaining}s...",
                        file=sys.stderr,
                        end="\r",
                    )

        print(
            f"\nIdle timeout of {idle_timeout}s reached. Shutting down instance.",
            file=sys.stderr,
        )


# NEW: RDP Desktop launch functions
@app.function(image=rdp_devbox_image, **cpu_devbox_args_rdp)
def launch_rdp_devbox(extra_packages: list[str] = None):
    """Launches an RDP desktop development environment."""
    run_rdp_devbox_shared(extra_packages)


@app.function(image=rdp_devbox_image, gpu="t4", **gpu_devbox_args_rdp)
def launch_rdp_devbox_t4(extra_packages: list[str] = None):
    """Launches an RDP desktop with T4 GPU."""
    run_rdp_devbox_shared(extra_packages)


@app.function(image=rdp_devbox_image, gpu="l4", **gpu_devbox_args_rdp)
def launch_rdp_devbox_l4(extra_packages: list[str] = None):
    """Launches an RDP desktop with L4 GPU."""
    run_rdp_devbox_shared(extra_packages)


@app.function(image=rdp_devbox_image, gpu="a10g", **gpu_devbox_args_rdp)
def launch_rdp_devbox_a10g(extra_packages: list[str] = None):
    """Launches an RDP desktop with A10G GPU."""
    run_rdp_devbox_shared(extra_packages)


# 5. A single, menu-driven local entrypoint.
@app.local_entrypoint()
def main():
    """
    Enhanced interactive menu for launching DevBox templates with fun UI elements.
    """
    # Welcome screen
    print()
    logo = """
╔══════════════════════════════════════════════════════════╗
║                                                          ║
║            🚀  MODAL DEVBOX LAUNCHER  🚀                ║
║                                                          ║
║              "Code in the Cloud, Anytime!"               ║
║                                                          ║
╚══════════════════════════════════════════════════════════╝
"""
    print(logo)

    # Show a random quote
    quote = get_random_quote()
    quote_box = format_quote(quote)
    create_box(quote_box, "💭 Programming Wisdom")

    # Display system info
    display_system_info()

    # Enhanced menu
    menu_box = """
🎯 Choose your DevBox:

1. 🛠️  Standard DevBox
    General purpose development environment
    with optional extra packages

2. 📄 Document Processing Box
    Pandoc + Full TeX Live for document work

3. 🤖 AI Assistants Box
    Includes OpenCode and Gemini CLI

4. 🧠 LLM Playroom
    Ollama with DeepSeek R1 for AI experimentation

5. 🖥️  RDP Desktop Box
    Full graphical desktop with XFCE and RDP access
"""
    create_box(menu_box, "🚀 LAUNCH OPTIONS")

    try:
        choice = input("Enter your choice (1-5): ").strip()
    except EOFError:
        print("\nNo input received. Exiting.")
        return

    if choice == "1":
        # Enhanced Standard DevBox Logic
        print()
        package_box = """
📦 Want to install additional tools?

Examples: htop tmux git neovim curl wget
(leave empty for default setup)
"""
        create_box(package_box, "🛠️  EXTRA PACKAGES")

        try:
            tools_input = input("Enter tools (space-separated): ").strip()
        except EOFError:
            tools_input = ""

        package_list = tools_input.split() if tools_input else []

        # Replace 'python' with 'python-is-python3' for compatibility.
        if "python" in package_list:
            package_list[package_list.index("python")] = "python-is-python3"
            print(
                "🔄 Replaced 'python' with 'python-is-python3' for Debian compatibility."
            )

        if package_list:
            print(f"✅ Requesting with additional tools: {', '.join(package_list)}")
        else:
            print("✅ No extra tools requested.")

        # GPU selection with enhanced UI
        gpu_box = """
🎮 Add GPU acceleration?

• T4: Cost-effective, good for inference
• L4: Newer, more performant than T4
• A10G: Higher performance, more VRAM

(Enter 'y' for GPU options, anything else for CPU-only)
"""
        create_box(gpu_box, "⚡ GPU ACCELERATION")

        try:
            gpu_choice = input("Attach GPU? (y/n): ").lower().strip()
        except EOFError:
            gpu_choice = "n"

        if gpu_choice == "y":
            gpu_menu = """
1. 🎯 T4 GPU (Cost-effective, good for inference)
2. 🚀 L4 GPU (Newer, more performant than T4)
3. 💪 A10G GPU (Higher performance, more VRAM)
"""
            create_box(gpu_menu, "🎮 SELECT GPU TYPE")

            try:
                gpu_type_choice = input("Choose GPU (1-3): ").strip()
            except EOFError:
                print("\nNo input received. Exiting.")
                return

            gpu_types = {
                "1": ("T4", launch_devbox_t4),
                "2": ("L4", launch_devbox_l4),
                "3": ("A10G", launch_devbox_a10g),
            }

            if gpu_type_choice in gpu_types:
                gpu_name, launch_func = gpu_types[gpu_type_choice]
                print()
                gpu_launch_box = f"""
🎯 Launching with {gpu_name} GPU...
⚡ Get ready for some serious computing power!
"""
                create_box(gpu_launch_box, f"🚀 {gpu_name} POWERED")
                show_spinner("Initializing GPU environment", 2)
                launch_func.remote(extra_packages=package_list)
            else:
                print("❌ Invalid GPU choice. Please run again.")
                return
        else:
            print()
            cpu_box = """
🖥️  Launching CPU-only environment...
💪 Ready for development work!
"""
            create_box(cpu_box, "🚀 STANDARD DEVBOX")
            show_spinner("Preparing your DevBox", 2)
            launch_devbox.remote(extra_packages=package_list)

    elif choice == "2":
        print()
        doc_box = """
📄 Launching Document Processing Box...
📚 Pandoc + Full TeX Live Distribution
✨ Perfect for academic and technical writing!
"""
        create_box(doc_box, "📄 DOCUMENT PROCESSING")
        show_spinner("Setting up document tools", 2)
        launch_doc_processor.remote()

    elif choice == "3":  # New logic branch
        print()
        gemini_box = """
🤖 Launching AI Assistants Box...
🧠 Includes OpenCode and Gemini CLI
🚀 Let's build something amazing together!
"""
        create_box(gemini_box, "🤖 AI ASSISTANTS")
        show_spinner("Initializing AI assistants", 2)
        launch_gemini_cli_box.remote()

    elif choice == "4":  # LLM Playroom
        print()
        llm_box = """
🧠 Launching LLM Playroom...
🤖 Ollama with DeepSeek R1 (8B distilled)
🚀 Ready for AI experimentation!
"""
        create_box(llm_box, "🧠 LLM PLAYROOM")
        show_spinner("Initializing LLM environment", 2)
        launch_llm_playroom.remote()

    elif choice == "5":  # RDP Desktop Box
        print()
        rdp_box = """
🖥️  Launching RDP Desktop Box...
🖼️  XFCE Desktop Environment + RDP Access
✨ Perfect for graphical development work!
"""
        create_box(rdp_box, "🖥️  RDP DESKTOP")
        show_spinner("Setting up desktop environment", 2)

        # Package installation for RDP (following existing pattern)
        package_box = """
📦 Want to install additional desktop tools?

Examples: firefox gedit vscode libreoffice
(leave empty for default XFCE setup)
"""
        create_box(package_box, "🖥️  EXTRA DESKTOP PACKAGES")

        try:
            tools_input = input("Enter desktop tools (space-separated): ").strip()
        except EOFError:
            tools_input = ""

        package_list = tools_input.split() if tools_input else []

        if package_list:
            print(f"✅ Requesting with additional tools: {', '.join(package_list)}")
        else:
            print("✅ No extra desktop tools requested.")

        # GPU selection for RDP (following existing pattern)
        gpu_box = """
🎮 Add GPU acceleration for desktop?

• T4: Cost-effective, good for graphics
• L4: Newer, more performant than T4
• A10G: Higher performance, more VRAM

(Enter 'y' for GPU options, anything else for CPU-only)
"""
        create_box(gpu_box, "⚡ GPU ACCELERATION")

        try:
            gpu_choice = input("Attach GPU? (y/n): ").lower().strip()
        except EOFError:
            gpu_choice = "n"

        if gpu_choice == "y":
            gpu_menu = """
1. 🎯 T4 GPU (Cost-effective, good for graphics)
2. 🚀 L4 GPU (Newer, more performant than T4)
3. 💪 A10G GPU (Higher performance, more VRAM)
"""
            create_box(gpu_menu, "🎮 SELECT GPU TYPE")

            try:
                gpu_type_choice = input("Choose GPU (1-3): ").strip()
            except EOFError:
                print("\nNo input received. Exiting.")
                return

            gpu_types = {
                "1": ("T4", launch_rdp_devbox_t4),
                "2": ("L4", launch_rdp_devbox_l4),
                "3": ("A10G", launch_rdp_devbox_a10g),
            }

            if gpu_type_choice in gpu_types:
                gpu_name, launch_func = gpu_types[gpu_type_choice]
                print()
                gpu_launch_box = f"""
🎯 Launching RDP Desktop with {gpu_name} GPU...
⚡ Get ready for accelerated graphics!
"""
                create_box(gpu_launch_box, f"🚀 {gpu_name} POWERED RDP")
                show_spinner("Initializing GPU RDP environment", 2)
                launch_func.remote(extra_packages=package_list)
            else:
                print("❌ Invalid GPU choice. Please run again.")
                return
        else:
            print()
            cpu_box = """
🖥️  Launching RDP Desktop (CPU-only)...
💻 Ready for graphical development work!
"""
            create_box(cpu_box, "🚀 RDP DESKTOP")
            show_spinner("Preparing your RDP Desktop", 2)
            launch_rdp_devbox.remote(extra_packages=package_list)

    else:
        error_box = """
❌ Invalid choice selected.

Please run the launcher again and choose:
• 1 for Standard DevBox
• 2 for Document Processing
• 3 for AI Assistants Box
• 4 for LLM Playroom
• 5 for RDP Desktop Box
"""
        create_box(error_box, "❌ ERROR")
