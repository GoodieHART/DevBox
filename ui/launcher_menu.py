"""Menu choice handlers for the local launcher entrypoint.

Handlers receive decorated launcher callables and the CPU_ONLY flag as
parameters — never importing devbox (circular).
"""


def handle_standard_choice(launch_devbox, launch_devbox_t4, launch_devbox_l4, launch_devbox_a10g, cpu_only):
    """Choice 1: Standard DevBox with optional extra packages + GPU dispatch."""
    from ui.gpu_picker import prompt_gpu_dispatch
    from ui.ui_utils import create_box, show_spinner

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
        if cpu_only:
            create_box("GPU launchers are disabled in CPU-only mode (DEVBOX_CPU_ONLY=1).\nUnset it or add a GPU payment method to use them.", "⚡ GPU UNAVAILABLE")
            return
        gpu_types = {
            "1": ("T4", launch_devbox_t4),
            "2": ("L4", launch_devbox_l4),
            "3": ("A10G", launch_devbox_a10g),
        }
        prompt_gpu_dispatch(gpu_types, package_list, "standard")
    else:
        cpu_box = """🖥️  Launching CPU-only environment...
        Potatoes Have High Carbohydrates Content 😉
        """
        create_box(cpu_box, "🚀 STANDARD DEVBOX")
        show_spinner("Preparing your DevBox", 2)
        launch_devbox.remote(extra_packages=package_list)


def handle_rdp_choice(launch_rdp_devbox, launch_rdp_devbox_t4, launch_rdp_devbox_l4, launch_rdp_devbox_a10g, cpu_only):
    """Choice 5: RDP Desktop Box with optional extra packages + GPU dispatch."""
    from ui.gpu_picker import prompt_gpu_dispatch
    from ui.ui_utils import create_box, show_spinner

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
        if cpu_only:
            create_box("GPU launchers are disabled in CPU-only mode (DEVBOX_CPU_ONLY=1).\nUnset it or add a GPU payment method to use them.", "⚡ GPU UNAVAILABLE")
            return
        gpu_types = {
            "1": ("T4", launch_rdp_devbox_t4),
            "2": ("L4", launch_rdp_devbox_l4),
            "3": ("A10G", launch_rdp_devbox_a10g),
        }
        prompt_gpu_dispatch(gpu_types, package_list, "rdp")
    else:
        cpu_box = """
        🖥️  Launching RDP Desktop (CPU-only)...
        """
        create_box(cpu_box, "🚀 RDP DESKTOP")
        show_spinner("Preparing your RDP Desktop", 2)
        launch_rdp_devbox.remote(extra_packages=package_list)


def handle_simple_choice(choice, launch_llamacpp_playroom, launch_forensics_image, launch_llamacpp_playroom_gpu, launch_opencode, cpu_only):
    """Choices 6/7/8/9/else: single-launcher flows and the invalid-choice box."""
    from ui.ui_utils import create_box, show_spinner

    if choice == "6":
        research_box = """
        🔬 Launching llama.cpp Research Center...

        Models available:
        • Qwen3.5-9B (General reasoning)
        • Bonsai-8B (1-bit ultra-lightweight)
        • SmolVLM-500M (Image captioning)
        • Gemma4-26B-A4B (Multimodal)
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

    elif choice == "8":
        if cpu_only:
            create_box("GPU launchers are disabled in CPU-only mode (DEVBOX_CPU_ONLY=1).\nUnset it or add a GPU payment method to use them.", "⚡ GPU UNAVAILABLE")
            return
        research_gpu_box = """
        🚀 Launching GPU llama.cpp Research Center...

        Models available:
        • Qwen3.5-9B (General reasoning)
        • Bonsai-8B (1-bit ultra-lightweight)
        • SmolVLM-500M (Image captioning)
        • Gemma4-26B-A4B (Multimodal)
        • Custom (Any HuggingFace GGUF)

        GPU Features:
        • T4 GPU with all layers offloaded
        • 32K context with KV cache quantization
        • Flash Attention for faster inference
        • Built-in WebUI (browser chat)
        • EXA Search integration
        """
        create_box(research_gpu_box, "🚀 GPU LLAMA.CPP RESEARCH CENTER")
        show_spinner("Preparing GPU-accelerated environment", 3)
        launch_llamacpp_playroom_gpu.remote()

    elif choice == "9":
        opencode_box = """
        🤖 Launching OpenCode Box...
        🌐 Web UI (browser) + SSH access
        📁 Workdir /data (persistent)
        🔒 Set OPENCODE_SERVER_PASSWORD secret for password auth (optional)
        """
        create_box(opencode_box, "🤖 OPENCODE BOX")

        # Skippable pre-launch upload to the volume's /data/uploads dir, so the
        # file is available to the REA MCP (and any tool) inside the box.
        upload_box = """
        📎 Upload a file to /data/uploads before launch? (optional)
        Enter a local file or directory path, or press Enter to skip.
        (Skipped automatically in non-interactive / detached runs.)
        """
        create_box(upload_box, "📎 PRE-LAUNCH UPLOAD")
        try:
            upload_path = input("Local path to upload (Enter to skip): ").strip()
        except (EOFError, OSError):
            upload_path = ""

        if upload_path:
            import os
            if not os.path.exists(upload_path):
                create_box(f"⚠️  Path not found: {upload_path}\nSkipping upload.", "📎 UPLOAD SKIPPED")
            else:
                try:
                    import modal
                    volume = modal.Volume.from_name("my-dev-volume")
                    remote_name = os.path.basename(upload_path.rstrip("/")) or "upload"
                    remote_dir = f"/uploads/{remote_name}" if os.path.isdir(upload_path) else None
                    with volume.batch_upload() as batch:
                        if os.path.isdir(upload_path):
                            batch.put_directory(upload_path, f"/uploads/{remote_name}")
                        else:
                            batch.put_file(upload_path, f"/uploads/{remote_name}")
                    create_box(
                        f"✅ Uploaded {upload_path}\n   -> /data/uploads/{remote_name}\n"
                        f"   Reference it in OpenCode/REA as /data/uploads/{remote_name}",
                        "📎 UPLOAD COMPLETE",
                    )
                except Exception as exc:
                    create_box(f"⚠️  Upload failed: {exc}\nContinuing launch.", "📎 UPLOAD FAILED")

        show_spinner("Starting OpenCode server", 2)
        launch_opencode.remote()

    else:
        error_box = """
        ❌ Invalid choice selected.
        Please run the launcher again and choose:
        • 1 for Standard DevBox
        • 2 for Document Processing
        • 3 for AI Assistants Box
        • 4 for LLM Playroom
        • 5 for RDP Desktop Box
        • 6 for llama.cpp Research Center (CPU)
        • 7 for Forensics Machine
        • 8 for llama.cpp Research Center (GPU)
        • 9 for OpenCode Box
        """
        create_box(error_box, "❌ ERROR")
