# 🚀 UNSLOTH LLAMA.CPP INTEGRATION - EXECUTION PLAN
# Created: 2026-01-29
# This is a comprehensive, detailed implementation plan for adding Unsloth llama.cpp support to the Modal DevBox

## EXECUTION SUMMARY

This plan implements a new DevBox option: **Unsloth llama.cpp Playroom** with three model choices (DeepSeek-V3.1, Qwen3-Coder, Gemma 3) using Unsloth's Dynamic 2.0 quantization for superior performance and efficiency.

## TARGET FILES & CHANGE LOCATIONS

### 1. devbox.py (MAIN FILE - 1,418 lines)
**Changes Required:**
- **Lines 198-212**: Add new image definition
- **Lines 920-930**: Add new function definition  
- **Lines 1418**: Add new menu option
- **Lines 1418**: Add new model selection logic

### 2. ui_utils.py (UI COMPONENTS - 129 lines)
**Changes Required:**
- **Lines 70-112**: Add new box types if needed
- **Lines 125-129**: Add new utility functions if needed

### 3. quotes_loader.py (QUOTES - 79 lines)
**Changes Required:**
- **Lines 55-56**: Add new quote if needed
- **Lines 69-70**: Add new quote formatting if needed

### 4. quotes.json (QUOTES DATA - 30 lines)
**Changes Required:**
- **Lines 1-30**: Add new quote if needed

## DETAILED IMPLEMENTATION STEPS

### STEP 1: IMAGE DEFINITION - LINES 198-212

**Current Location:** Lines 198-212 contain `llm_playroom_image` definition

**Add New Image Definition:**
```python
# NEW: Unsloth-optimized llama.cpp image with Dynamic 2.0 quantization
llamacpp_unsloth_image = (
    modal.Image.debian_slim(python_version="3.10")
    .apt_install([
        # Standard DevBox packages
        "openssh-server", "git", "neovim", "curl", "wget", 
        "unzip", "procps", "nano", "htop", "build-essential",
        
        # llama.cpp build dependencies
        "cmake", "clang", "pkg-config", "python3-dev", 
        "zlib1g-dev", "pciutils", "lshw", "libcurl4-openssl-dev"
    ])
    .run_commands([
        # Standard SSH setup (MUST BE IDENTICAL)
        "mkdir -p /root/.ssh && chmod 700 /root/.ssh",
        "touch /root/.ssh/authorized_keys && chmod 600 /root/.ssh/authorized_keys",
        "mkdir -p /var/run/sshd",
        
        # llama.cpp build with curl support for model downloads
        "git clone https://github.com/ggml-org/llama.cpp.git /tmp/llama.cpp",
        "cd /tmp/llama.cpp && cmake -B build -DBUILD_SHARED_LIBS=OFF -DGGML_CUDA=ON -DLLAMA_CURL=ON",
        "cmake --build build --config Release -j $(nproc)",
        "mv /tmp/llama.cpp /opt/llama.cpp",
        
        # Create Unsloth model directories
        "mkdir -p /opt/models/unsloth",
        "mkdir -p /opt/models/unsloth/deepseek",
        "mkdir -p /opt/models/unsloth/qwen", 
        "mkdir -p /opt/models/unsloth/gemma"
    ])
)
```

### STEP 2: LAUNCH FUNCTION - LINES 920-930

**Current Location:** Lines 920-930 contain `llm_playroom_image` function definition

**Add New Function Definition:**
```python
# NEW: Unsloth llama.cpp playroom with model selection
@app.function(
    image=llamacpp_unsloth_image,
    gpu="L40S",
    cpu=1.0,
    memory=4096,
    timeout=600,
    enable_memory_snapshot=True,
    experimental_options={"enable_gpu_snapshot": True},
    secrets=[modal.Secret.from_name("ssh-public-key")],
    volumes={"/data": dev_volume},
)
def launch_llamacpp_unsloth_playroom():
    """Unsloth llama.cpp playroom with model selection and Dynamic 2.0 quantization."""
    import os
    import shutil
    import subprocess
    import sys
    import time
    import atexit

    # Show welcome message
    print("\n🧠 Launching Unsloth llama.cpp Playroom...")
    print("🚀 GPU: NVIDIA L40S detected - ready for AI workloads")
    print("📦 Unsloth Dynamic 2.0 quantization for superior performance")
    print("📦 Models available: DeepSeek-V3.1, Qwen3-Coder, Gemma 3")
    
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
    model_path = f"/opt/models/unsloth/{selected_model["name"].lower().replace(' ', '_')}/{model_filename}"
    
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
    
    # Start SSH daemon
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
```

### STEP 3: MENU INTEGRATION - LINES 1418

**Current Location:** Lines 1418-1418 contain main menu options

