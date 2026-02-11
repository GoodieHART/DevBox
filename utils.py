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
    
    Returns:
        bool: True if successful, False otherwise
    """
    # Ensure .ssh directory exists with proper permissions
    ssh_dir = "/root/.ssh"
    auth_keys_file = f"{ssh_dir}/authorized_keys"
    
    try:
        # CRITICAL: Check who we are running as
        current_user = pwd.getpwuid(os.getuid()).pw_name
        print("="*60, file=sys.stderr)
        print("🔐 SSH KEY INJECTION DIAGNOSTICS", file=sys.stderr)
        print("="*60, file=sys.stderr)
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
        
        # Ensure .ssh directory exists with proper permissions
        os.makedirs(ssh_dir, exist_ok=True)
        os.chmod(ssh_dir, 0o700)
        print(f"✓ Created/verified .ssh directory: {ssh_dir}", file=sys.stderr)
        
        # Write the key to authorized_keys with proper permissions
        with open(auth_keys_file, 'w') as f:
            f.write(pubkey + '\n')
        os.chmod(auth_keys_file, 0o600)
        print(f"✓ Key written to {auth_keys_file}", file=sys.stderr)
        
        # Verify the key was written correctly
        with open(auth_keys_file, 'r') as f:
            written_key = f.read().strip()
        
        if written_key == pubkey:
            print("✓ SSH key injection VERIFIED successfully!", file=sys.stderr)
            print("="*60, file=sys.stderr)
            return True
        else:
            print("❌ VERIFICATION FAILED: Written key doesn't match original!", file=sys.stderr)
            return False
            
    except Exception as e:
        print(f"❌ CRITICAL ERROR during SSH key injection: {e}", file=sys.stderr)
        print("="*60, file=sys.stderr)
        return False