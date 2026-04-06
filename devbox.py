import modal
import random
import platform

from images import (
    standard_devbox_image, cuda_devbox_image, doc_processing_image,
    assisted_coding_image, llm_playroom_image, llamacpp_cpu_image, rdp_devbox_image, forensic_analysis_image
)
from shared_runtime import run_devbox_shared, run_rdp_devbox_shared
from config import get_resource_config, LLAMACPP_DEVBOX_ARGS, LLAMACPP_IDLE_TIMEOUT


app = modal.App(
    name="personal-devbox-launcher",
)


dev_volume = modal.Volume.from_name("my-dev-volume", create_if_missing=True)

juicy_secrets = [modal.Secret.from_name("ssh-public-key"), modal.Secret.from_name("gemini-api-key"), modal.Secret.from_name("exa-api-key")] # Right now, all boxes will be filled with these secrets even if it may not directly be intented.

# Common arguments for the devbox functions loaded from config.py and None values such as secret and volume are filled with values defined above
cpu_devbox_args = get_resource_config("cpu", secrets= juicy_secrets, volume = dev_volume)

cpu_devbox_args_rdp = get_resource_config("cpu", secrets = juicy_secrets, volume = dev_volume, is_rdp = True)

gpu_devbox_args = get_resource_config("gpu", secrets = juicy_secrets, volume = dev_volume, is_rdp = True)

gpu_devbox_args_rdp = get_resource_config("gpu", secrets = juicy_secrets, volume = dev_volume, is_rdp = True)

# llama.cpp Research Center config - fill in secrets and volume
llamacpp_devbox_args = LLAMACPP_DEVBOX_ARGS.copy()
llamacpp_devbox_args["secrets"] = juicy_secrets
llamacpp_devbox_args["volumes"] = {"/data": dev_volume}

@app.function(image=standard_devbox_image, **cpu_devbox_args)
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

@app.function(image=doc_processing_image, **gpu_devbox_args)
def launch_doc_processor():
    """Launches a document processing environment with Pandoc and TeX Live."""
    run_devbox_shared(extra_packages=None)

@app.function(image=assisted_coding_image, **cpu_devbox_args)
def launch_assisted_coding():
    """Launches a development environment with Gemini CLI & OpenCode pre-installed."""
    run_devbox_shared(extra_packages=None)

@app.function(image=llm_playroom_image, **gpu_devbox_args_rdp) # Needs review
def launch_llm_playroom():
    """Launches an LLM Playroom environment with Ollama and preloaded models."""
    run_devbox_shared(extra_packages=None) # add model selection here too!

@app.function(image=forensic_analysis_image, **cpu_devbox_args)
def launch_forensics_image():
  """ Launches A Forensic Analysis Machine With Volatilty3 pre-installed. """
  run_devbox_shared(extra_packages=None)

