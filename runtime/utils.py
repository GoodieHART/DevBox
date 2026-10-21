"""
Utility functions for DevBox Launcher.

This module provides system information, SSH key injection, and other
common utility functions used across the DevBox application.

Author: GoodieHART
"""

import os
import platform


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
    Display system specs in a formatted box.
    """
    info = get_system_info()
    system_box = f"""
 🖥️  Local System:
{info}
 🐍 Python: {platform.python_version()}
 💻 Platform: {platform.system()} {platform.release()}
"""
    # Import here to avoid circular dependency
    from ui.ui_utils import create_box
    create_box(system_box, "🖥️  SYSTEM SPECS")


def inject_ssh_key(ssh_dir="/root/.ssh"):
    """
    Inject SSH public keys from Modal Secrets into authorized_keys.

    Reads PUBKEYS (preferred, one key per line, unlimited) with fallback
    to the legacy single-key PUBKEY. Blank lines and malformed entries
    are skipped; installation is idempotent. Returns True if at least
    one key ends up installed.
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
    auth_keys_file = f"{ssh_dir}/authorized_keys"

    try:
        # Check who we are running as
        current_user = pwd.getpwuid(os.getuid()).pw_name
        print(f"👤 Running as user: {current_user} (UID: {os.getuid()})", file=sys.stderr)

        # Check environment variables (key material never printed in full)
        print("🔍 Environment variables:", file=sys.stderr)
        for key in ['PUBKEYS', 'PUBKEY', 'HOME', 'USER']:
            value = os.environ.get(key, 'NOT SET')
            if key in ('PUBKEYS', 'PUBKEY') and value and value != 'NOT SET':
                lines = [l for l in value.splitlines() if l.strip()]
                print(f"  {key}: {len(lines)} key line(s), {len(value)} chars", file=sys.stderr)
            else:
                print(f"  {key}: {value}", file=sys.stderr)

        # Get pubkeys from environment - THIS IS THE CRITICAL PART
        # PUBKEYS (one key per line, unlimited) wins; legacy PUBKEY is fallback.
        raw_keys = os.environ.get("PUBKEYS", "")
        source = "PUBKEYS"
        if not raw_keys.strip():
            raw_keys = os.environ.get("PUBKEY", "")
            source = "PUBKEY"

        if not raw_keys.strip():
            print("\n❌ CRITICAL ERROR: PUBKEYS/PUBKEY environment variables are EMPTY!", file=sys.stderr)
            print("❌ SSH authentication WILL FAIL!", file=sys.stderr)
            print("❌ Check: modal secret list | grep ssh", file=sys.stderr)
            print("❌ Check: modal secret create ssh-public-key PUBKEYS=\"$(cat ~/.ssh/id_ed25519.pub)\"", file=sys.stderr)
            print("❌   (multiple devices: one key per line, as many as needed)", file=sys.stderr)
            print("="*60, file=sys.stderr)
            return False

        _KEY_PREFIXES = ("ssh-rsa ", "ssh-dss ", "ssh-ed25519 ",
                         "ecdsa-sha2-nistp256 ", "ecdsa-sha2-nistp384 ",
                         "ecdsa-sha2-nistp521 ", "sk-ssh-ed25519@",
                         "sk-ecdsa-sha2-")
        keys = []
        skipped = 0
        for line in raw_keys.splitlines():
            line = line.strip()
            if not line:
                continue
            if line.startswith(_KEY_PREFIXES) and line not in keys:
                keys.append(line)
            else:
                skipped += 1

        print(f"\n✓ Found {len(keys)} valid key(s) via {source} ({skipped} malformed skipped)", file=sys.stderr)

        if not keys:
            print("❌ No valid SSH public keys found — check key format!", file=sys.stderr)
            print("="*60, file=sys.stderr)
            return False

        # Ensure .ssh directory exists
        os.makedirs(ssh_dir, mode=0o700, exist_ok=True)
        
        # Get current .ssh directory info
        ssh_stat = os.stat(ssh_dir)
        ssh_owner = pwd.getpwuid(ssh_stat.st_uid).pw_name
        ssh_perms = oct(ssh_stat.st_mode)[-3:]
        print(f"📁 {ssh_dir} owner={ssh_owner}, perms={ssh_perms}", file=sys.stderr)
        
        if ssh_perms != "700":
            print("  ⚠️ Fixing permissions to 700", file=sys.stderr)
            os.chmod(ssh_dir, 0o700)

        # Check if authorized_keys exists and get its current state
        if os.path.exists(auth_keys_file):
            auth_stat = os.stat(auth_keys_file)
            auth_owner = pwd.getpwuid(auth_stat.st_uid).pw_name
            auth_perms = oct(auth_stat.st_mode)[-3:]
            with open(auth_keys_file, "r") as f:
                existing_content = f.read().strip()
            print(f"📄 {auth_keys_file} exists, owner={auth_owner}, perms={auth_perms}, size={len(existing_content)} bytes", file=sys.stderr)
            
            # Check which keys are already there
            present = sum(1 for k in keys if k in existing_content)
            print(f"  {present}/{len(keys)} key(s) already present in authorized_keys", file=sys.stderr)
        else:
            print(f"📄 {auth_keys_file} does not exist, will create", file=sys.stderr)
            existing_content = ""

        # Write any missing keys (idempotent — already-present keys are skipped)
        added = 0
        for key in keys:
            if key not in existing_content:
                with open(auth_keys_file, "a") as f:
                    f.write(key + "\n")
                existing_content += "\n" + key
                added += 1
        print(f"✓ Installed {added} new key(s), {len(keys) - added} already present", file=sys.stderr)

        # Set permissions (CRITICAL for SSH to work!)
        os.chmod(auth_keys_file, 0o600)
        
        # Final verification
        final_stat = os.stat(auth_keys_file)
        final_perms = oct(final_stat.st_mode)[-3:]
        final_owner = pwd.getpwuid(final_stat.st_uid).pw_name
        
        with open(auth_keys_file, "r") as f:
            final_content = f.read()
        
        print("\n📊 FINAL STATE:", file=sys.stderr)
        print(f"  File: {auth_keys_file}", file=sys.stderr)
        print(f"  Owner: {final_owner}", file=sys.stderr)
        print(f"  Permissions: {final_perms} (should be 600)", file=sys.stderr)
        print(f"  Size: {len(final_content)} bytes", file=sys.stderr)
        print(f"  Contains all keys: {all(k in final_content for k in keys)}", file=sys.stderr)
        
        if final_perms != "600":
            print(f"  ❌ WARNING: Permissions are {final_perms}, not 600!", file=sys.stderr)
        
        # Also check SSHD config
        print("\n🔍 SSHD Configuration:", file=sys.stderr)
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