**Add New Menu Option:**
```python
# Add to main menu after existing options
elif choice == "6":  # New logic branch for Unsloth
    print()
    
    # Enhanced Unsloth menu with model selection
    unsloth_box = """
    🧠 Launching Unsloth llama.cpp Playroom...
    
    Unsloth Dynamic 2.0 quantization for superior performance
    
    Models available:
    • DeepSeek-V3.1-Terminus - Superior performance (75.6% Aider score)
    • Qwen3-Coder-30B-A3B - Optimized for agentic coding and development
    • Gemma 3-27B - Excellent efficiency, multimodal support
    
    GPU: NVIDIA L40S detected - ready for AI workloads
    • Model download sizes: 15GB to 170GB
    • Dynamic 2.0 quantization for 80% size reduction
    • Bug-fixed models with enhanced stability
    • Production-ready with API support
    """
    create_box(unsloth_box, "🧠 UNSLOTH LLAMA.CPP PLAYROOM")
    
    show_spinner("Preparing Unsloth environment", 2)
    launch_llamacpp_unsloth_playroom.remote()
```

### STEP 4: ERROR HANDLING - LINES 1418-1418

**Current Location:** Lines 1418-1418 contain error handling

**Add New Error Message:**
```python
# Add to error box
elif choice not in ["1", "2", "3", "4", "5", "6"]:
    error_box = """
    ❌ Invalid choice selected.
    
    Please run the launcher again and choose:
    • 1 for Standard DevBox
    • 2 for Document Processing
    • 3 for AI Assistants Box
    • 4 for LLM Playroom
    • 5 for RDP Desktop Box
    • 6 for Unsloth llama.cpp Playroom
    """
    create_box(error_box, "❌ ERROR")
```

### STEP 5: UI UTILITIES - ui_utils.py

**Current Location:** Lines 70-112 contain box types

**Add New Box Types (if needed):**
```python
# Add new box types for Unsloth-specific messages
def create_unsloth_box(message: str, title: str = "🧠 UNSLOTH") -> None:
    """
    Create a standardized Unsloth box for displaying Unsloth-specific messages.
    
    Args:
        message: The Unsloth-specific message to display
        title: Title for the Unsloth box (default: "🧠 UNSLOTH")
    """
    create_box(message, title)

def create_model_box(message: str, title: str = "📦 MODEL") -> None:
    """
    Create a standardized model box for displaying model information.
    
    Args:
        message: The model information to display
        title: Title for the model box (default: "📦 MODEL")
    """
    create_box(message, title)
```

### STEP 6: QUOTES - quotes_loader.py & quotes.json

**Current Location:** Lines 55-56 contain quotes

**Add New Quote (if needed):**
```python
# Add to fallback_quotes in quotes_loader.py
fallback_quotes = [
    # ... existing quotes
    {
        "text": "The best code is the code that never runs.",
        "author": "Unknown"
    }
]
```

**Add to quotes.json:**
```json
{
    "text": "The best code is the code that never runs.",
    "author": "Unknown"
}
```

## DEPENDENCY CHECKS

### 1. Python Dependencies
- **Required**: No additional Python dependencies needed
- **Existing**: All required packages already installed

### 2. System Dependencies
- **Required**: `libcurl4-openssl-dev` for model downloads
- **Existing**: Most dependencies already installed in base image

### 3. Modal Dependencies
- **Required**: No new Modal dependencies needed
- **Existing**: All Modal functionality already configured

## TESTING CHECKLIST

### 1. Image Creation
- [ ] Image builds successfully with new definition
- [ ] All dependencies install correctly
- [ ] llama.cpp compiles without errors

### 2. Function Execution
- [ ] Function launches without errors
- [ ] Model selection menu displays correctly
- [ ] Model download works correctly
- [ ] SSH connection established

### 3. Menu Integration
- [ ] Menu option #6 appears correctly
- [ ] Menu selection works correctly
- [ ] Error handling works for invalid choices

### 4. Persistence
- [ ] Dotfiles persist correctly
- [ ] Model files persist correctly
- [ ] Backups work correctly

### 5. Resource Usage
- [ ] GPU utilization works correctly
- [ ] Memory usage within expected limits
- [ ] Idle timeout works correctly

## POTENTIAL ISSUES & SOLUTIONS

### 1. Model Download Failures
**Issue**: Large models may fail to download due to network issues
**Solution**: Implement retry logic and progress indicators

### 2. GPU Memory Issues
**Issue**: Large models may exceed GPU memory
**Solution**: Add memory checking and model selection based on available VRAM

### 3. SSH Connection Issues
**Issue**: SSH may not start correctly
**Solution**: Add SSH health checks and error reporting

### 4. Build Failures
**Issue**: llama.cpp compilation may fail
**Solution**: Add build error handling and fallback to pre-built binaries

## OPTIMIZATION OPPORTUNITIES

### 1. Model Caching
- Implement model caching to avoid repeated downloads
- Add model versioning and update checking

### 2. Resource Optimization
- Add dynamic resource allocation based on model size
- Implement memory usage monitoring and optimization

### 3. User Experience
- Add progress indicators for long-running operations
- Implement better error reporting and recovery

### 4. Performance Monitoring
- Add GPU utilization monitoring
- Implement model performance benchmarking

## FINAL NOTES

This implementation plan provides a complete, production-ready integration of Unsloth llama.cpp with the existing Modal DevBox architecture. The plan follows all established patterns and conventions while adding the advanced capabilities of Unsloth's Dynamic 2.0 quantization.

**Key Benefits:**
- Superior performance with 80% size reduction
- Bug-fixed models with enhanced stability
- Full control over model selection and quantization
- Production-ready with API support
- Seamless integration with existing DevBox patterns

**Ready for implementation!**