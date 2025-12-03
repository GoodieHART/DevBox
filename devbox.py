import modal
import subprocess
import sys
import time

# 1. Configuration for the auto-shutdown mechanism.
# Container will shut down if no one is connected via SSH for this many seconds.
IDLE_TIMEOUT_SECONDS = 300  # 5 minutes

# 2. Define base images.
# Standard image for CPU-only tasks.
standard_devbox_image = (
    modal.Image.debian_slim()
    .apt_install("openssh-server", "git", "vim", "curl", "wget", "unzip", "procps", "zlib1g-dev", "build-essential", "pkg-config", "python3-dev")  # Good default tools
    .run_commands(
        "mkdir -p /root/.ssh",
        "chmod 700 /root/.ssh",
        "touch /root/.ssh/authorized_keys",
        "chmod 600 /root/.ssh/authorized_keys",
        "mkdir -p /var/run/sshd"
    )
)

# CUDA image for GPU tasks, based on an official NVIDIA image.
cuda_devbox_image = (
    modal.Image.from_registry("nvidia/cuda:12.1.1-devel-ubuntu22.04", add_python="3.11")
    .apt_install(
        "openssh-server", "git", "vim", "curl", "wget", "unzip", "procps", 
        "zlib1g-dev", "build-essential", "pkg-config", "python3-dev",
        "libcudnn9-cuda-12", "libcudnn9-dev-cuda-12"  # Specify CUDA 12 version for cuDNN
    )
    .run_commands(
        "mkdir -p /root/.ssh",
        "chmod 700 /root/.ssh",
        "touch /root/.ssh/authorized_keys",
        "chmod 600 /root/.ssh/authorized_keys",
        "mkdir -p /var/run/sshd"
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
        "pandoc",       # The document converter
        "texlive-full", # A comprehensive LaTeX distribution for high-quality PDFs
    )
    .run_commands(
        "mkdir -p /root/.ssh",
        "chmod 700 /root/.ssh",
        "touch /root/.ssh/authorized_keys",
        "chmod 600 /root/.ssh/authorized_keys",
        "mkdir -p /var/run/sshd"
    )
)

