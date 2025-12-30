import modal
import time
import random

app = modal.App(
    name="windows-sandbox-launcher",
)


# Simplified UI utilities - clean and reliable
def create_box(content, title="", width=60):
    """Create a bordered box around content."""
    lines = content.split("\n")
    max_len = max(len(line) for line in lines) if lines else 0
    box_width = max(max_len + 4, width)

    if title:
        title_len = len(title) + 2
        left_padding = (box_width - title_len) // 2
        right_padding = box_width - title_len - left_padding
        top_border = "╔" + "═" * left_padding + f" {title} " + "═" * right_padding + "╗"
    else:
        top_border = "╔" + "═" * box_width + "╗"

    print(top_border)

    for line in lines:
        padded_line = line.ljust(max_len)
        print(f"║ {padded_line} ║")

    bottom_border = "╚" + "═" * box_width + "╝"
    print(bottom_border)


def show_spinner(message="Loading", duration=2):
    """Simple spinner with visual feedback."""
    spinner_chars = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
    start_time = time.time()
    i = 0

    while time.time() - start_time < duration:
        char = spinner_chars[i % len(spinner_chars)]
        spinner_text = f"{char} {message}..."
        print(f"\r{spinner_text}", end="", flush=True)
        time.sleep(0.1)
        i += 1

    # Clear the spinner line
    clear_length = len(message) + 10
    print(f"\r{' ' * clear_length}\r", end="", flush=True)


# Programming quotes embedded
PROGRAMMING_QUOTES = [
    {
        "text": "First, solve the problem. Then, write the code.",
        "author": "John Johnson",
    },
    {
        "text": "The best error message is the one that never shows up.",
        "author": "Thomas Fuchs",
    },
    {
        "text": "Programs must be written for people to read, and only incidentally for machines to execute.",
        "author": "Harold Abelson",
    },
    {
        "text": "The only way to learn a new programming language is by writing programs in it.",
        "author": "Dennis Ritchie",
    },
    {
        "text": "Code is like humor. When you have to explain it, it's bad.",
        "author": "Cory House",
    },
    {"text": "Make it work, make it right, make it fast.", "author": "Kent Beck"},
    {
        "text": "The most disastrous thing that you can ever learn is your first programming language.",
        "author": "Alan Kay",
    },
]


def get_random_quote():
    return random.choice(PROGRAMMING_QUOTES)


# System info functions
def get_system_info():
    try:
        import os

        cpu_count = os.cpu_count() or 1
        return f"CPU: {cpu_count} cores"
    except:
        return "CPU: Unknown"


def display_system_info():
    info = get_system_info()
    system_box = f"""
🖥️  Local System:
{info}
🐍 Python: 3.12
💻 Platform: Windows
"""
    create_box(system_box, "🖥️  SYSTEM CAPABILITIES")


def create_windows_sandbox(
    windows_version: str = "11",
    ram_size: str = "8G",
    cpu_cores: str = "4",
    disk_size: str = "64G",
):
    """
    Create a Windows DevBox using Modal Sandbox.
    This runs a Windows container (not a full VM) but provides RDP access.
    """
    print("🪟 Creating Windows DevBox with Modal Sandbox...")
    print(f"Version: Windows {windows_version}")
    print(f"RAM: {ram_size}, CPU: {cpu_cores} cores, Disk: {disk_size}")

    # Create a custom image with environment variables for dockurr/windows
    env_vars = {
        "VERSION": windows_version,
        "RAM_SIZE": ram_size,
        "CPU_CORES": cpu_cores,
        "DISK_SIZE": disk_size,
    }
    windows_image = modal.Image.from_registry("dockurr/windows:latest").env(env_vars)

    # Create the sandbox with the customized Windows image
    sandbox = modal.Sandbox.create(
        image=windows_image,
        # Mount a volume for persistent storage
        volumes={
            "/storage": modal.Volume.from_name(
                "windows-sandbox-volume", create_if_missing=True
            )
        },
        # Allocate resources
        cpu=float(cpu_cores),
        memory=int(ram_size.rstrip("G")) * 1024,  # Convert GB to MB
        timeout=3600,  # 1 hour timeout
        # Enable RDP and web viewer ports
        unencrypted_ports=[3389, 8006],  # RDP and web viewer
    )

    print("⏳ Waiting for Windows container to start...")
    time.sleep(10)  # Give it time to boot

    return sandbox