# llama.cpp Research Center - Curated Model Catalog
LLAMACPP_MODELS = {
    "1": {
        "name": "Qwen3.5-9B-Instruct",
        "repo_id": "unsloth/Qwen3.5-9B-GGUF",
        "filename": "Qwen3.5-9B-Q4_K_M.gguf",
        "size": "5.68GB",
        "type": "text",
        "description": "Best overall - thinking mode, 256K context",
        "function_calling": True,
        "settings": {"temp": 0.7, "top_p": 0.8, "top_k": 20}
    },
    "2": {
        "name": "Dolphin3.0-Llama3.2-3B",
        "repo_id": "QuantFactory/Dolphin3.0-Llama3.2-3B-GGUF",
        "filename": "Dolphin3.0-Llama3.2-3B.Q4_K_M.gguf",
        "size": "~2.5GB",
        "type": "text",
        "description": "Fast, abliterated, general use",
        "function_calling": True,
        "settings": {"temp": 0.7, "top_p": 0.9, "top_k": 40}
    },
    "3": {
        "name": "DeepSeek-R1-Distill-Qwen-7B-Uncensored",
        "repo_id": "mradermacher/DeepSeek-R1-Distill-Qwen-7B-Uncensored",
        "filename": "DeepSeek-R1-Distill-Qwen-7B-Uncensored.Q4_K_M.gguf",
        "size": "~5GB",
        "type": "text",
        "description": "Reasoning specialist - science, math, analysis",
        "function_calling": True,
        "settings": {"temp": 0.6, "top_p": 0.95, "top_k": 20}
    },
    "4": {
        "name": "Qwen2.5-Coder-7B",
        "repo_id": "unsloth/Qwen2.5-Coder-7B-Instruct-GGUF",
        "filename": "Qwen2.5-Coder-7B-Instruct-Q4_K_M.gguf",
        "size": "~5GB",
        "type": "text",
        "description": "Coding specialist - 92.7% HumanEval",
        "function_calling": True,
        "settings": {"temp": 0.6, "top_p": 0.95, "top_k": 20}
    },
    "5": {
        "name": "SmolVLM-500M",
        "repo_id": "ggml-org/SmolVLM-500M-Instruct-GGUF",
        "filename": "ggml-model-mmproj-f16.gguf",
        "size": "~1.5GB",
        "type": "vision",
        "description": "Fast image captioning",
        "function_calling": False,
        "settings": {"temp": 0.7, "top_p": 0.9, "top_k": 40}
    },
    "6": {
        "name": "Gemma3-4B",
        "repo_id": "unsloth/gemma-3-4b-it-GGUF",
        "filename": "gemma-3-4b-it-Q4_K_M.gguf",
        "size": "~2.4GB",
        "type": "vision",
        "description": "Good multimodal - images + text",
        "function_calling": True,
        "settings": {"temp": 0.7, "top_p": 0.8, "top_k": 20}
    },
    "7": {
        "name": "Custom Model",
        "repo_id": None,
        "filename": None,
        "size": "User-defined",
        "type": "text",
        "description": "Any GGUF model from HuggingFace",
        "function_calling": True,
        "settings": {"temp": 0.7, "top_p": 0.9, "top_k": 40}
    },
}
#The models list will be moved to a better /dedicated file
@app.function(image=llamacpp_cpu_image, **llamacpp_devbox_args)
def launch_llamacpp_playroom():
    """llama.cpp Research Center with curated models, WebUI, and EXA Search."""
    import os
    import shutil
    import subprocess
    import sys
    import modal
    import time
    import json
    import httpx
    from utils import inject_ssh_key
    from exa_helper import get_exa_api_key, get_tools_for_model
    
    modal.interact()  # Enable user input
    
    print("\n🧠 Launching llama.cpp Research Center")
    print("💻 CPU-Optimized Inference")
    print("🔍 EXA Search Integration")
    print("🌐 Built-in WebUI")
    
    # --- Persistence Setup ---
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
    
    # --- Model Selection ---
    print("\n📦 Model Selection:")
    for key, model in LLAMACPP_MODELS.items():
        print(f"{key}. {model['name']} - {model['description']}")
        print(f"   Size: {model['size']} | Type: {model['type']}")
    
    try:
        model_choice = input("\nEnter model number (1-7): ").strip()
    except EOFError:
        model_choice = "1"
    
    if model_choice not in LLAMACPP_MODELS:
        print("❌ Invalid choice. Defaulting to Qwen3.5-9B")
        model_choice = "1"
    
    selected_model = LLAMACPP_MODELS[model_choice].copy()
    
    # Handle custom model input
    if model_choice == "7":
        print("\n📝 Custom Model Details:")
        repo_id = input("Repo ID (e.g., unsloth/Qwen3.5-9B-GGUF): ").strip()
        filename = input("Filename (e.g., model-Q4_K_M.gguf): ").strip()
        selected_model["repo_id"] = repo_id
        selected_model["filename"] = filename
        selected_model["name"] = filename.replace(".gguf", "")
    
    # --- Download Model ---
    model_dir = "/data/models"
    os.makedirs(model_dir, exist_ok=True)
    model_path = f"{model_dir}/{selected_model['filename']}"
    
    if not os.path.exists(model_path):
        print(f"\n📦 Downloading {selected_model['repo_id']}/{selected_model['filename']}...")
        print("   This may take a few minutes on first run...")
        
        try:
            subprocess.run([
                "hf", "download",
                selected_model["repo_id"],
                selected_model["filename"],
                "--local-dir", model_dir
            ], check=True)
            print(f"✅ Model downloaded to {model_path}")
        except subprocess.CalledProcessError:
            print(f"❌ Download failed. Check repo_id and filename.")
            print(f"   Repo: {selected_model['repo_id']}")
            print(f"   File: {selected_model['filename']}")
            return
    else:
        print(f"✅ Model already cached: {model_path}")
    
    # --- EXA Search Check ---
    exa_key = get_exa_api_key()
    if exa_key:
        print("✅ EXA Search API key found")
        use_exa = True
    else:
        print("⚠️  EXA Search API key not found. Web search disabled.")
        print("   Add 'exa-api-key' secret to Modal to enable.")
        use_exa = False
    
    # --- Start llama-server ---
    model_settings = selected_model.get('settings', {})
    
    server_cmd = [
        "llama-server",
        "-m", model_path,
        "--host", "0.0.0.0",
        "--port", "8080",
        "--threads", "2",
        "--ctx-size", "4096",
        "--batch-size", "512",
        "--mlock",
        "--jinja",  # Enable function calling + WebUI
        "--temp", str(model_settings.get('temp', 0.7)),
        "--top-p", str(model_settings.get('top_p', 0.9)),
        "--top-k", str(model_settings.get('top_k', 40)),
    ]
    
    print(f"\n🚀 Starting llama-server for {selected_model['name']}...")
    print(f"   Settings: temp={model_settings.get('temp', 0.7)}, top_p={model_settings.get('top_p', 0.9)}")
    
    # Start server in background
    server_process = subprocess.Popen(
        server_cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE
    )
    
    # Wait for server to be ready
    time.sleep(3)
    for i in range(30):
        try:
            resp = httpx.get("http://localhost:8080/health", timeout=1.0)
            if resp.status_code == 200:
                print("✅ llama-server ready!")
                break
        except:
            pass
        time.sleep(1)
    else:
        print("❌ llama-server failed to start. Check model file.")
        server_process.terminate()
        return
    
    # --- SSH Setup ---
    inject_ssh_key()
    subprocess.run(["/usr/sbin/sshd"])
    
    # --- Port Forwarding ---
    with modal.forward(22, unencrypted=True) as ssh_tunnel:
        ssh_command = f"ssh root@{ssh_tunnel.host} -p {ssh_tunnel.unencrypted_port}"
        
    with modal.forward(8080, unencrypted=True) as web_tunnel:
            web_url = f"http://{web_tunnel.host}:{web_tunnel.unencrypted_port}"
            
            print("\n" + "="*60)
            print("🚀 Your llama.cpp Research Center is ready!")
            print("="*60)
            print(f"\n🌐 WebUI: {web_url}")
            print(f"   (Open in browser for chat interface)")
            print(f"\n🔐 SSH: {ssh_command}")
            print(f"\n🧠 Model: {selected_model['name']} ({selected_model['size']})")
            if use_exa:
                print(f"🔍 EXA Search: Enabled (function calling)")
            print(f"\n⏰ Idle timeout: {LLAMACPP_IDLE_TIMEOUT // 60} minutes")
            print("\n" + "="*60)
            
            # --- Idle Monitor ---
            idle_time = 0
            check_interval = 30
            
            while idle_time < LLAMACPP_IDLE_TIMEOUT:
                time.sleep(check_interval)
                
                # Check for active SSH sessions
                ssh_result = subprocess.run(
                    "ps -ef | grep 'sshd: root@' | grep -v grep",
                    shell=True,
                    capture_output=True,
                )
                
                # Check for active WebUI connections
                web_active = False
                try:
                    stats = httpx.get("http://localhost:8080/health", timeout=1.0)
                    web_active = True  # Server is running
                except:
                    pass
                
                if ssh_result.stdout or web_active:
                    idle_time = 0
                else:
                    idle_time += check_interval
                    remaining = LLAMACPP_IDLE_TIMEOUT - idle_time
                    print(f"\r💤 No activity. Shutting down in {remaining // 60}m {remaining % 60}s...", end="", flush=True)
            
            print(f"\n\n⏰ Idle timeout reached ({LLAMACPP_IDLE_TIMEOUT}s). Shutting down.")
            server_process.terminate()
