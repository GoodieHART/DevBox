"""
UI utilities for the DevBox launcher - colors, animations, and formatting.
"""

import sys
import time
import threading
import os


# ANSI color codes
class Colors:
    # Basic colors
    BLACK = "\033[30m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    WHITE = "\033[37m"

    # Bright colors
    BRIGHT_RED = "\033[91m"
    BRIGHT_GREEN = "\033[92m"
    BRIGHT_YELLOW = "\033[93m"
    BRIGHT_BLUE = "\033[94m"
    BRIGHT_MAGENTA = "\033[95m"
    BRIGHT_CYAN = "\033[96m"
    BRIGHT_WHITE = "\033[97m"

    # Styles
    BOLD = "\033[1m"
    UNDERLINE = "\033[4m"
    RESET = "\033[0m"

    # Background colors
    BG_BLUE = "\033[44m"
    BG_GREEN = "\033[42m"
    BG_YELLOW = "\033[43m"
    BG_RED = "\033[41m"


def colorize(text, color):
    """Apply color to text."""
    if not supports_color():
        return text
    return f"{color}{text}{Colors.RESET}"


def supports_color():
    """Check if terminal supports colors."""
    # Check for NO_COLOR environment variable
    if os.environ.get("NO_COLOR"):
        return False

    # Check if stdout is a TTY
    try:
        return sys.stdout.isatty()
    except:
        return False


def print_colored(text, color=Colors.WHITE, bold=False, end="\n"):
    """Print colored text."""
    if bold:
        color = Colors.BOLD + color
    colored_text = colorize(text, color)
    print(colored_text, end=end)


def center_text(text, width=60):
    """Center text within a given width."""
    return text.center(width)


def create_box(content, title="", width=60, color=Colors.CYAN):
    """Create a bordered box around content."""
    if not supports_color():
        print(f"\n{title}")
        print(content)
        return

    lines = content.split("\n")
    max_len = max(len(line) for line in lines) if lines else 0
    box_width = max(max_len + 4, width)

    # Top border
    if title:
        title_len = len(title) + 2
        left_padding = (box_width - title_len) // 2
        right_padding = box_width - title_len - left_padding
        top_border = "╔" + "═" * left_padding + f" {title} " + "═" * right_padding + "╗"
    else:
        top_border = "╔" + "═" * box_width + "╗"

    print(colorize(top_border, color))

    # Content lines
    for line in lines:
        padded_line = line.ljust(max_len)
        print(colorize(f"║ {padded_line} ║", color))

    # Bottom border
    bottom_border = "╚" + "═" * box_width + "╝"
    print(colorize(bottom_border, color))


def show_spinner(message="Loading", duration=2, spinner_chars="⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"):
    """Show a spinning animation for a duration."""
    if not supports_color():
        print(f"{message}...")
        time.sleep(duration)
        print("Done!")
        return

    stop_spinner = threading.Event()

    def spin():
        i = 0
        while not stop_spinner.is_set():
            char = spinner_chars[i % len(spinner_chars)]
            colored_spinner = colorize(f"{char} {message}...", Colors.CYAN)
            print(f"\r{colored_spinner}", end="", flush=True)
            time.sleep(0.1)
            i += 1

    spinner_thread = threading.Thread(target=spin, daemon=True)
    spinner_thread.start()

    time.sleep(duration)

    stop_spinner.set()
    spinner_thread.join(timeout=0.2)

    # Clear the spinner line
    print(f"\r{' ' * (len(message) + 10)}\r", end="", flush=True)


def progress_bar(current, total, width=30, message="Progress"):
    """Display a progress bar."""
    if not supports_color():
        return

    percentage = current / total
    filled_width = int(width * percentage)
    bar = "█" * filled_width + "░" * (width - filled_width)

    percent_text = f"{percentage:.1%}"
    progress_text = f"{message}: [{bar}] {percent_text}"

    print(f"\r{colorize(progress_text, Colors.GREEN)}", end="", flush=True)

    if current >= total:
        print()  # New line when complete


def typewriter_effect(text, delay=0.05, color=Colors.WHITE):
    """Print text with a typewriter effect."""
    if not supports_color():
        print(text)
        return

    for char in text:
        print(colorize(char, color), end="", flush=True)
        time.sleep(delay)
    print()


def fade_in_text(text, color=Colors.WHITE):
    """Simple fade-in effect (just delayed print for now)."""
    time.sleep(0.5)
    print_colored(text, color)


def clear_screen():
    """Clear the terminal screen."""
    os.system("cls" if os.name == "nt" else "clear")


def print_separator(char="─", length=50, color=Colors.BLUE):
    """Print a separator line."""
    separator = char * length
    print_colored(separator, color)