def show_connection_info(sandbox):
    """Display connection information for the Windows sandbox."""
    print("\n🪟 Your Windows DevBox is starting up!")
    print("This runs a Windows container (not a full VM) with RDP access.")
    print()

    # Get tunnel URLs
    try:
        # Get all tunnels
        tunnels = sandbox.tunnels(timeout=30)

        # RDP tunnel on port 3389 (container port)
        if 3389 in tunnels:
            rdp_tunnel = tunnels[3389]
            print("🔗 RDP Connection (via Modal tunnel):")
            print(f"   External Host: {rdp_tunnel.host}")
            print(f"   External Port: {rdp_tunnel.port}")
            print("   Container Port: 3389 (RDP)")
            print("   Username: Docker")
            print("   Password: admin")
            print()
            print(
                "   💡 Modal assigns random external ports and tunnels to container ports"
            )
            print()

        # Web viewer tunnel on port 8006 (container port)
        if 8006 in tunnels:
            web_tunnel = tunnels[8006]
            print("🌐 Web Viewer (via Modal tunnel):")
            print(f"   External URL: http://{web_tunnel.host}:{web_tunnel.port}")
            print("   Container Port: 8006 (web)")
            print()

        print("📋 Instructions:")
        print("1. Use Microsoft Remote Desktop or any RDP client")
        print("2. Connect to the EXTERNAL host and port shown above")
        print("3. Modal automatically forwards this to the container's RDP port (3389)")
        print("4. Login with Docker/admin credentials")
        print("5. Alternatively, use the web viewer external URL")
        print()

        print("⚠️  Note: This is a Windows CONTAINER, not a full VM")
        print("   KVM acceleration disabled (runs ~10x slower)")
        print("   But you get RDP access to a Windows environment!")
        print()
        print("💡 Pro tip: The container may take 5-10 minutes to fully boot")
        print("   Be patient - Windows startup is slower without hardware acceleration")

    except Exception as e:
        print(f"❌ Error setting up tunnels: {e}")
        print("The sandbox may still be starting up...")
        print("Try waiting a few minutes and checking the Modal dashboard.")


def detect_network_interface():
    """Detect the actual network interface name available in Modal sandbox."""
    print("🔍 Detecting network interface for Modal sandbox...")

    try:
        # Create a test sandbox to inspect network interfaces
        test_sandbox = modal.Sandbox.create(
            image=modal.Image.debian_slim(),
            cpu=0.1,
            memory=128,
            timeout=60,
        )

        print("   📡 Created test sandbox, running interface detection...")

        # Run ip addr show to get detailed interface information
        process = test_sandbox.exec("ip", "addr", "show")
        output = process.stdout.read()

        print("   📋 Network interfaces detected:")
        print("   " + "=" * 50)

        # Parse and display all interfaces
        lines = output.split("\n")
        interfaces = []

        for line in lines:
            print(f"   {line}")  # Show raw output for debugging

            # Parse interface names from lines like "2: eth0: <BROADCAST,MULTICAST,UP,LOWER_UP>"
            if ":" in line and not line.startswith(" "):
                parts = line.split(":")
                if len(parts) >= 2:
                    iface_num = parts[0].strip()
                    iface_info = parts[1].strip()
                    iface_name = iface_info.split()[0] if iface_info else ""

                    if (
                        iface_name
                        and iface_name != "lo"
                        and not iface_name.startswith("docker")
                    ):
                        interfaces.append(iface_name)
                        print(f"   ✅ Found interface: {iface_name}")

        test_sandbox.terminate()

        print("   " + "=" * 50)

        # Return the first usable interface
        if interfaces:
            chosen = interfaces[0]  # Use the first non-loopback interface
            print(f"   🎯 Selected interface: {chosen}")
            return chosen
        else:
            print("   ⚠️  No usable interfaces found")
            return None

    except Exception as e:
        print(f"   ❌ Interface detection failed: {e}")
        return None


# Modal function to create the Windows sandbox
@app.function()
def create_windows_sandbox_modal(
    windows_version: str = "11",
    ram_size: str = "8G",
    cpu_cores: str = "4",
    disk_size: str = "64G",
):
    """Modal function to create Windows sandbox - runs in Modal environment."""
    print("🪟 Creating Windows DevBox with Modal Sandbox...")
    print(f"Version: Windows {windows_version}")
    print(f"RAM: {ram_size}, CPU: {cpu_cores} cores, Disk: {disk_size}")

    # Detect the correct network interface for this Modal environment
    network_interface = detect_network_interface()

    if network_interface:
        print(f"🌐 Using detected network interface: {network_interface}")
        vm_net_dev = network_interface
    else:
        print("🌐 No interface detected, trying common names...")
        # Try common interface names that might work
        common_names = ["eth0", "ens4", "enp0s3", "eno1", "enp1s0", "eth1"]
        vm_net_dev = common_names[0]  # Start with eth0
        print(f"🌐 Using fallback interface: {vm_net_dev}")

    # Create a custom image with environment variables for dockurr/windows
    env_vars = {
        "VERSION": windows_version,
        "RAM_SIZE": ram_size,
        "CPU_CORES": cpu_cores,
        "DISK_SIZE": disk_size,
        "KVM": "N",  # Disable KVM acceleration (runs slower but works without hardware virtualization)
        "VM_NET_DEV": vm_net_dev,  # Network interface for VM networking
    }
    windows_image = modal.Image.from_registry("dockurr/windows:latest").env(env_vars)

    # Create the sandbox with the customized Windows image
    sandbox = modal.Sandbox.create(
        image=windows_image,
        # Mount a volume for persistent storage
        volumes={
            "/storage": modal.Volume.from_name(
                "windows-sandbox-volume", create_if_missing=True
            )
        },
        # Allocate resources
        cpu=float(cpu_cores),
        memory=int(ram_size.rstrip("G")) * 1024,  # Convert GB to MB
        timeout=3600,  # 1 hour timeout
        # Enable RDP and web viewer ports
        unencrypted_ports=[3389, 8006],  # RDP and web viewer
    )

    print("⏳ Waiting for Windows container to start...")
    time.sleep(10)  # Give it time to boot

    return sandbox


