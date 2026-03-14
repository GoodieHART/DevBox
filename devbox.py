import modal
import subprocess
import sys
import time
import random
import platform
import os

from images import (
    standard_devbox_image, cuda_devbox_image, doc_processing_image,
    assisted_coding_image, llm_playroom_image, llamacpp_cpu_image, rdp_devbox_image, forensic_analysis_image
)
from shared_runtime import run_devbox_shared, run_rdp_devbox_shared


app = modal.App(
    name="personal-devbox-launcher",
)

# This will be mounted in the container for persistent storage.
dev_volume = modal.Volume.from_name("my-dev-volume", create_if_missing=True)

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

@app.function(
    image=doc_processing_image,
    secrets=[modal.Secret.from_name("ssh-public-key")],
    volumes={"/data": dev_volume},
    cpu=1,
    memory=4096,
    timeout=28000,
)
def launch_doc_processor():
    """Launches a document processing environment with Pandoc and TeX Live."""
    run_devbox_shared(extra_packages=None)

@app.function(
    image=assisted_coding_image,
    secrets=[modal.Secret.from_name("ssh-public-key"), modal.Secret.from_name("gemini-api-key"), # make sure to create this if you haven't already
    ],
    volumes={"/data": dev_volume},
    cpu=0.5,
    memory=1024,
    timeout=28800,
)
def launch_assisted_coding():
    """Launches a development environment with Gemini CLI & OpenCode pre-installed."""
    run_devbox_shared(extra_packages=None)

@app.function(
    image=llm_playroom_image,
    secrets=[modal.Secret.from_name("ssh-public-key")],
    volumes={"/data": dev_volume},
    gpu="L40S",
    cpu=1.0,
    memory=4096,
    timeout=600,
)
def launch_llm_playroom():
    """Launches an LLM Playroom environment with Ollama and preloaded models."""
    run_devbox_shared(extra_packages=None)
# add model selection here too!

@app.function(
  image=forensic_analysis_image,
  secrets=[modal.Secret.from_name("ssh-public-key")],
  volumes={"/data": dev_volume},
  cpu=1,
  memory=3096,
  timeout=18000,
)

def launch_forensics_image():
  """ Launches A Forensic Analysis Machine With Volatilty3 pre-installed. """
  run_devbox_shared(extra_packages=None)

@app.function(
    image=llamacpp_cpu_image,
    cpu=4.0,
    memory=8192,
    timeout=1800,
    secrets=[modal.Secret.from_name("ssh-public-key")],
    volumes={"/data": dev_volume},
)

