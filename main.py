"""
DevBox Launcher - Main Entry Point

This is the main entry point for the DevBox application,
coordinating all modular components and providing the interactive CLI.

Author: DevBox Launcher
"""

import modal
import sys
import time
import random
import os
import platform
from ui_utils import create_box, show_spinner
from quotes_loader import get_random_quote, format_quote
from launchers import (
    launch_standard_devbox, launch_gpu_devbox, launch_doc_processor,
    launch_gemini_cli, launch_llm_playroom, launch_llamacpp_playroom,
    launch_rdp_desktop, launch_rdp_t4, launch_rdp_l4, launch_rdp_a10g
)
from config import GPU_TYPES
from gpu_utils import get_available_gpus


def display_system_info():
    """Display local system capabilities."""
    try:
        import platform
        cpu_count = os.cpu_count() or 1
        info = f"CPU: {cpu_count} cores"
    except (OSError, AttributeError):
        info = "CPU: Unknown"
    
    system_box = f"""
 🖥️  Local System:
{info}
 🐍 Python: {platform.python_version()}
 💻 Platform: {platform.system()} {platform.release()}
"""
    create_box(system_box, "🖥️  SYSTEM CAPABILITIES")


def get_extra_packages():
    """Prompt user for extra packages and return list."""
    try:
        extra = input("Enter extra apt packages (space-separated, or press Enter to skip): ").strip()
        if not extra:
            return None
        return [pkg.strip() for pkg in extra.split() if pkg.strip()]
    except (EOFError, KeyboardInterrupt):
        print("\nOperation cancelled.")
        return None


def display_gpu_menu():
    """Display GPU selection menu and return user's choice."""
    gpu_types = get_available_gpus()
    
    print("\n" + "="*60)
    create_box("🎮 GPU SELECTION", "Choose your GPU type:")
    
    for i, gpu_type in enumerate(gpu_types, 1):
        description = GPU_TYPES.get(gpu_type, f"{gpu_type} - Available GPU")
        print(f"  {i}. {description}")
    
    print(f"  {' + str(len(gpu_types) + 1) + '}. Back to main menu")
    print("="*60)
    
    try:
        choice = input("\nEnter your choice (1-{}): ".format(len(gpu_types) + 1)).strip()
        
        if choice == str(len(gpu_types) + 1):
            return None
        
        choice_num = int(choice)
        if 1 <= choice_num <= len(gpu_types):
            return gpu_types[choice_num - 1]
        else:
            print("Invalid choice. Please try again.")
            return display_gpu_menu()
            
    except (ValueError, EOFError, KeyboardInterrupt):
        print("\nOperation cancelled.")
        return None


def display_main_menu():
    """Display the main DevBox selection menu."""
    gpu_types = get_available_gpus()
    
    print("\n" + "="*60)
    create_box("🚀 DEVBOX LAUNCHER", "Select your DevBox environment:")
    
    menu_options = [
        "1. Standard DevBox (CPU-only)",
        "2. Document Processor (Pandoc + LaTeX)",
        "3. Gemini CLI (Google AI Assistant)",
        "4. LLM Playroom (Ollama + L40S GPU)",
        "5. llama.cpp Playroom (CPU-only)",
    ]
    
    for option in menu_options:
        print(f"  {option}")
    
    # Add GPU options if available
    if gpu_types:
        menu_options.extend([
            f"6. GPU DevBox - T4 ({GPU_TYPES.get('t4', 'NVIDIA T4')})",
            f"7. GPU DevBox - L4 ({GPU_TYPES.get('l4', 'NVIDIA L4')})", 
            f"8. GPU DevBox - A10G ({GPU_TYPES.get('a10g', 'NVIDIA A10G')})",
        ])
        menu_options.extend([
            "9. RDP Desktop (CPU-only)",
            "10. RDP Desktop - T4 GPU",
            "11. RDP Desktop - L4 GPU", 
            "12. RDP Desktop - A10G GPU",
        ])
    
    print(f"  13. Back to main menu")
    print("="*60)
    
    try:
        choice = input("\nEnter your choice (1-13): ").strip()
        
        if choice == "13":
            return None
            
        choice_num = int(choice)
        if 1 <= choice_num <= len(menu_options):
            return choice_num
        else:
            print("Invalid choice. Please try again.")
            return display_main_menu()
            
    except (ValueError, EOFError, KeyboardInterrupt):
        print("\nOperation cancelled.")
        return None


def launch_selected_environment(choice, extra_packages):
    """Launch the selected DevBox environment."""
    
    # Map menu choices to launch functions
    launch_functions = {
        1: launch_standard_devbox,
        2: launch_doc_processor,
        3: launch_gemini_cli,
        4: launch_llm_playroom,
        5: launch_llamacpp_playroom,
        6: lambda pkg: launch_gpu_devbox("t4", pkg),
        7: lambda pkg: launch_gpu_devbox("l4", pkg),
        8: lambda pkg: launch_gpu_devbox("a10g", pkg),
        9: launch_rdp_desktop,
        10: lambda pkg: launch_rdp_t4(pkg),
        11: lambda pkg: launch_rdp_l4(pkg),
        12: lambda pkg: launch_rdp_a10g(pkg),
    }
    
    if choice in launch_functions:
        print(f"\n🚀 Launching selected DevBox environment...", file=sys.stderr)
        
        if choice in [6, 7, 8]:  # GPU options need GPU selection
            gpu_type = {6: "t4", 7: "l4", 8: "a10g"}[choice]
            selected_gpu = display_gpu_menu()
            if not selected_gpu:
                print("GPU selection cancelled. Returning to main menu.")
                return main()
            launch_func = launch_functions[choice]
            return launch_func(extra_packages)
        else:
            launch_func = launch_functions[choice]
            return launch_func(extra_packages)
    else:
        print("Invalid choice. Returning to main menu.")
        return main()


def display_startup_message():
    """Display startup message with random quote."""
    quote = get_random_quote()
    quote_box = f"""
🎯 Welcome to DevBox Launcher!

{format_quote(quote)}

Ready to launch your personal cloud development environment.
"""
    create_box(quote_box, "🚀 WELCOME TO DEVBOX")


def main():
    """Main entry point for the DevBox application."""
    display_startup_message()
    display_system_info()
    
    while True:
        choice = display_main_menu()
        
        if choice is None:  # User chose to exit
            print("\n👋 Goodbye!")
            break
        
        # Get extra packages if needed
        if choice in [1, 2, 3, 4, 5]:  # Standard environments
            extra_packages = get_extra_packages()
        else:
            extra_packages = None
        
        # Launch selected environment
        result = launch_selected_environment(choice, extra_packages)
        
        if result:
            # Get connection details and display them
            with modal.forward(result.remote, 22) as tunnel:
                ssh_cmd = f"ssh root@{tunnel.url} -p {tunnel.local_port}"
                
                connection_box = f"""
🚀 Your DevBox is ready!
Paste this command into your terminal:

{ssh_cmd}

💡 Tips:
- The connection will auto-shutdown after 5 minutes of inactivity
- Save your work in the /data directory (persistent storage)
- Use 'exit' in the DevBox to shut down cleanly
"""
                create_box(connection_box, "🎯 CONNECTION READY")
                
                print(f"\n📍 DevBox running at: {tunnel.url}")
                print(f"🔌 SSH port: {tunnel.local_port}")
                
                # Wait for the function to complete
                try:
                    result.get()
                except Exception as e:
                    print(f"Error during DevBox execution: {e}", file=sys.stderr)
        else:
            print("Launch failed. Please try again.")


if __name__ == "__main__":
    main()