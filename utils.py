"""
Utility functions for DevBox Launcher.

This module provides system information, SSH key injection, and other
common utility functions used across the DevBox application.

Author: GoodieHART
"""

import os
import platform
import subprocess
import sys


def get_system_info():
    """
    Get system information for display in UI.
    
    Returns:
        str: Formatted system information
    """
    try:
        cpu_count = os.cpu_count() or 1
        return f"CPU: {cpu_count} cores"
    except (OSError, AttributeError):
        return "CPU: Unknown"


def display_system_info():
    """
    Display system capabilities in a formatted box.
    """
    info = get_system_info()
    system_box = f"""
 🖥️  Local System:
{info}
 🐍 Python: {platform.python_version()}
 💻 Platform: {platform.system()} {platform.release()}
"""
    # Import here to avoid circular dependency
    from ui_utils import create_box
    create_box(system_box, "🖥️  SYSTEM CAPABILITIES")


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