# DETAILED MODULARIZATION EXECUTION PLAN
# This document contains the complete plan for refactoring devbox.py into modular components

## OVERVIEW
This plan details the step-by-step process to modularize the 1,430+ line devbox.py file while maintaining backward compatibility and functionality.

## PHASE 1: CREATE CONFIG.PY

### Files to Create:
- `config.py` - Centralizes all configuration constants

### Constants to Extract from devbox.py:

#### 1. IDLE_TIMEOUT_SECONDS
- **Current Location**: Line 84
- **Value**: `300` (5 minutes)
- **Usage**: Lines 486, 491, 504, 512, 660, 665, 683, 692, 700, 807, 812, 824, 832, 921, 926, 938, 946

#### 2. Resource Configurations
- **cpu_devbox_args**: Lines 706-712
- **gpu_devbox_args**: Lines 714-720  
- **cpu_devbox_args_rdp**: Lines 723-729
- **gpu_devbox_args_rdp**: Lines 731-737

#### 3. Package Lists (to be extracted later)
- Standard package lists used in image definitions
- Common SSH setup commands

### config.py Structure:
```python
# Configuration constants for DevBox launcher

# Timeout settings
IDLE_TIMEOUT_SECONDS = 300  # 5 minutes

# Resource configurations
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
```

## PHASE 2: CREATE IMAGES.PY

### Files to Create:
- `images.py` - Contains all image definitions and related utilities

### Image Definitions to Extract:

#### 1. standard_devbox_image (Lines 88-114)
- **Base**: `modal.Image.debian_slim(python_version="3.10")`
- **Packages**: 15 apt packages
- **SSH Setup**: Lines 108-113 (common across all images)

#### 2. cuda_devbox_image (Lines 117-143)
- **Base**: `modal.Image.from_registry("nvidia/cuda:12.1.1-devel-ubuntu22.04", add_python="3.11")`
- **Packages**: 15 apt packages + CUDA-specific packages
- **SSH Setup**: Lines 137-142 (same as standard)

#### 3. doc_processing_image (Lines 147-163)
- **Base**: `modal.Image.debian_slim()`
- **Packages**: 5 apt packages (Pandoc + TeX Live)
- **SSH Setup**: Lines 157-162 (same pattern)

#### 4. gemini_cli_image (Lines 166-196)
- **Base**: `modal.Image.debian_slim()`
- **Packages**: 8 apt packages + Node.js + Gemini CLI
- **SSH Setup**: Lines 188-195 (same pattern)

#### 5. llm_playroom_image (Lines 199-212)
- **Base**: `modal.Image.debian_slim(python_version="3.10")`
- **Packages**: 7 apt packages
- **SSH Setup**: Lines 207-209 (same pattern)

#### 6. llamacpp_unsloth_image (Lines 215-244)
- **Base**: `modal.Image.debian_slim(python_version="3.10")`
- **Packages**: 15 apt packages + llama.cpp dependencies
- **SSH Setup**: Lines 228-230 (same pattern)

#### 7. rdp_devbox_image (Lines 247-292)
- **Base**: `modal.Image.debian_slim(python_version="3.10")`
- **Packages**: 15 apt packages + RDP/desktop packages
- **SSH Setup**: Lines 261-264 (same pattern)

### images.py Structure:
```python
import modal
from config import dev_volume

def create_standard_image():
    """Create standard development environment image."""
    return modal.Image.debian_slim(python_version="3.10") \
        .apt_install(STANDARD_PACKAGES) \
        .run_commands(SSH_SETUP_COMMANDS)

def create_cuda_image():
    """Create CUDA development environment image."""
    return modal.Image.from_registry("nvidia/cuda:12.1.1-devel-ubuntu22.04", add_python="3.11") \
        .apt_install(CUDA_PACKAGES) \
        .run_commands(SSH_SETUP_COMMANDS)

def create_doc_processing_image():
    """Create document processing environment image."""
    return modal.Image.debian_slim() \
        .apt_install(DOC_PROCESSING_PACKAGES) \
        .run_commands(SSH_SETUP_COMMANDS)

# ... other image creation functions

# Common constants and functions
def create_ssh_setup_commands():
    """Create standard SSH setup commands."""
    return [
        "mkdir -p /root/.ssh",
        "chmod 700 /root/.ssh",
        "touch /root/.ssh/authorized_keys",
        "chmod 600 /root/.ssh/authorized_keys",
        "mkdir -p /var/run/sshd",
    ]

SSH_SETUP_COMMANDS = create_ssh_setup_commands()

STANDARD_PACKAGES = [
    "openssh-server", "clang", "cmake", "htop", "nano", "git",
    "neovim", "curl", "wget", "unzip", "procps", "zlib1g-dev",
    "build-essential", "pkg-config", "python3-dev",
]

# ... other package lists
```

## PHASE 3: CREATE UTILS.PY

### Files to Create:
- `utils.py` - Contains reusable utility functions

### Functions to Extract:

#### 1. SSH Key Injection (common pattern)
- **Current Locations**: Lines 318-322, 531-534, 788-791, 858-861, 971-974, 1254-1258
- **Pattern**: Inject PUBKEY from environment into authorized_keys

#### 2. Persistence Setup (common pattern)
- **Current Locations**: Lines 324-434 (run_devbox_shared), 536-582 (run_rdp_devbox_shared)
- **Pattern**: Create symbolic links for persistent storage

