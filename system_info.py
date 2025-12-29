"""
System information detection for the DevBox launcher.
"""

import platform
import psutil
import os


def get_cpu_info():
    """Get CPU information."""
    try:
        cpu_count = psutil.cpu_count(logical=True)
        cpu_physical = psutil.cpu_count(logical=False)
        cpu_freq = psutil.cpu_freq()

        freq_info = ""
        if cpu_freq:
            freq_info = f"@ {cpu_freq.current:.0f}MHz"

        return f"{cpu_count} cores ({cpu_physical} physical) {freq_info}"
    except:
        return f"{os.cpu_count() or 'Unknown'} cores"


def get_memory_info():
    """Get memory information."""
    try:
        memory = psutil.virtual_memory()
        total_gb = memory.total / (1024**3)
        return f"{total_gb:.1f} GB"
    except:
        return "Unknown"


def get_gpu_info():
    """Try to detect GPU information."""
    try:
        # Try NVIDIA GPU detection
        import subprocess

        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.total",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            lines = result.stdout.strip().split("\n")
            gpu_info = []
            for line in lines[:2]:  # Show up to 2 GPUs
                name, memory = line.split(", ")
                gpu_info.append(f"{name} ({memory}MB)")
            return ", ".join(gpu_info)
    except:
        pass

    # Fallback GPU detection
    try:
        if platform.system() == "Windows":
            # Windows GPU detection (simplified)
            return "Windows GPU detection not implemented"
        elif platform.system() == "Darwin":
            # macOS GPU detection
            return (
                "Apple Silicon GPU"
                if "arm" in platform.machine().lower()
                else "Intel GPU"
            )
        else:
            # Linux fallback
            return "GPU detection requires nvidia-smi"
    except:
        return "Unknown"


def get_system_info():
    """Get comprehensive system information."""
    return {
        "os": f"{platform.system()} {platform.release()}",
        "cpu": get_cpu_info(),
        "memory": get_memory_info(),
        "gpu": get_gpu_info(),
        "python": platform.python_version(),
    }


def display_system_info():
    """Display system information in a formatted way."""
    try:
        from ui_utils import create_box, colorize, Colors

        info = get_system_info()

        system_box = f"""
🖥️  Operating System: {info["os"]}
🧠 CPU: {info["cpu"]}
🧠 Memory: {info["memory"]}
🎮 GPU: {info["gpu"]}
🐍 Python: {info["python"]}
"""

        create_box(system_box, "🖥️  SYSTEM CAPABILITIES", color=Colors.BRIGHT_BLUE)

    except ImportError:
        # Fallback display without fancy formatting
        info = get_system_info()
        print("\n🖥️  SYSTEM CAPABILITIES")
        print("=" * 40)
        print(f"OS: {info['os']}")
        print(f"CPU: {info['cpu']}")
        print(f"Memory: {info['memory']}")
        print(f"GPU: {info['gpu']}")
        print(f"Python: {info['python']}")
        print()


def get_network_info():
    """Get basic network information."""
    try:
        import socket

        hostname = socket.gethostname()
        return f"Host: {hostname}"
    except:
        return "Network: Unknown"


# For testing
if __name__ == "__main__":
    print("System Information Test:")
    display_system_info()
