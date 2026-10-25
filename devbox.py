import modal
import os
from datetime import datetime, timedelta, timezone

from devbox_core.images import (
    standard_devbox_image, cuda_devbox_image, doc_processing_image,
    assisted_coding_image, llm_playroom_image, llamacpp_cpu_image, rdp_devbox_image, forensic_analysis_image
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

ssh_secret = modal.Secret.from_name("ssh-public-key")
gemini_secret = modal.Secret.from_name("gemini-api-key")
exa_secret = modal.Secret.from_name("exa-api-key")

_wiring = build_devbox_args(
    [ssh_secret],
    dev_volume,
    secret_sets={
        "coding": [ssh_secret, gemini_secret],
        "forensics": [ssh_secret],
        "exa": [ssh_secret, exa_secret],
    },
)
cpu_devbox_args = _wiring["cpu_devbox_args"]

cpu_devbox_args_rdp = _wiring["cpu_devbox_args_rdp"]

gpu_devbox_args = _wiring["gpu_devbox_args"]

gpu_devbox_args_rdp = _wiring["gpu_devbox_args_rdp"]

assisted_devbox_args = _wiring["assisted_devbox_args"]
forensics_devbox_args = _wiring["forensics_devbox_args"]

llamacpp_devbox_args = _wiring["llamacpp_devbox_args"]

llamacpp_gpu_devbox_args = _wiring["llamacpp_gpu_devbox_args"]

@app.function(image=standard_devbox_image, **cpu_devbox_args)
def launch_devbox(extra_packages=None):
    """Launches a non-GPU personal development environment."""
    run_devbox_shared(extra_packages, devbox_type="standard_devbox", resources=cpu_devbox_args)


@_unless_cpu_only(app.function(image=cuda_devbox_image, gpu="t4", **gpu_devbox_args))
def launch_devbox_t4(extra_packages=None):
    """Launches a T4 GPU-powered personal development environment."""
    run_devbox_shared(extra_packages, devbox_type="cuda_devbox_t4", resources={**gpu_devbox_args, "gpu": "t4"})


@_unless_cpu_only(app.function(image=cuda_devbox_image, gpu="l4", **gpu_devbox_args))
def launch_devbox_l4(extra_packages=None):
    """Launches an L4 GPU-powered personal development environment."""
    run_devbox_shared(extra_packages, devbox_type="cuda_devbox_l4", resources={**gpu_devbox_args, "gpu": "l4"})


@_unless_cpu_only(app.function(image=cuda_devbox_image, gpu="a10g", **gpu_devbox_args))
def launch_devbox_a10g(extra_packages=None):
    """Launches an A10G GPU-powered personal development environment."""
    run_devbox_shared(extra_packages, devbox_type="cuda_devbox_a10g", resources={**gpu_devbox_args, "gpu": "a10g"})


@_unless_cpu_only(app.function(image=cuda_devbox_image, gpu="L40S", **gpu_devbox_args))
def launch_devbox_l40s(extra_packages=None):
    """Launches an L40S GPU-powered personal development environment."""
    run_devbox_shared(extra_packages, devbox_type="cuda_devbox_l40s", resources={**gpu_devbox_args, "gpu": "L40S"})

@app.function(image=rdp_devbox_image, **cpu_devbox_args_rdp)
def launch_rdp_devbox(extra_packages=None):
    """Launches an RDP desktop development environment."""
    run_rdp_devbox_shared(extra_packages, devbox_type="rdp_devbox", resources=cpu_devbox_args_rdp)

@_unless_cpu_only(app.function(image=rdp_devbox_image, gpu="t4", **gpu_devbox_args_rdp))
def launch_rdp_devbox_t4(extra_packages=None):
    """Launches an RDP desktop with T4 GPU."""
    run_rdp_devbox_shared(extra_packages, devbox_type="rdp_devbox_t4", resources={**gpu_devbox_args_rdp, "gpu": "t4"})

@_unless_cpu_only(app.function(image=rdp_devbox_image, gpu="l4", **gpu_devbox_args_rdp))
def launch_rdp_devbox_l4(extra_packages=None):
    """Launches an RDP desktop with L4 GPU."""
    run_rdp_devbox_shared(extra_packages, devbox_type="rdp_devbox_l4", resources={**gpu_devbox_args_rdp, "gpu": "l4"})

@_unless_cpu_only(app.function(image=rdp_devbox_image, gpu="a10g", **gpu_devbox_args_rdp))
def launch_rdp_devbox_a10g(extra_packages=None):
    """Launches an RDP desktop with A10G GPU."""
    run_rdp_devbox_shared(extra_packages, devbox_type="rdp_devbox_a10g", resources={**gpu_devbox_args_rdp, "gpu": "a10g"})


@_unless_cpu_only(app.function(image=rdp_devbox_image, gpu="L40S", **gpu_devbox_args_rdp))
def launch_rdp_devbox_l40s(extra_packages=None):
    """Launches an RDP desktop with L40S GPU."""
    run_rdp_devbox_shared(extra_packages, devbox_type="rdp_devbox_l40s", resources={**gpu_devbox_args_rdp, "gpu": "L40S"})

@app.function(image=doc_processing_image, **gpu_devbox_args)
def launch_doc_processor():
    """Launches a document processing environment with Pandoc and TeX Live."""
    run_devbox_shared(extra_packages=None, devbox_type="doc_processing", resources=gpu_devbox_args)

@app.function(image=assisted_coding_image, **assisted_devbox_args)
def launch_assisted_coding():
    """Launches a development environment with Gemini CLI & OpenCode pre-installed."""
    run_opencode_shared(extra_packages=None, resources=assisted_devbox_args)

@app.function(image=llm_playroom_image, **gpu_devbox_args_rdp)
def launch_llm_playroom():
    """Launches an LLM Playroom environment with Ollama and preloaded models."""
    run_devbox_shared(extra_packages=None, devbox_type="llm_playroom", resources=gpu_devbox_args_rdp)

@app.function(image=forensic_analysis_image, **forensics_devbox_args)
def launch_forensics_image():
  """Launches the forensic and reverse-engineering environment."""
  run_opencode_shared(extra_packages=None, resources=forensics_devbox_args, forensic=True)

# llama.cpp Research Center - Curated Model Catalog lives in
# devbox_core/llamacpp_models.py (imported function-locally below).
@app.function(image=llamacpp_cpu_image, **llamacpp_devbox_args)
def launch_llamacpp_playroom():
    """llama.cpp Research Center with curated models, WebUI, and EXA Search."""
    from runtime.llamacpp_runtime import run_llamacpp_playroom
    run_llamacpp_playroom("cpu", resources=llamacpp_devbox_args)


@_unless_cpu_only(app.function(image=llamacpp_cpu_image, **llamacpp_gpu_devbox_args))
def launch_llamacpp_playroom_gpu():
    """GPU-accelerated llama.cpp Research Center with curated models, WebUI, and EXA Search."""
    from runtime.llamacpp_runtime import run_llamacpp_playroom
    run_llamacpp_playroom("gpu", resources=llamacpp_gpu_devbox_args)


# Menu-driven local entrypoint.
@app.local_entrypoint()
def main():
  
    from ui.ui_utils import create_box, show_spinner
    from ui.quotes_loader import get_random_quote, format_quote
    from runtime.utils import inject_ssh_key, display_system_info
    from devbox_core.config import IDLE_TIMEOUT_SECONDS

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
    
    3. 🤖 AI Coding Box
    OpenCode web UI, SSH, and Gemini CLI
    
    4. 🧠 LLM Playroom 
    Ollama for AI experimentation
    
    5. 🖥️  RDP Desktop Box Full graphical desktop with XFCE and RDP access
    
    6. 🔬 llama.cpp Research Center (CPU)
    Curated models + WebUI + EXA Search + Multimodal
    
    7. 🔍 Forensics Analysis
    Analysis Machine using Volatilty3 and other tools

    8. 🚀 llama.cpp Research Center (GPU)
    GPU-accelerated inference + 32K context + T4 GPU

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
      handle_standard_choice(launch_devbox, launch_devbox_t4, launch_devbox_l4, launch_devbox_a10g, launch_devbox_l40s, CPU_ONLY)

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
        🤖 Launching AI Coding Box...
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
      handle_rdp_choice(launch_rdp_devbox, launch_rdp_devbox_t4, launch_rdp_devbox_l4, launch_rdp_devbox_a10g, launch_rdp_devbox_l40s, CPU_ONLY)

    else:
      from ui.launcher_menu import handle_simple_choice
      handle_simple_choice(choice, launch_llamacpp_playroom, launch_forensics_image, launch_llamacpp_playroom_gpu, CPU_ONLY)


@app.function(image=standard_devbox_image, **cpu_devbox_args)
def show_costs(reconcile: bool = False):
    """Print accumulated DevBox cost ledger from /data/.cost."""
    from runtime.cost_tracker import list_sessions, summarize

    sessions = list_sessions()
    summary = summarize(sessions)
    print("=" * 60)
    print("DevBox Cost Report")
    print("=" * 60)
    print(f"Sessions: {summary['sessions']}")
    print(f"Total elapsed: {summary['total_elapsed_s']}s ({summary['total_elapsed_s'] / 3600:.2f}h)")
    print(f"Total estimated cost: ${summary['total_estimated_cost_usd']:.4f} USD")
    print("-" * 60)
    print("By box type:")
    for box, info in sorted(summary["by_type"].items()):
        print(f"  {box}: {info['sessions']} sessions, {info['elapsed_s']:.0f}s, ${info['cost']:.4f}")
    print("-" * 60)
    print("Recent sessions:")
    for s in sessions[-10:]:
        print(
            f"  {s.get('started_at')}  {s.get('devbox_type'):24s}  "
            f"{s.get('elapsed_s', 0):8.0f}s  ${s.get('estimated_cost_usd', 0):.4f}  {s.get('status')}"
        )
    print("=" * 60)
    if reconcile:
        try:
            import modal

            ws = modal.Workspace()
            end = datetime.now(timezone.utc)
            start = end - timedelta(days=30)
            report = ws.billing.report(start=start, end=end, resolution="d", tag_names=["*"])
            print("Reconciliation (Modal billing report):")
            for item in report:
                print(f"  {item.object_id}: ${item.cost} ({item.cost_by_resource})")
        except Exception as e:
            print(f"Reconciliation failed: {e}")


@app.local_entrypoint()
def cost_report(reconcile: bool = False):
    """Local entrypoint: modal run devbox.py::cost_report"""
    show_costs.remote(reconcile=reconcile)