def launch_llamacpp_playroom():
    """llama.cpp playroom with prebuilt CPU binaries and model selection."""
    import os
    import shutil
    import subprocess
    import sys
    import modal
    import time
    import atexit
    from utils import inject_ssh_key

    modal.interact() # This modal function allows to pass input to the running container
    
    print("\n🧠 Launching llama.cpp Playroom (CPU)")
    print("💻 Running on CPU")
    print("📦 Default Models List: DeepSeek, Qwen3-Coder, Gemma 3")
    
    # --- Set up persistent dotfiles using symbolic links ---
    print("Linking persistent configuration files...", file=sys.stderr)
    
    persistent_storage_dir = "/data/.config_persistence"
    os.makedirs(persistent_storage_dir, exist_ok=True)

    items_to_persist = [
        ".bash_history", ".bashrc", ".profile", ".viminfo", ".vimrc",
        ".gitconfig", ".ssh/config", ".ssh/known_hosts",
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

    print("\n📦 Model Selection:")
    print("1. DeepSeek-R1 - 87.5% on AIME 2025 Benchmark")
    print("2. Llama3.2 - Finetuned Llama3.2")
    print("3. Gemma 3-9B - Excellent efficiency, multimodal support")
    print("4. Custom Model - Select a custom model to download from HuggingFace: repo_id + filename")
    
    try:
        model_choice = input("Enter model number (1-4): ").strip()
    except EOFError:
        model_choice = "2"

    model_info = {
    "1": {
        "name": "DeepSeek-R1",
        "repo_id": "unsloth/DeepSeek-R1-0528-Qwen3-8B-GGUF",
        "filename": "DeepSeek-R1-0528-Qwen3-8B-Q4_K_S.gguf",
        "size": "4.2GB (Q4_K_S)",
        "description": "87.5 AIME 2025 Score"
    },
    "2": {
        "name": "Llama3.2", 
        "repo_id": "unsloth/Llama-3.2-3B-Instruct-GGUF",
        "filename": "Llama-3.2-3B-Instruct-Q4_K_S.gguf",
        "size": "2GB (Q4_K_S)",
        "description": "Finetuned Llama3.2"
    },
    "3": {
        "name": "Gemma 3-4B",
        "repo_id": "unsloth/gemma-3-4b-it-GGUF",
        "filename": "ggemma-3-4b-it-Q4_K_S.gguf",
        "size": "2.4GB (Q4_K_S)",             "description": "Excellent efficiency, multimodal support"
    },
    "4": {                                            "name": "Custom",
        "repo_id": None,
        "filename": None
    }
}

    if model_choice not in model_info:
        print("❌ Invalid choice. Defaulting to DeepSeek-R1")
        model_choice = "1"

    if model_choice == "4":
        print("\n📝 Custom Model Details:")
        repo_id = input("Repo ID (e.g., unsloth/DeepSeek-V3.1-Terminus-GGUF): ").strip()
        filename = input("Filename (e.g., model-Q4_K_M.gguf): ").strip()
        selected_model = {
            "name": filename.replace(".gguf", ""),
            "repo_id": repo_id,
            "filename": filename,
            "size": "Unknown",                                                            "description": "User-provided custom model"
    }
    else:
        selected_model = model_info[model_choice]
    
    # Download model if not already prese
    model_dir = "/data/models" 

    os.makedirs(model_dir, exist_ok=True)
    
    model_path = f"{model_dir}/{selected_model['filename']}"

    if not os.path.exists(model_path):
      print(f"📦 Downloading {selected_model['repo_id']}/{selected_model['filename']}...")
      
      subprocess.run(["hf", "download",    selected_model["repo_id"],
        selected_model["filename"],
        "--local-dir", model_dir ], check=True)
      print(f"✅ Model downloaded to {model_path}") 
    else:                                       print(f"✅ Model already exists: {model_path}")

    print("Setting up llama.cpp persistence system...", file=sys.stderr)

    # Create model storage directory
    os.makedirs("/opt/models/unsloth", exist_ok=True)

    # --- Start llama.cpp server ---
    print(f"📦 Selected Model: {selected_model['name']} ({selected_model['size']})")
    print(f"📦 Model Description: {selected_model['description']}")
    print("📝 To get started:")
    print("   1. Connect via SSH below")
    print("   2. Run: llama-cli -m /data/models/{model_name}.gguf")
    
    inject_ssh_key()
    subprocess.run(["/usr/sbin/sshd"])

    # Forward the SSH port and print the connection command
    with modal.forward(22, unencrypted=True) as tunnel:
        ssh_command = f"ssh root@{tunnel.host} -p {tunnel.unencrypted_port}"
        print("\n🚀 Your Unsloth llama.cpp Playroom is ready!")
        print("Paste this command into your terminal:")
        print(ssh_command)

        idle_time = 0
        check_interval = 15 # all these will be centralized
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

# RDP Desktop launch functions
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


# Menu-driven local entrypoint.
@app.local_entrypoint()
def main():
  
    from ui_utils import create_box, show_spinner
    from quotes_loader import get_random_quote, format_quote
    from utils import inject_ssh_key, display_system_info
    from config import IDLE_TIMEOUT_SECONDS, get_resource_config, GPU_TYPES
    from gpu_utils import get_gpu_config, get_available_gpus

    banner = """
╔══════════════════════════════════════════════════════════╗
║                                                          ║
║            🚀  DEVBOX LAUNCHER  🚀                ║
║                                                          ║
║              " Potatoes Taste Nice 🤔 "               ║
║                                                          ║
╚══════════════════════════════════════════════════════════╝
"""
    print(banner)

    quote = get_random_quote()
    quote_box = format_quote(quote)
    create_box(quote_box, "💭 Programming Wisdom")
    display_system_info()

    menu_box = """
    🎯 Choose your DevBox Config:
    1. 🛠️  Standard DevBox general purpose development environment with optional extra packages
    
    2. 📄 Document Processing Box
    Pandoc + Full TeX Live for document work
    
    3. 🤖 AI Assistants Box
    Includes OpenCode and Gemini CLI
    
    4. 🧠 LLM Playroom 
    Ollama for AI experimentation
    
    5. 🖥️  RDP Desktop Box Full graphical desktop with XFCE and RDP access
    
    6. 🧠 llama.cpp Playroom
    Raw C++ Inference Power, With Custom Model Selection
    7. 🔍 Forensics Analysis
    Analysis Machine using Volatilty3 and other tools
    """
    create_box(menu_box, "🚀 LAUNCH OPTIONS")
    
    try:
      choice = input("Enter your choice (1-7): ").strip()
    except EOFError:
      print("\nNo input received. Exiting.")
      return
      
    print(choice)
    if choice == "1": #remember to adjust subsequent indents at package_selction
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
        
        # Replace 'python' with 'python-is-python3' for Debian compatibility.
        if "python" in package_list:
          package_list[package_list.index("python")]= "python-is-python3"
          print("🔄 Replaced 'python' with 'python-is-python3' for Debian compatibility.")

        if package_list:
          print(f"✅ Requesting with additional tools: {', '.join(package_list)}")
        else:
          print("✅ No extra tools requested.")

        gpu_box = """
        🎮 Add GPU acceleration?
        • T4: Cost-effective, good for inference
        • L4: More Performant than T4
        • A10G: Higher performance, more VRAM
        (Enter 'y' To Attach a GPU, anything else for CPU-only)
        """
        create_box(gpu_box, "⚡ GPU ACCELERATION")
        
        try:
          gpu_choice = input("Attach GPU? (y/n): ").lower().strip()
        except EOFError:
          gpu_choice = "n"

          if gpu_choice == "y":
            gpu_menu = """
            1. 🎯 T4 GPU (Cost-effective, good for inference)
            2. 🚀 L4 GPU (More Performant than T4)
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
🎯 Launching with {gpu_name} GPU... Silicon Dust 🔥
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
 Potatoes Have High Carbohydrates Content 😉
"""
            create_box(cpu_box, "🚀 STANDARD DEVBOX")
            show_spinner("Preparing your DevBox", 2)
            launch_devbox.remote(extra_packages=package_list)

    elif choice == "2":
        doc_box = """
        📄 Launching Document Processing Box...
        📚 Pandoc + Full TeX Live Distribution
        """
        create_box(doc_box, "📄 DOCUMENT PROCESSING")
        show_spinner("Setting up document tools", 2)
        launch_doc_processor.remote()

    elif choice == "3":
        assistants_box = """
        🤖 Launching AI Assistants Box...
        🧠 Includes OpenCode and Gemini CLI
        🚀 Let's build something amazing together!
        """
        create_box(assistants_box, "🤖 AI ASSISTANTS")
        show_spinner("Initializing AI assistants", 2)
        launch_assisted_coding.remote()

    elif choice == "4":
        llm_box = """
        🧠 Launching LLM Playroom...
        🤖 Ollama with DeepSeek R1 (8B distilled)
        🚀 Ready for AI experimentation!
        """
        create_box(llm_box, "🧠 LLM PLAYROOM")
        show_spinner("Initializing LLM environment", 2)
        launch_llm_playroom.remote()

    elif choice == "5":
        rdp_box = """
        🖥️  Launching RDP Desktop Box...
        🖼️  XFCE Desktop Environment + RDP access
        """
        create_box(rdp_box, "🖥️  RDP DESKTOP")
        show_spinner("Setting up desktop environment", 2)
        
        package_box = """
        📦 Want to install additional desktop tools?
        Examples: firefox gedit vscode libreoffice(leave empty for default XFCE setup)
        """
        create_box(package_box, "🖥️  EXTRA DESKTOP PACKAGES")
        try:
          tools_input = input("Enter desktop tools(space-separated): ").strip()
        except EOFError:
          tools_input = ""

        package_list = tools_input.split() if tools_input else []

        if package_list:
          print(f"✅ Requesting with additional tools: {', '.join(package_list)}")
        else:
          print("✅ No extra desktop tools requested.")

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
            gpu_launch_box = f"""
            🎯 Launching RDP Desktop with {gpu_name} GPU...
            """
            create_box(gpu_launch_box, f"🚀 {gpu_name} POWERED RDP")
            show_spinner("Initializing GPU RDP environment", 2)
            launch_func.remote(extra_packages=package_list)
          else:
            print("❌ Invalid GPU choice. Please run again.")
            return
        else:
            cpu_box = """
            🖥️  Launching RDP Desktop (CPU-only)...
            """
            create_box(cpu_box, "🚀 RDP DESKTOP")
            show_spinner("Preparing your RDP Desktop", 2)
            launch_rdp_devbox.remote(extra_packages=package_list)

    elif choice == "6":
        llamacpp_box = """
        🧠 Launching llama.cpp Playroom...
        Prebuilt CPU-optimized llama.cpp binaries from official releases
        Models available:
        • DeepSeek-R1
        • Qwen3-Coder
        • Gemma 3-4B
        """
        create_box(llamacpp_box, "🧠 LLAMA.CPP PLAYROOM")
        show_spinner("Preparing llama.cpp environment", 2)
        launch_llamacpp_playroom.remote()
 
    elif choice == "7":
        forensics_box = """
        Immerse Yourself Into The Bits.... 01101010101010100101
        """
        create_box(forensics_box, "Forensics Machine")
        show_spinner("Interleaving Bits... Hold On Tight!", 3)
        launch_forensics_image.remote()

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
        . 7 for Forwnsics Machine
        """
        create_box(error_box, "❌ ERROR")