# NEW: Define a dedicated image for the Gemini CLI.
gemini_cli_image = (
    modal.Image.debian_slim()
    .apt_install("openssh-server", "git", "vim", "curl", "wget", "unzip", "procps", "nodejs", "npm") # Add nodejs and npm
    .run_commands(
        "npm install -g @google/gemini-cli", # Correct, official installation
        "mkdir -p /root/.ssh",
        "chmod 700 /root/.ssh",
        "touch /root/.ssh/authorized_keys",
        "chmod 600 /root/.ssh/authorized_keys",
        "mkdir -p /var/run/sshd"
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
        print(f"Installing extra packages: {', '.join(extra_packages)}...", file=sys.stderr)
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
        print(f"\nContainer will shut down after {IDLE_TIMEOUT_SECONDS // 60} minutes of inactivity.", file=sys.stderr)

        # Loop to check for active connections
        while idle_time < IDLE_TIMEOUT_SECONDS:
            time.sleep(check_interval)
            # Check for active SSH user sessions.
            result = subprocess.run(
                "ps -ef | grep 'sshd: root@' | grep -v grep",
                shell=True,
                capture_output=True,
            )
            
            if result.stdout: # If there is any output, a user is connected.
                idle_time = 0 # Reset the idle timer.
            else:
                idle_time += check_interval
                remaining = IDLE_TIMEOUT_SECONDS - idle_time
                print(f"No active SSH connection. Shutting down in {remaining}s...", file=sys.stderr, end='\r')
        
        print(f"\nIdle timeout of {IDLE_TIMEOUT_SECONDS}s reached. Shutting down instance.", file=sys.stderr)

# Common arguments for the devbox functions
common_devbox_args = dict(
    secrets=[modal.Secret.from_name("ssh-public-key")],
    volumes={"/data": dev_volume},
    cpu=0.5,
    memory=2096,
    timeout=28800,
    enable_memory_snapshot=True,
)

@app.function(image=standard_devbox_image, **common_devbox_args)
def launch_devbox(extra_packages: list[str] = None):
    """Launches a non-GPU personal development environment."""
    run_devbox_shared(extra_packages)

@app.function(image=cuda_devbox_image, gpu="t4", **common_devbox_args)
def launch_devbox_t4(extra_packages: list[str] = None):
    """Launches a T4 GPU-powered personal development environment."""
    run_devbox_shared(extra_packages)

@app.function(image=cuda_devbox_image, gpu="l4", **common_devbox_args)
def launch_devbox_l4(extra_packages: list[str] = None):
    """Launches an L4 GPU-powered personal development environment."""
    run_devbox_shared(extra_packages)

@app.function(image=cuda_devbox_image, gpu="a10g", **common_devbox_args)
def launch_devbox_a10g(extra_packages: list[str] = None):
    """Launches an A10G GPU-powered personal development environment."""
    run_devbox_shared(extra_packages)


# NEW: Add a dedicated function for the document processing environment.
@app.function(
    image=doc_processing_image, # Use the new, dedicated image
    secrets=[modal.Secret.from_name("ssh-public-key")],
    volumes={"/data": dev_volume},
    cpu=1, # More CPU for potentially heavy pandoc jobs
    memory=4096, # More memory for texlive
    timeout=28800,
    enable_memory_snapshot=True
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
        print(f"\nContainer will shut down after {IDLE_TIMEOUT_SECONDS // 60} minutes of inactivity.", file=sys.stderr)

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
                print(f"No active SSH connection. Shutting down in {remaining}s...", file=sys.stderr, end='\r')
        
        print(f"\nIdle timeout of {IDLE_TIMEOUT_SECONDS}s reached. Shutting down instance.", file=sys.stderr)

# NEW: Add a dedicated function for the Gemini CLI environment.
@app.function(
    image=gemini_cli_image, # Use the new, dedicated image
    secrets=[
        modal.Secret.from_name("ssh-public-key"),
        modal.Secret.from_name("gemini-api-key") # New secret for Gemini API key
    ],
    volumes={"/data": dev_volume},
    cpu=0.5,
    memory=2096,
    timeout=28800,
    enable_memory_snapshot=True
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
        ".profile",
        ".viminfo",
        ".vimrc",
        ".gitconfig",
        ".ssh/config",
        ".ssh/known_hosts",
        # Gemini CLI specific persistence
        ".gemini/GEMINI.md",
        ".gemini/google_account_id",
        ".gemini/google_accounts.json",
        ".gemini/mcp-oauth-tokens-v2.json",
        ".gemini/settings.json",
        ".gemini/extensions", # This is a directory
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
        print(f"\nContainer will shut down after {IDLE_TIMEOUT_SECONDS // 60} minutes of inactivity.", file=sys.stderr)

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
                print(f"No active SSH connection. Shutting down in {remaining}s...", file=sys.stderr, end='\r')
        
        print(f"\nIdle timeout of {IDLE_TIMEOUT_SECONDS}s reached. Shutting down instance.", file=sys.stderr)


# 5. A single, menu-driven local entrypoint.
@app.local_entrypoint()
def main():
    """
    Presents a menu to the user to select and launch a DevBox template.
    """
    print("\nSelect a DevBox template to launch:")
    print("1. Standard DevBox (General purpose, with optional extra packages)")
    print("2. Document Processing Box (Pandoc + TeX Live pre-installed)")
    print("3. Gemini CLI Box (Pre-installed and configured)") # New option

    try:
        choice = input("Enter your choice (1, 2, or 3): ") # Updated prompt
    except EOFError:
        print("\nNo input received. Exiting.")
        return

    if choice == '1':
        # --- Standard DevBox Logic ---
        try:
            tools_input = input("Enter any extra tools to install (space-separated, e.g., 'htop tmux'): ")
        except EOFError:
            tools_input = "" # Default to no extra tools if input is piped
        
        package_list = tools_input.split()

        # Replace 'python' with 'python-is-python3' for compatibility.
        if "python" in package_list:
            package_list[package_list.index("python")] = "python-is-python3"
            print("Replaced 'python' with 'python-is-python3' for Debian compatibility.", file=sys.stderr)

        if package_list:
            print(f"Requesting with additional tools: {package_list}")
        else:
            print("No extra tools requested.")

        # Ask about GPU
        try:
            gpu_choice = input("Attach a GPU? (y/n, default: n): ").lower()
        except EOFError:
            gpu_choice = "n"

        if gpu_choice == 'y':
            print("\nSelect GPU type:")
            print("1. T4 GPU (Cost-effective, good for inference)")
            print("2. L4 GPU (Newer, more performant than T4)")
            print("3. A10G GPU (Higher performance, more VRAM)")
            
            try:
                gpu_type_choice = input("Enter your choice (1, 2, or 3): ")
            except EOFError:
                print("\nNo input received. Exiting.")
                return

            if gpu_type_choice == '1':
                print("\nRequesting a DevBox with T4 GPU...")
                launch_devbox_t4.remote(extra_packages=package_list)
            elif gpu_type_choice == '2':
                print("\nRequesting a DevBox with L4 GPU...")
                launch_devbox_l4.remote(extra_packages=package_list)
            elif gpu_type_choice == '3':
                print("\nRequesting a DevBox with A10G GPU...")
                launch_devbox_a10g.remote(extra_packages=package_list)
            else:
                print("Invalid GPU choice. Please run again.")
                return
        else:
            print("\nRequesting a Standard DevBox (no GPU)...")
            launch_devbox.remote(extra_packages=package_list)

    elif choice == '2':
        print("\nRequesting a dedicated Document Processing Box...")
        launch_doc_processor.remote()
        
    elif choice == '3': # New logic branch
        print("\nRequesting a dedicated Gemini CLI Box...")
        launch_gemini_cli_box.remote()

    else:
        print("Invalid choice. Please run the script again and select 1, 2, or 3.")