"""GPU picker shared by the Standard and RDP menu flows."""

from ui.ui_utils import create_box, show_spinner


def prompt_gpu_dispatch(launch_map, extra_packages, label=""):
    """Prompt for a GPU type and dispatch to the chosen launcher.

    Args:
        launch_map: maps "1"/"2"/"3" to (name, callable).
        extra_packages: package list forwarded to the launcher.
        label: "standard" or "rdp" — selects the menu/launch copy.
    """
    is_rdp = "rdp" in label.lower()
    if is_rdp:
        gpu_menu = """
        1. 🎯 T4 GPU (Cost-effective, good for graphics)
        2. 🚀 L4 GPU (Newer, more performant than T4)
        3. 💪 A10G GPU (Higher performance, more VRAM)
        """
    else:
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

    if gpu_type_choice in launch_map:
        gpu_name, launch_func = launch_map[gpu_type_choice]
        if is_rdp:
            gpu_launch_box = f"""
            🎯 Launching RDP Desktop with {gpu_name} GPU...
            """
            create_box(gpu_launch_box, f"🚀 {gpu_name} POWERED RDP")
            show_spinner("Initializing GPU RDP environment", 2)
        else:
            gpu_launch_box = f"🎯 Launching with {gpu_name} GPU... Silicon Dust 🔥"
            create_box(gpu_launch_box, f"🚀 {gpu_name} POWERED")
            show_spinner("Initializing GPU environment", 2)
        launch_func.remote(extra_packages=extra_packages)
    else:
        print("❌ Invalid GPU choice. Please run again.")
        return
