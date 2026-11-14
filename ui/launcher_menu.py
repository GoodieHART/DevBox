"""Menu choice handlers for the local launcher entrypoint.

Handlers receive decorated launcher callables and the CPU_ONLY flag as
parameters — never importing devbox (circular).
"""


def _network_label(network):
    return {
        "labs": "HTB Labs",
        "starting-point": "HTB Starting Point",
        "both": "HTB Labs + Starting Point",
    }.get(network, network)


def prompt_htb_vm():
    """Ask whether to use HTB VPN VM mode, then which network.

    Returns `labs`, `starting-point`, `both`, or None to launch normally.
    Defaults to Labs when the network prompt is skipped.
    """
    from ui.ui_utils import create_box

    try:
        answer = input("Enable HTB VPN VM mode? (y/n): ").lower().strip()
    except EOFError:
        answer = "n"
    if answer != "y":
        return None

    network_box = """
    🌐 Which HTB network(s) should this box join?
    • 1: HTB Labs (Machines, 10.10.x.x)
    • 2: HTB Starting Point (10.129.x.x)
    • 3: Both - separate tun device per network
    """
    create_box(network_box, "🌐 HTB NETWORK")
    try:
        answer = input("Select network [1]: ").strip()
    except EOFError:
        answer = "1"
    return {"1": "labs", "2": "starting-point", "3": "both"}.get(answer, "labs")


def handle_standard_choice(launch_devbox, launch_devbox_t4, launch_devbox_l4, launch_devbox_a10g, launch_devbox_l40s, cpu_only, launch_devbox_htb=None):
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

    # HTB mode runs in a CPU-only VM Sandbox, so it is offered before the GPU
    # question; answering yes skips GPU dispatch.
    htb_network = prompt_htb_vm()
    if htb_network is not None:
        if launch_devbox_htb is None:
            create_box("HTB VPN mode is unavailable in this launcher build.", "🌐 HTB VPN")
            return
        htb_box = f"""
        🌐 Launching Standard DevBox in HTB VPN VM mode...
        🔗 Network(s): {_network_label(htb_network)}
        ⏳ The VM waits for the VPN handshake before starting SSH.
        """
        create_box(htb_box, "🚀 STANDARD DEVBOX + HTB VPN")
        show_spinner("Bringing up the HTB VPN VM", 3)
        launch_devbox_htb.remote(network=htb_network)
        return

    gpu_box = """
    🎮 Add GPU acceleration?
    • T4: Cost-effective, good for inference
    • L4: More Performant than T4
    • A10G: Higher performance, more VRAM
    • L40S: High-end AI workload, 48 GB VRAM
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
            "4": ("L40S", launch_devbox_l40s),
        }
        prompt_gpu_dispatch(gpu_types, package_list, "standard")
    else:
        cpu_box = """🖥️  Launching CPU-only environment...
        Potatoes Have High Carbohydrates Content 😉
        """
        create_box(cpu_box, "🚀 STANDARD DEVBOX")
        show_spinner("Preparing your DevBox", 2)
        launch_devbox.remote(extra_packages=package_list)


def handle_rdp_choice(launch_rdp_devbox, launch_rdp_devbox_t4, launch_rdp_devbox_l4, launch_rdp_devbox_a10g, launch_rdp_devbox_l40s, cpu_only):
    """Choice 4: RDP Desktop Box with optional extra packages + GPU dispatch."""
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

    quality_box = """
    📶 Low-bandwidth / remote-desktop tuning?
    • y: lower color depth and recommend a smaller client resolution
    • n: keep the default high-quality 32-bit color depth
    """
    create_box(quality_box, "📶 RDP QUALITY")
    try:
        quality_choice = input("Low bandwidth mode? (y/n): ").lower().strip()
    except EOFError:
        quality_choice = "n"
    rdp_quality = "low" if quality_choice == "y" else "auto"

    gpu_box = """
    🎮 Add GPU acceleration for desktop?
    • T4: Cost-effective, good for graphics
    • L4: Newer, more performant than T4
    • A10G: Higher performance, more VRAM
    • L40S: High-end AI workload, 48 GB VRAM
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
            "4": ("L40S", launch_rdp_devbox_l40s),
        }
        prompt_gpu_dispatch(gpu_types, package_list, "rdp", rdp_quality=rdp_quality)
    else:
        cpu_box = """
        🖥️  Launching RDP Desktop (CPU-only)...
        """
        create_box(cpu_box, "🚀 RDP DESKTOP")
        show_spinner("Preparing your RDP Desktop", 2)
        launch_rdp_devbox.remote(extra_packages=package_list, rdp_quality=rdp_quality)


def handle_simple_choice(choice, launch_llamacpp_playroom, launch_forensics_image, launch_llamacpp_playroom_gpu, cpu_only, launch_forensics_htb=None):
    """Choices 5/6/7/else: single-launcher flows and the invalid-choice box."""
    from ui.ui_utils import create_box, show_spinner

    if choice == "5":
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

    elif choice == "6":
        forensics_box = """
        Immerse Yourself Into The Bits.... 01001100 01101111 01110110 01100101
        """
        create_box(forensics_box, "Forensics Machine")
        show_spinner("Interleaving Bits... Hold On Tight!", 3)
        htb_network = prompt_htb_vm()
        if htb_network is not None:
            if launch_forensics_htb is None:
                print("HTB VPN mode is unavailable in this launcher build.")
                return
            htb_box = f"""
            🌐 Forensics box in HTB VPN VM mode...
            🔗 Network(s): {_network_label(htb_network)}
            🖥️  RDP desktop + OpenCode + SSH start after the VPN handshake.
            """
            create_box(htb_box, "🔍 FORENSICS + HTB VPN")
            show_spinner("Bringing up the HTB VPN VM", 3)
            launch_forensics_htb.remote(network=htb_network)
        else:
            launch_forensics_image.remote()

    elif choice == "7":
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

    else:
        error_box = """
        ❌ Invalid choice selected.
        Please run the launcher again and choose:
        • 1 for Standard DevBox
        • 2 for AI Assistants Box
        • 3 for LLM Playroom
        • 4 for RDP Desktop Box
        • 5 for llama.cpp Research Center (CPU)
        • 6 for Forensics Machine
        • 7 for llama.cpp Research Center (GPU)
        """
        create_box(error_box, "❌ ERROR")