def get_user_config():
    """Get user configuration interactively."""
    # Show welcome
    print()
    logo = """
╔══════════════════════════════════════════════════════════╗
║                                                          ║
║            🪟  WINDOWS SANDBOX DEVBOX  🪟               ║
║                                                          ║
║       "Windows Containers in the Cloud!"                 ║
║                                                          ║
╚══════════════════════════════════════════════════════════╝
"""
    print(logo)

    # Show quote
    quote = get_random_quote()
    quote_box = f'"{quote["text"]}"\n\n— {quote["author"]}'
    create_box(quote_box, "💭 Programming Wisdom")

    # Show system info
    display_system_info()

    # Configuration menu
    config_menu = """
🪟 Configure your Windows Sandbox:

Windows Versions:
• 11 - Windows 11 Pro (default)
• 10 - Windows 10 Pro
• 11l - Windows 11 LTSC
• 10l - Windows 10 LTSC

Resource Options:
• RAM: 4G, 8G, 16G (default: 8G)
• CPU: 2, 4, 8 cores (default: 4)
• Disk: 32G, 64G, 128G, 256G (default: 64G)

⚠️  This creates a Windows CONTAINER (not full VM)
"""
    create_box(config_menu, "⚙️  CONFIGURATION")

    # Get version
    version_box = """
Choose Windows version:
1. 🪟 Windows 11 Pro (recommended)
2. 🪟 Windows 10 Pro
3. 🪟 Windows 11 LTSC (lightweight)
4. 🪟 Windows 10 LTSC (lightweight)
"""
    create_box(version_box, "🎯 WINDOWS VERSION")

    try:
        version_choice = input("Enter version (1-4): ").strip()
    except EOFError:
        print("\nNo input received. Exiting.")
        return None

    version_map = {
        "1": "11",
        "2": "10",
        "3": "11l",
        "4": "10l",
    }

    windows_version = version_map.get(version_choice, "11")

    # Get resources
    try:
        ram_input = input("RAM size (default 8G): ").strip() or "8G"
        cpu_input = input("CPU cores (default 4): ").strip() or "4"
        disk_input = input("Disk size (default 64G): ").strip() or "64G"
    except EOFError:
        ram_input = "8G"
        cpu_input = "4"
        disk_input = "64G"

    # Validate
    valid_ram = ["4G", "8G", "16G"]
    valid_cpu = ["2", "4", "8"]
    valid_disk = ["32G", "64G", "128G", "256G"]

    ram_size = ram_input if ram_input in valid_ram else "8G"
    cpu_cores = cpu_input if cpu_input in valid_cpu else "4"
    disk_size = disk_input if disk_input in valid_disk else "64G"

    # Confirmation
    launch_info = f"""
Launching Windows Sandbox with:
• Version: Windows {windows_version}
• RAM: {ram_size}
• CPU: {cpu_cores} cores
• Disk: {disk_size}

⚠️  This creates a Windows CONTAINER (not full VM)
🐌 Performance: ~10x slower without KVM acceleration
🕐 Timeout: 1 hour
🔄 Persistent storage: Yes
"""
    create_box(launch_info, "🚀 LAUNCH CONFIRMATION")

    try:
        confirm = input("Ready to launch? (y/n): ").lower().strip()
    except EOFError:
        confirm = "n"

    if confirm == "y":
        return {
            "version": windows_version,
            "ram": ram_size,
            "cpu": cpu_cores,
            "disk": disk_size,
        }
    else:
        return None


def manage_sandbox_lifecycle(sandbox):
    """Manage the sandbox lifecycle - keep it alive and handle termination."""
    print("🔄 Sandbox is running. Press Ctrl+C to stop.")
    try:
        while True:
            time.sleep(60)  # Keep alive for 1 hour max
    except KeyboardInterrupt:
        print("\n🛑 Stopping Windows Sandbox...")
        sandbox.terminate()
        print("✅ Sandbox terminated.")


# Modal local entrypoint for running the Windows sandbox
@app.local_entrypoint()
def run_windows_sandbox():
    """Modal local entrypoint to run the Windows sandbox launcher."""
    # Run the interactive UI locally, then call the modal function
    config = get_user_config()
    if config:
        print("\n🚀 Launching Windows Sandbox...")
        try:
            # Call the modal function directly (app is already running in local entrypoint)
            sandbox = create_windows_sandbox_modal.remote(
                config["version"], config["ram"], config["cpu"], config["disk"]
            )
            show_connection_info(sandbox)
            manage_sandbox_lifecycle(sandbox)
        except Exception as e:
            print(f"❌ Error: {e}")
    else:
        print("Launch cancelled.")


# Keep a simple main for local testing
if __name__ == "__main__":
    print("Please use: modal run windows_sandbox.py::run_windows_sandbox")