#### 3. Backup Functions (common pattern)
- **Current Locations**: Lines 437-457, 585-603, 1184-1202
- **Pattern**: Create compressed backup of /root directory

### utils.py Structure:
```python
def inject_ssh_key():
    """Inject SSH public key from environment into authorized_keys."""
    import os
    pubkey = os.environ["PUBKEY"]
    with open("/root/.ssh/authorized_keys", "a") as f:
        if pubkey not in open("/root/.ssh/authorized_keys").read():
            f.write(pubkey + "\n")

def setup_persistence(items_to_persist, persistent_storage_dir="/data/.config_persistence"):
    """Set up symbolic links for persistent storage."""
    import os, shutil
    
    os.makedirs(persistent_storage_dir, exist_ok=True)
    
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

def create_backup(backup_file="/data/root_full_backup.tar.gz", exclude=[]):
    """Create compressed backup of /root directory."""
    import subprocess
    
    exclude_args = ["--exclude=" + e for e in exclude]
    subprocess.run([
        "tar", "-czf", backup_file,
        *exclude_args,
        "-C", "/root", "."
    ], check=True)
```

## PHASE 4: REFACTOR DEVBOX.PY

### Files to Modify:
- `devbox.py` - Main entry point, refactor to use new modules

### Step-by-Step Refactoring Process:

#### Step 4.1: Import New Modules
```python
# Add at the top of devbox.pyrom config import (
    IDLE_TIMEOUT_SECONDS,
    cpu_devbox_args, gpu_devbox_args,
    cpu_devbox_args_rdp, gpu_devbox_args_rdp,
)

from images import (
    create_standard_image, create_cuda_image,
    create_doc_processing_image, create_gemini_cli_image,
    create_llm_playroom_image, create_llamacpp_unsloth_image,
    create_rdp_devbox_image,
)

from utils import inject_ssh_key, setup_persistence, create_backup
```

#### Step 4.2: Replace Image Definitions
```python
# Replace lines 88-114
standard_devbox_image = create_standard_image()

# Replace lines 117-143
cuda_devbox_image = create_cuda_image()

# Replace lines 147-163
doc_processing_image = create_doc_processing_image()

# ... and so on for all image definitions
```

#### Step 4.3: Replace Function Implementations
```python
# Replace run_devbox_shared function (lines 306-515)
def run_devbox_shared(extra_packages: list[str] | None = None):
    """Shared logic for launching a personal development environment."""
    import os, shutil, subprocess, atexit, sys
    
    # Use utils functions
    inject_ssh_key()
    
    # Set up persistence
    items_to_persist = [
        ".bash_history", ".bashrc", ".profile", ".viminfo", ".vimrc",
        ".gitconfig", ".ssh/config", ".ssh/known_hosts",
        # ... other items
    ]
    setup_persistence(items_to_persist)
    
    # Register backup
    atexit.register(lambda: create_backup())
    
    # ... rest of the function logic
```

#### Step 4.4: Update App Function Decorators
```python
# Replace image references in decorators
@app.function(
    image=standard_devbox_image,
    secrets=[modal.Secret.from_name("ssh-public-key")],
    volumes={"data": dev_volume},
    **cpu_devbox_args
)
def launch_devbox(extra_packages: list[str] | None = None):
    """Launches a non-GPU personal development environment."""
    run_devbox_shared(extra_packages)
```

#### Step 4.5: Update Local Entrypoint
```python
# No changes needed in main() function
# It already uses get_random_quote() and format_quote() which are modularized
```

## PHASE 5: VALIDATION AND TESTING

### Step 5.1: Verify Functionality
- Test each image configuration
- Verify all app functions work
- Test the local entrypoint menu
- Check SSH connectivity
- Verify persistence works

### Step 5.2: Check Backward Compatibility
- Ensure existing behavior is unchanged
- Verify all outputs are identical
- Test with same inputs as before

### Step 5.3: Performance Testing
- Measure startup time
- Verify resource usage
- Test idle timeout functionality
- Check backup/restore functionality

## FILES TO CREATE SUMMARY

1. `config.py` - Configuration constants
2. `images.py` - Image definitions and utilities  
3. `utils.py` - Reusable utility functions
4. `refactoring_plan.md` - This document

## FILES TO MODIFY SUMMARY

1. `devbox.py` - Main refactoring (import updates, function replacements)

## KEY CHANGES SUMMARY

### Before Refactoring:
- 1,430+ line monolithic file
- All constants embedded in code
- Repetitive SSH setup code
- Mixed concerns (UI, images, config, functions)

### After Refactoring:
- Modular structure with separate concerns
- Centralized configuration
- Reusable utility functions
- Maintained backward compatibility
- Easier to maintain and extend

## EXECUTION ORDER

1. Create `config.py`
2. Create `images.py`  
3. Create `utils.py`
4. Refactor `devbox.py`
5. Test and validate

## SUCCESS CRITERIA

- All existing functionality preserved
- No breaking changes
- Code is more maintainable
- Clear separation of concerns
- Easier to add new images/features
- Reduced code duplication

---

**This plan provides a complete roadmap for modularizing devbox.py while maintaining all existing functionality and backward compatibility.**

The refactoring will reduce code duplication, centralize configuration, and make the codebase easier to maintain and extend.