"""
ASCII art and branding for the DevBox launcher.
"""

# Import handling for both standalone and module usage
import sys
import os

# Add current directory to path for imports
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

try:
    from ui_utils import colorize, Colors, center_text, create_box
    from quotes import get_random_quote
except ImportError:
    # Define minimal fallbacks if imports fail
    def colorize(text, color):
        return text

    class Colors:
        BRIGHT_CYAN = BRIGHT_GREEN = BRIGHT_YELLOW = BRIGHT_MAGENTA = BRIGHT_BLUE = (
            BRIGHT_RED
        ) = WHITE = BOLD = ""

    def center_text(text, width=60):
        return text

    def create_box(content, title="", width=60, color=""):
        print(content)

    def get_random_quote(category):
        return {"text": "Code is poetry in motion.", "author": "Anonymous"}


def show_logo():
    """Display the DevBox launcher logo."""
    logo = """
╔══════════════════════════════════════════════════════════╗
║                                                          ║
║            🚀  MODAL DEVBOX LAUNCHER  🚀                ║
║                                                          ║
║              "Code in the Cloud, Anytime!"               ║
║                                                          ║
╚══════════════════════════════════════════════════════════╝
"""

    print(colorize(logo, Colors.BRIGHT_CYAN + Colors.BOLD))


def show_welcome_animation():
    """Show a welcome animation sequence."""
    from .ui_utils import typewriter_effect, fade_in_text, print_separator

    typewriter_effect("Initializing DevBox Launcher...", color=Colors.BRIGHT_BLUE)
    typewriter_effect("Loading cloud configurations...", color=Colors.BRIGHT_GREEN)
    typewriter_effect("Ready for liftoff! 🚀", color=Colors.BRIGHT_YELLOW)
    print()


def show_success_celebration():
    """Display a celebration for successful launch."""
    celebration = """
╔══════════════════════════════════════════════╗
║                                              ║
║              🎉 SUCCESS! 🎉                   ║
║                                              ║
║         Your DevBox is ready to code!        ║
║                                              ║
╚══════════════════════════════════════════════╝
"""
    print(colorize(celebration, Colors.BRIGHT_GREEN + Colors.BOLD))


def show_ssh_reveal_animation(ssh_command):
    """Dramatic reveal of the SSH command."""
    from .ui_utils import typewriter_effect, create_box

    typewriter_effect(
        "🔐 Establishing secure connection...", color=Colors.BRIGHT_MAGENTA
    )
    typewriter_effect("🌐 Routing through Modal's network...", color=Colors.BRIGHT_BLUE)
    typewriter_effect("✨ Connection ready!", color=Colors.BRIGHT_GREEN)
    print()

    # Create a fancy box for the SSH command
    ssh_box = f"""
🎯 Your DevBox is live and ready!

💻 Connect using this command:

{colorize(ssh_command, Colors.BRIGHT_WHITE + Colors.BOLD)}

⚠️  Remember: Work is saved in /data/
⏰ Container auto-shuts down after 5 minutes of inactivity
"""

    create_box(ssh_box, "🚀 LAUNCH COMPLETE", color=Colors.BRIGHT_GREEN)


def show_loading_stages():
    """Show different loading stages during container launch."""
    stages = [
        ("🔧", "Initializing container environment", Colors.BRIGHT_BLUE),
        ("📦", "Installing requested packages", Colors.BRIGHT_YELLOW),
        ("🔑", "Injecting SSH keys", Colors.BRIGHT_MAGENTA),
        ("🌐", "Setting up network tunnels", Colors.BRIGHT_CYAN),
        ("⚡", "Starting services", Colors.BRIGHT_GREEN),
    ]

    from .ui_utils import show_spinner

    for icon, message, color in stages:
        show_spinner(f"{icon} {message}", duration=1.5)


def show_gpu_powered_message(gpu_type):
    """Show GPU activation message."""
    gpu_message = f"""
╔══════════════════════════════════════════════╗
║                                              ║
║              ⚡ GPU POWERED ⚡                 ║
║                                              ║
║         Activating {gpu_type} acceleration      ║
║                                              ║
╚══════════════════════════════════════════════╝
"""
    print(colorize(gpu_message, Colors.BRIGHT_YELLOW + Colors.BOLD))


def show_document_processing_ready():
    """Show document processing box ready message."""
    doc_message = """
╔══════════════════════════════════════════════╗
║                                              ║
║           📄 DOCUMENT PROCESSING 📄         ║
║                                              ║
║     Pandoc + Full TeX Live Distribution      ║
║                                              ║
║         Ready for your documents! 📝         ║
║                                              ║
╚══════════════════════════════════════════════╝
"""
    print(colorize(doc_message, Colors.BRIGHT_BLUE + Colors.BOLD))


def show_gemini_ready():
    """Show Gemini CLI ready message."""
    gemini_message = """
╔══════════════════════════════════════════════╗
║                                              ║
║            🤖 GEMINI CLI READY 🤖            ║
║                                              ║
║       AI-powered development assistant       ║
║                                              ║
║         Let's build something amazing! 🚀     ║
║                                              ║
╚══════════════════════════════════════════════╝
"""
    print(colorize(gemini_message, Colors.BRIGHT_MAGENTA + Colors.BOLD))


def show_error_art(error_type="unknown"):
    """Show error art based on error type."""
    error_art = {
        "connection": """
╔══════════════════════════════════════════════╗
║                                              ║
║              🚫 CONNECTION ERROR 🚫          ║
║                                              ║
║        Unable to connect to Modal cloud      ║
║                                              ║
║        Check your internet and try again     ║
║                                              ║
╚══════════════════════════════════════════════╝
""",
        "auth": """
╔══════════════════════════════════════════════╗
║                                              ║
║            🔐 AUTHENTICATION ERROR 🔐        ║
║                                              ║
║        Please run 'modal setup' to login     ║
║                                              ║
║        Or check your API credentials         ║
║                                              ║
╚══════════════════════════════════════════════╝
""",
        "unknown": """
╔══════════════════════════════════════════════╗
║                                              ║
║              💥 UNKNOWN ERROR 💥             ║
║                                              ║
║        Something unexpected happened         ║
║                                              ║
║        Check the logs and try again          ║
║                                              ║
╚══════════════════════════════════════════════╝
""",
    }

    art = error_art.get(error_type, error_art["unknown"])
    print(colorize(art, Colors.BRIGHT_RED + Colors.BOLD))


def show_startup_quote():
    """Show a random startup quote."""
    from .quotes import get_random_quote
    from .ui_utils import create_box

    quote = get_random_quote("startup")
    if quote:
        quote_box = f'"{quote["text"]}"\n\n— {quote["author"]}'
        create_box(quote_box, "💭 Programming Wisdom", color=Colors.BRIGHT_YELLOW)
