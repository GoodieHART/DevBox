import modal
import os

from devbox_core.images import (
    standard_devbox_image, cuda_devbox_image, doc_processing_image,
    assisted_coding_image, opencode_image, llm_playroom_image, llamacpp_cpu_image, rdp_devbox_image, forensic_analysis_image
)
from runtime.shared_runtime import run_devbox_shared, run_rdp_devbox_shared, run_opencode_shared
from devbox_core.config import build_devbox_args


# Paywall gate: set DEVBOX_CPU_ONLY=1 to run this app on a Modal account
# without a GPU payment method. GPU-backed launchers stay defined as plain
# functions but are never registered on the Modal app, so Modal skips GPU
# validation entirely. Unset (default) = today's behavior, unchanged.
# NOTE: kept inline here (not in devbox_core/) on purpose — devbox.py's
# top-level imports must all be packaged into every image, and this gate
# needs zero packaging.
CPU_ONLY = os.environ.get("DEVBOX_CPU_ONLY", "").strip().lower() in ("1", "true", "yes")


def _unless_cpu_only(decorator):
    """Apply a Modal @app.function decorator unless CPU-only mode is on."""
    def apply(fn):
        return fn if CPU_ONLY else decorator(fn)
    return apply


app = modal.App(
    name="personal-devbox-launcher",
)


dev_volume = modal.Volume.from_name("my-dev-volume", create_if_missing=True)

juicy_secrets = [modal.Secret.from_name("ssh-public-key"), modal.Secret.from_name("gemini-api-key"), modal.Secret.from_name("exa-api-key")] # Right now, all boxes will be filled with these secrets even if it may not directly be intented.

_wiring = build_devbox_args(juicy_secrets, dev_volume)
cpu_devbox_args = _wiring["cpu_devbox_args"]

cpu_devbox_args_rdp = _wiring["cpu_devbox_args_rdp"]

gpu_devbox_args = _wiring["gpu_devbox_args"]

gpu_devbox_args_rdp = _wiring["gpu_devbox_args_rdp"]

opencode_devbox_args = _wiring["opencode_devbox_args"]

assisted_devbox_args = _wiring["assisted_devbox_args"]

llamacpp_devbox_args = _wiring["llamacpp_devbox_args"]

llamacpp_gpu_devbox_args = _wiring["llamacpp_gpu_devbox_args"]

@app.function(image=standard_devbox_image, **cpu_devbox_args)
def launch_devbox(extra_packages: list[str] | None = None):
    """Launches a non-GPU personal development environment."""
    run_devbox_shared(extra_packages, devbox_type="standard_devbox")


@_unless_cpu_only(app.function(image=cuda_devbox_image, gpu="t4", **gpu_devbox_args))
def launch_devbox_t4(extra_packages: list[str] | None = None):
    """Launches a T4 GPU-powered personal development environment."""
    run_devbox_shared(extra_packages, devbox_type="cuda_devbox_t4")


@_unless_cpu_only(app.function(image=cuda_devbox_image, gpu="l4", **gpu_devbox_args))
def launch_devbox_l4(extra_packages: list[str] | None = None):
    """Launches an L4 GPU-powered personal development environment."""
    run_devbox_shared(extra_packages, devbox_type="cuda_devbox_l4")


@_unless_cpu_only(app.function(image=cuda_devbox_image, gpu="a10g", **gpu_devbox_args))
def launch_devbox_a10g(extra_packages: list[str] | None = None):
    """Launches an A10G GPU-powered personal development environment."""
    run_devbox_shared(extra_packages, devbox_type="cuda_devbox_a10g")

@app.function(image=rdp_devbox_image, **cpu_devbox_args_rdp)
def launch_rdp_devbox(extra_packages: list[str] = None):
    """Launches an RDP desktop development environment."""
    run_rdp_devbox_shared(extra_packages)

@_unless_cpu_only(app.function(image=rdp_devbox_image, gpu="t4", **gpu_devbox_args_rdp))
def launch_rdp_devbox_t4(extra_packages: list[str] = None):
    """Launches an RDP desktop with T4 GPU."""
    run_rdp_devbox_shared(extra_packages)

@_unless_cpu_only(app.function(image=rdp_devbox_image, gpu="l4", **gpu_devbox_args_rdp))
def launch_rdp_devbox_l4(extra_packages: list[str] = None):
    """Launches an RDP desktop with L4 GPU."""
    run_rdp_devbox_shared(extra_packages)

