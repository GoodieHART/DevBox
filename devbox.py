import modal
import subprocess
import sys
import time
import random
import platform
import os

from images import (
    standard_devbox_image, cuda_devbox_image, doc_processing_image,
    gemini_cli_image, llm_playroom_image, llamacpp_cpu_image, rdp_devbox_image
)

app = modal.App(
    name="personal-devbox-launcher",
)

# This will be mounted in the container for persistent storage.
dev_volume = modal.Volume.from_name("my-dev-volume", create_if_missing=True)


# Helper function to inject SSH key with proper error handling and debugging
def inject_ssh_key():
    """
    Inject SSH public key from Modal Secret into authorized_keys.
    Includes debugging output and ensures proper permissions.
    """
    import os
    import sys
    import subprocess
    import pwd

    print("="*60, file=sys.stderr)
    print("🔐 SSH KEY INJECTION DIAGNOSTICS", file=sys.stderr)
    print("="*60, file=sys.stderr)

    # Ensure .ssh directory exists with proper permissions
    ssh_dir = "/root/.ssh"
    auth_keys_file = f"{ssh_dir}/authorized_keys"

    try:
        # CRITICAL: Check who we are running as
        current_user = pwd.getpwuid(os.getuid()).pw_name
        print(f"👤 Running as user: {current_user} (UID: {os.getuid()})", file=sys.stderr)

        # Check environment variables
        print(f"🔍 Environment variables:", file=sys.stderr)
        for key in ['PUBKEY', 'HOME', 'USER']:
            value = os.environ.get(key, 'NOT SET')
            if key == 'PUBKEY':
                # Show partial key for security
                if value and len(value) > 20:
                    print(f"  {key}: {value[:30]}... (length: {len(value)})", file=sys.stderr)
                else:
                    print(f"  {key}: {value[:30] if value else 'EMPTY OR NOT SET'} ⚠️", file=sys.stderr)
            else:
                print(f"  {key}: {value}", file=sys.stderr)

        # Get pubkey from environment - THIS IS THE CRITICAL PART
        pubkey = os.environ.get("PUBKEY", "").strip()
        
        if not pubkey:
            print("\n❌ CRITICAL ERROR: PUBKEY environment variable is EMPTY!", file=sys.stderr)
            print("❌ SSH authentication WILL FAIL!", file=sys.stderr)
            print("❌ Check: modal secret list | grep ssh", file=sys.stderr)
            print("❌ Check: modal secret create ssh-public-key PUBKEY=\"$(cat ~/.ssh/id_ed25519.pub)\"", file=sys.stderr)
            print("="*60, file=sys.stderr)
            return False

        print(f"\n✓ Found PUBKEY (length: {len(pubkey)} chars)", file=sys.stderr)

        # Ensure .ssh directory exists
        os.makedirs(ssh_dir, mode=0o700, exist_ok=True)
        
        # Get current .ssh directory info
        ssh_stat = os.stat(ssh_dir)
        ssh_owner = pwd.getpwuid(ssh_stat.st_uid).pw_name
        ssh_perms = oct(ssh_stat.st_mode)[-3:]
        print(f"📁 {ssh_dir} owner={ssh_owner}, perms={ssh_perms}", file=sys.stderr)
        
        if ssh_perms != "700":
            print(f"  ⚠️ Fixing permissions to 700", file=sys.stderr)
            os.chmod(ssh_dir, 0o700)

        # Check if authorized_keys exists and get its current state
        if os.path.exists(auth_keys_file):
            auth_stat = os.stat(auth_keys_file)
            auth_owner = pwd.getpwuid(auth_stat.st_uid).pw_name
            auth_perms = oct(auth_stat.st_mode)[-3:]
            with open(auth_keys_file, "r") as f:
                existing_content = f.read().strip()
            print(f"📄 {auth_keys_file} exists, owner={auth_owner}, perms={auth_perms}, size={len(existing_content)} bytes", file=sys.stderr)
            
            # Check if our key is already there
            if pubkey in existing_content:
                print(f"  ✓ Key already present in authorized_keys", file=sys.stderr)
            else:
                print(f"  ⚠️ Key NOT in authorized_keys, will append", file=sys.stderr)
        else:
            print(f"📄 {auth_keys_file} does not exist, will create", file=sys.stderr)
            existing_content = ""

        # Write the key
        if pubkey not in existing_content:
            with open(auth_keys_file, "a") as f:
                f.write(pubkey + "\n")
            print(f"  ✓ Appended key to authorized_keys", file=sys.stderr)

        # Set permissions (CRITICAL for SSH to work!)
        os.chmod(auth_keys_file, 0o600)
        
        # Final verification
        final_stat = os.stat(auth_keys_file)
        final_perms = oct(final_stat.st_mode)[-3:]
        final_owner = pwd.getpwuid(final_stat.st_uid).pw_name
        
        with open(auth_keys_file, "r") as f:
            final_content = f.read()
        
        print(f"\n📊 FINAL STATE:", file=sys.stderr)
        print(f"  File: {auth_keys_file}", file=sys.stderr)
        print(f"  Owner: {final_owner}", file=sys.stderr)
        print(f"  Permissions: {final_perms} (should be 600)", file=sys.stderr)
        print(f"  Size: {len(final_content)} bytes", file=sys.stderr)
        print(f"  Contains key: {pubkey in final_content}", file=sys.stderr)
        
        if final_perms != "600":
            print(f"  ❌ WARNING: Permissions are {final_perms}, not 600!", file=sys.stderr)
        
        # Also check SSHD config
        print(f"\n🔍 SSHD Configuration:", file=sys.stderr)
        try:
            result = subprocess.run(['grep', '-E', '^(PubkeyAuthentication|PasswordAuthentication|PermitRootLogin)', '/etc/ssh/sshd_config'], 
                                  capture_output=True, text=True)
            if result.stdout:
                for line in result.stdout.strip().split('\n'):
                    print(f"  {line}", file=sys.stderr)
            else:
                print("  ⚠️ No SSH auth settings found in sshd_config!", file=sys.stderr)
        except Exception as e:
            print(f"  ⚠️ Could not read sshd_config: {e}", file=sys.stderr)

        print("="*60, file=sys.stderr)
        return True

    except Exception as e:
        print(f"\n❌ EXCEPTION during SSH key injection: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)
        print("="*60, file=sys.stderr)
        return False


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

    # CRITICAL: Inject SSH key AFTER backup restore and symlinks!
    # Otherwise the backup will overwrite the authorized_keys file
    inject_ssh_key()

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
    inject_ssh_key()

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
    inject_ssh_key()

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
    inject_ssh_key()

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
    inject_ssh_key()

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


# NEW: llama.cpp playroom with prebuilt CPU binaries
@app.function(
    image=llamacpp_cpu_image,
    cpu=4.0,  # Increased CPU for better performance
    memory=8192,  # Increased memory for large models
    timeout=1800,  # 30 minutes for playroom
    secrets=[modal.Secret.from_name("ssh-public-key")],
    volumes={"/data": dev_volume},
)
def launch_llamacpp_playroom():
    """llama.cpp playroom with prebuilt CPU binaries and model selection."""
    import os
    import shutil
    import subprocess
    import sys
    import time
    import atexit

    # Show welcome message
    print("\n🧠 Launching llama.cpp Playroom (CPU)")
    print("💻 Running on CPU - optimized for inference")
    print("📦 Models available: DeepSeek, Qwen3-Coder, Gemma 3")
    
    # --- Set up persistent dotfiles using symbolic links ---
    print("Linking persistent configuration files...", file=sys.stderr)
    
    persistent_storage_dir = "/data/.config_persistence"
    os.makedirs(persistent_storage_dir, exist_ok=True)

    items_to_persist = [
        ".bash_history", ".bashrc", ".profile", ".viminfo", ".vimrc",
        ".gitconfig", ".ssh/config", ".ssh/known_hosts",
        # Add Unsloth-specific persistence
        ".gemini", ".opencode", ".ollama", ".llama.cpp",
        ".config/xfce4", ".local/share/xfce4", ".cache/sessions",
        "Desktop", ".xsession",
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

    # --- Model selection logic ---
    print("\n📦 Model Selection:")
    print("1. DeepSeek-V3.1-Terminus - Superior performance (75.6% Aider score)")
    print("2. Qwen3-Coder-30B-A3B - Optimized for coding and development")
    print("3. Gemma 3-27B - Excellent efficiency, multimodal support")
    
    try:
        model_choice = input("Enter model number (1-3): ").strip()
    except EOFError:
        model_choice = "1"

    model_info = {
        "1": {
            "name": "DeepSeek-V3.1-Terminus",
            "url": "https://huggingface.co/unsloth/DeepSeek-V3.1-Terminus-GGUF/resolve/main/DeepSeek-V3.1-Terminus-IQ2_XS.gguf",
            "size": "170GB (IQ2_XS)",
            "description": "Superior performance, 75.6% Aider score"
        },
        "2": {
            "name": "Qwen3-Coder-30B-A3B", 
            "url": "https://huggingface.co/unsloth/Qwen3-Coder-30B-A3B-GGUF/resolve/main/Qwen3-Coder-30B-A3B-Q4_K_M.gguf",
            "size": "15GB (Q4_K_M)",
            "description": "Optimized for agentic coding and development"
        },
        "3": {
            "name": "Gemma 3-27B",
            "url": "https://huggingface.co/unsloth/gemma-3-27b-it-GGUF/resolve/main/gemma-3-27b-it-Q4_K_XL.gguf", 
            "size": "16GB (Q4_K_XL)",
            "description": "Excellent efficiency, multimodal support"
        }
    }

    if model_choice not in model_info:
        print("❌ Invalid choice. Defaulting to DeepSeek-V3.1-Terminus.")
        model_choice = "1"

    selected_model = model_info[model_choice]
    
    # Download model if not already present
    model_filename = selected_model["name"] + ".gguf"
    model_path = f"/opt/models/unsloth/{selected_model['name'].lower().replace(' ', '_')}/{model_filename}"
    
    if not os.path.exists(model_path):
        print(f"📦 Downloading {selected_model['name']} ({selected_model['size']})...")
        os.makedirs(os.path.dirname(model_path), exist_ok=True)
        
        # Download with curl
        subprocess.run([
            "curl", "-L", "-o", model_path, "--create-dirs",
            selected_model["url"]
        ], check=True)
        print(f"✅ Model downloaded to {model_path}")
    else:
        print(f"✅ Model already downloaded: {model_path}")

    # --- Set up comprehensive persistence for llama.cpp ---
    print("Setting up llama.cpp persistence system...", file=sys.stderr)

    # Create model storage directory
    os.makedirs("/opt/models/unsloth", exist_ok=True)

    # --- Register comprehensive backup on shutdown ---
    def create_llama_backup():
        """Create comprehensive llama.cpp backup on shutdown."""
        try:
            print("Creating llama.cpp backup...", file=sys.stderr)
            backup_file = "/data/llama_backup.tar.gz"

            # Create compressed backup of model directory
            subprocess.run([
                "tar", "-czf", backup_file,
                "-C", "/opt/models/unsloth", "."
            ], check=True, capture_output=True)

            print(f"Backup saved to {backup_file}", file=sys.stderr)

        except Exception as e:
            print(f"Warning: Backup failed - {e}", file=sys.stderr)

    # Register the backup function to run on exit
    atexit.register(create_llama_backup)

    # --- Start llama.cpp server ---
    print(f"\n🧠 Launching {selected_model['name']} with Unsloth Dynamic 2.0...")
    print(f"🚀 GPU: NVIDIA L40S detected - ready for AI workloads")
    print(f"📦 Model: {selected_model['name']} ({selected_model['size']})")
    print(f"📦 Description: {selected_model['description']}")
    print("📝 To get started:")
    print("   1. Connect via SSH below")
    print("   2. Run: ./opt/llama.cpp/build/bin/llama-cli -m /opt/models/unsloth/.../model.gguf")
    
    # Inject SSH key and start SSH daemon
    inject_ssh_key()
    subprocess.run(["/usr/sbin/sshd"])

    # Forward the SSH port and print the connection command
    with modal.forward(22, unencrypted=True) as tunnel:
        ssh_command = f"ssh root@{tunnel.host} -p {tunnel.unencrypted_port}"
        print("\n🚀 Your Unsloth llama.cpp Playroom is ready!")
        print("Paste this command into your terminal:")
        print(ssh_command)

        idle_time = 0
        check_interval = 15
        idle_timeout = 600  # 10 minutes for playroom

        print(f"\nContainer will shut down after {idle_timeout // 60} minutes of inactivity.")

        # Loop to check for active connections
        while idle_time < idle_timeout:
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
                remaining = idle_timeout - idle_time
                print(
                    f"No active SSH connection. Shutting down in {remaining}s...",
                    end="\r",
                )

        print(f"\nIdle timeout of {idle_timeout}s reached. Shutting down instance.")
        import os
        import shutil

        # Inject your public key from the secret using Modal's mechanism
        # This will be handled automatically by Modal with the secrets parameter

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
    from ui_utils import create_box, show_spinner
    from quotes_loader import get_random_quote, format_quote
    from utils import inject_ssh_key, display_system_info
    from config import IDLE_TIMEOUT_SECONDS, get_resource_config, GPU_TYPES
    from gpu_utils import get_gpu_config, get_available_gpus
    from shared_runtime import handle_devbox_startup

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

 6. 🧠 llama.cpp Playroom
      Prebuilt CPU binaries with model selection
 """
    create_box(menu_box, "🚀 LAUNCH OPTIONS")

    try:
        choice = input("Enter your choice (1-6): ").strip()
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

    elif choice == "6":  # llama.cpp Playroom
        print()
        
        # llama.cpp Playroom menu
        llamacpp_box = """
🧠 Launching llama.cpp Playroom...

Prebuilt CPU-optimized llama.cpp binaries from official releases

Models available:
• DeepSeek-V3.1-Terminus - Superior performance (75.6% Aider score)
• Qwen3-Coder-30B-A3B - Optimized for agentic coding and development
• Gemma 3-27B - Excellent efficiency, multimodal support

💻 CPU-optimized for inference
• Model download sizes: 15GB to 170GB
• GGUF quantization format
• OpenAI-compatible API support
"""
        create_box(llamacpp_box, "🧠 LLAMA.CPP PLAYROOM")
        
        show_spinner("Preparing llama.cpp environment", 2)
        launch_llamacpp_playroom.remote()

    else:
        error_box = """
❌ Invalid choice selected.

Please run the launcher again and choose:
• 1 for Standard DevBox
• 2 for Document Processing
• 3 for AI Assistants Box
• 4 for LLM Playroom
• 5 for RDP Desktop Box
• 6 for llama.cpp Playroom
"""
        create_box(error_box, "❌ ERROR")
