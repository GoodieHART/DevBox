import modal
import subprocess
import sys
import time

# 1. Configuration for the auto-shutdown mechanism.
# Container will shut down if no one is connected via SSH for this many seconds.
IDLE_TIMEOUT_SECONDS = 300  # 5 minutes

# 2. Define a base image with essential tools + OpenSSH server.
# `procps` is included to provide the `ps` command for monitoring.
devbox_image = (
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


app = modal.App(
    name="personal-devbox-launcher",
    # The base image is no longer attached to the app directly
)

# 2. Define the persistent Volume.
# This will be mounted in the container for persistent storage.
dev_volume = modal.Volume.from_name("my-dev-volume", create_if_missing=True)

# 3. The remote function now accepts a list of packages to install.
@app.function(
    image=devbox_image, # Specify the base devbox image here
    secrets=[modal.Secret.from_name("ssh-public-key")],
    # Mount the volume at /data for persistent storage.
    # Note: Your home directory /root is not persistent.
    volumes={"/data": dev_volume},
    cpu=0.5,
    memory=2096,
    # We set a generous timeout as a fallback safety net,
    # but the idle check is the primary shutdown mechanism.
    timeout=28800, # 8-hour safety net
    enable_memory_snapshot=True
)
def launch_devbox(extra_packages: list[str] = None):
    """
    Launches a personal development environment with persistent storage
    and optional, dynamically installed tools.
    """
    import os

    # Inject your public key from the secret.
    pubkey = os.environ["PUBKEY"]
    # We use 'a' (append) mode to be safe, though it will be fresh on first run.
    with open("/root/.ssh/authorized_keys", "a") as f:
        if pubkey not in open("/root/.ssh/authorized_keys").read():
            f.write(pubkey + "\n")

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


# 5. A single, menu-driven local entrypoint.
@app.local_entrypoint()
def main():
    """
    Presents a menu to the user to select and launch a DevBox template.
    """
    print("\nSelect a DevBox template to launch:")
    print("1. Standard DevBox (General purpose, with optional extra packages)")
    print("2. Document Processing Box (Pandoc + TeX Live pre-installed)")

    try:
        choice = input("Enter your choice (1 or 2): ")
    except EOFError:
        print("\nNo input received. Exiting.")
        return

    if choice == '1':
        print("\nRequesting a Standard DevBox.")
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
            print("No extra tools requested. Launching with default tools.")

        launch_devbox.remote(extra_packages=package_list)

    elif choice == '2':
        print("\nRequesting a dedicated Document Processing Box...")
        launch_doc_processor.remote()
        
    else:
        print("Invalid choice. Please run the script again and select 1 or 2.")