import modal
import subprocess
import sys
import time
import random
import platform
import os


# Simplified UI utilities - clean and reliable
def create_box(content, title="", width=60):
    """Create a bordered box around content."""
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
    """Simple spinner with visual feedback."""
    spinner_chars = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
    start_time = time.time()
    i = 0

    while time.time() - start_time < duration:
        char = spinner_chars[i % len(spinner_chars)]
        spinner_text = f"{char} {message}..."
        print(f"\r{spinner_text}", end="", flush=True)
        time.sleep(0.1)
        i += 1

    # Clear the spinner line
    clear_length = len(message) + 10
    print(f"\r{' ' * clear_length}\r", end="", flush=True)


# Programming quotes embedded
PROGRAMMING_QUOTES = [
    {
        "text": "First, solve the problem. Then, write the code.",
        "author": "John Johnson",
    },
    {
        "text": "The best error message is the one that never shows up.",
        "author": "Thomas Fuchs",
    },
    {
        "text": "Programs must be written for people to read, and only incidentally for machines to execute.",
        "author": "Harold Abelson",
    },
    {
        "text": "The only way to learn a new programming language is by writing programs in it.",
        "author": "Dennis Ritchie",
    },
    {
        "text": "Code is like humor. When you have to explain it, it's bad.",
        "author": "Cory House",
    },
    {"text": "Make it work, make it right, make it fast.", "author": "Kent Beck"},
    {
        "text": "The most disastrous thing that you can ever learn is your first programming language.",
        "author": "Alan Kay",
    },
]


def get_random_quote():
    return random.choice(PROGRAMMING_QUOTES)


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


app = modal.App(
    name="personal-devbox-launcher",
    # The base image is no longer attached to the app directly
)

# 2. Define the persistent Volume.
# This will be mounted in the container for persistent storage.
dev_volume = modal.Volume.from_name("my-dev-volume", create_if_missing=True)


# 3. The remote function now accepts a list of packages to install.
def run_devbox_shared(extra_packages: list[str] = None):
    """
    Shared logic for launching a personal development environment.
    Sets up public key, persistent dotfiles, installs packages, and runs sshd.
    """
    import os
    import shutil

    # Inject your public key from the secret.
    pubkey = os.environ["PUBKEY"]
    # We use 'a' (append) mode to be safe, though it will be fresh on first run.
    with open("/root/.ssh/authorized_keys", "a") as f:
        if pubkey not in open("/root/.ssh/authorized_keys").read():
            f.write(pubkey + "\n")

    # --- Set up persistent dotfiles using symbolic links ---
    print("Linking persistent configuration files...", file=sys.stderr)

    # We create a directory on the persistent volume to store the real files.
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


@app.function(image=standard_devbox_image, **cpu_devbox_args)
def launch_devbox(extra_packages: list[str] = None):
    """Launches a non-GPU personal development environment."""
    run_devbox_shared(extra_packages)


@app.function(image=cuda_devbox_image, gpu="t4", **gpu_devbox_args)
def launch_devbox_t4(extra_packages: list[str] = None):
    """Launches a T4 GPU-powered personal development environment."""
    run_devbox_shared(extra_packages)


@app.function(image=cuda_devbox_image, gpu="l4", **gpu_devbox_args)
def launch_devbox_l4(extra_packages: list[str] = None):
    """Launches an L4 GPU-powered personal development environment."""
    run_devbox_shared(extra_packages)


@app.function(image=cuda_devbox_image, gpu="a10g", **gpu_devbox_args)
def launch_devbox_a10g(extra_packages: list[str] = None):
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
    quote_box = f'"{quote["text"]}"\n\n— {quote["author"]}'
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
"""
    create_box(menu_box, "🚀 LAUNCH OPTIONS")

    try:
        choice = input("Enter your choice (1-3): ").strip()
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

    else:
        error_box = """
❌ Invalid choice selected.

Please run the launcher again and choose:
• 1 for Standard DevBox
• 2 for Document Processing
• 3 for AI Assistants Box
"""
        create_box(error_box, "❌ ERROR")