@_unless_cpu_only(app.function(image=rdp_devbox_image, gpu="a10g", **gpu_devbox_args_rdp))
def launch_rdp_devbox_a10g(extra_packages: list[str] = None):
    """Launches an RDP desktop with A10G GPU."""
    run_rdp_devbox_shared(extra_packages)

@app.function(image=doc_processing_image, **gpu_devbox_args)
def launch_doc_processor():
    """Launches a document processing environment with Pandoc and TeX Live."""
    run_devbox_shared(extra_packages=None, devbox_type="doc_processing")

@app.function(image=assisted_coding_image, **assisted_devbox_args)
def launch_assisted_coding():
    """Launches a development environment with Gemini CLI & OpenCode pre-installed."""
    run_devbox_shared(extra_packages=None, devbox_type="assisted_coding")

@app.function(image=opencode_image, **opencode_devbox_args)
def launch_opencode(extra_packages=None):
    """Launches a dedicated OpenCode server box (browser web UI + SSH)."""
    run_opencode_shared(extra_packages)

@app.function(image=llm_playroom_image, **gpu_devbox_args_rdp)
def launch_llm_playroom():
    """Launches an LLM Playroom environment with Ollama and preloaded models."""
    run_devbox_shared(extra_packages=None, devbox_type="llm_playroom")

@app.function(image=forensic_analysis_image, **cpu_devbox_args)
def launch_forensics_image():
  """ Launches A Forensic Analysis Machine With Volatilty3 pre-installed. """
  run_devbox_shared(extra_packages=None, devbox_type="forensic_analysis")

# llama.cpp Research Center - Curated Model Catalog lives in
# devbox_core/llamacpp_models.py (imported function-locally below).
@app.function(image=llamacpp_cpu_image, **llamacpp_devbox_args)
def launch_llamacpp_playroom():
    """llama.cpp Research Center with curated models, WebUI, and EXA Search."""
    from runtime.llamacpp_runtime import run_llamacpp_playroom
    run_llamacpp_playroom("cpu")


@_unless_cpu_only(app.function(image=llamacpp_cpu_image, **llamacpp_gpu_devbox_args))
def launch_llamacpp_playroom_gpu():
    """GPU-accelerated llama.cpp Research Center with curated models, WebUI, and EXA Search."""
    from runtime.llamacpp_runtime import run_llamacpp_playroom
    run_llamacpp_playroom("gpu")


# Menu-driven local entrypoint.
@app.local_entrypoint()
def main():
  
    from ui.ui_utils import create_box, show_spinner
    from ui.quotes_loader import get_random_quote, format_quote
    from runtime.utils import inject_ssh_key, display_system_info
    from devbox_core.config import IDLE_TIMEOUT_SECONDS
    from runtime.gpu_utils import get_gpu_config, get_available_gpus

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
    
    6. 🔬 llama.cpp Research Center (CPU)
    Curated models + WebUI + EXA Search + Multimodal
    
    7. 🔍 Forensics Analysis
    Analysis Machine using Volatilty3 and other tools

    8. 🚀 llama.cpp Research Center (GPU)
    GPU-accelerated inference + 32K context + T4 GPU

    9. 🤖 OpenCode Box
    Dedicated OpenCode web server (browser UI + SSH, workdir /data)
    """
    create_box(menu_box, "🚀 LAUNCH OPTIONS")
    
    try:
      choice = input("Enter your choice (1-9): ").strip()
    except EOFError:
      print("\nNo input received. Exiting.")
      return
      
    print(choice)
    if choice == "1":
      from ui.launcher_menu import handle_standard_choice
      handle_standard_choice(launch_devbox, launch_devbox_t4, launch_devbox_l4, launch_devbox_a10g, CPU_ONLY)

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
      from ui.launcher_menu import handle_rdp_choice
      handle_rdp_choice(launch_rdp_devbox, launch_rdp_devbox_t4, launch_rdp_devbox_l4, launch_rdp_devbox_a10g, CPU_ONLY)

    else:
      from ui.launcher_menu import handle_simple_choice
      handle_simple_choice(choice, launch_llamacpp_playroom, launch_forensics_image, launch_llamacpp_playroom_gpu, launch_opencode, CPU_ONLY)