# Menu-driven local entrypoint.
@app.local_entrypoint()
def main():
  
    from ui_utils import create_box, show_spinner
    from quotes_loader import get_random_quote, format_quote
    from utils import inject_ssh_key, display_system_info
    from config import IDLE_TIMEOUT_SECONDS
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
    
    6. 🔬 llama.cpp Research Center
    Curated models + WebUI + EXA Search + Multimodal
    
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

      ⚠️  GPU usage incurs charges on your Modal account.
         See modal.com/pricing for current rates.
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
            
            gpu_launch_box = f"🎯 Launching with {gpu_name} GPU... Silicon Dust 🔥"
            create_box(gpu_launch_box, f"🚀 {gpu_name} POWERED")
            show_spinner("Initializing GPU environment", 2)
            launch_func.remote(extra_packages=package_list)
          else:
            print("❌ Invalid GPU choice. Please run again.")
            return
      else:
        cpu_box = """🖥️  Launching CPU-only environment...
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

        ⚠️  GPU usage incurs charges on your Modal account.
           See modal.com/pricing for current rates.
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
        research_box = """
        🔬 Launching llama.cpp Research Center...
        
        Models available:
        • Qwen3.5-9B (General reasoning)
        • Dolphin3.0-3B (Fast, abliterated)
        • DeepSeek-R1-7B (Science specialist)
        • Qwen2.5-Coder-7B (Coding specialist)
        • SmolVLM-500M (Image captioning)
        • Gemma3-4B (Multimodal)
        • Custom (Any HuggingFace GGUF)
        
        Features:
        • Built-in WebUI (browser chat)
        • EXA Search integration
        • Function calling support
        """
        create_box(research_box, "🔬 LLAMA.CPP RESEARCH CENTER")
        show_spinner("Preparing research environment", 3)
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
        • 6 for llama.cpp Research Center
        - 7 for Forensics Machine
        """
        create_box(error_box, "❌ ERROR")
