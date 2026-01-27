"""
UI Utilities Module for DevBox Launcher

This module provides reusable UI components for the DevBox application,
including box creation, spinner animations, and visual feedback utilities.

Author: DevBox Launcher
"""

import time
import sys
from typing import Optional


def create_box(content: str, title: str = "", width: int = 60) -> None:
    """
    Create a bordered box around content with optional title.
    
    Args:
        content: The text content to display inside the box
        title: Optional title to display in the top border
        width: Minimum width of the box (default: 60)
    """
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


def show_spinner(message: str = "Loading", duration: float = 2) -> None:
    """
    Display a simple spinner with visual feedback for the specified duration.
    
    Args:
        message: Message to display alongside the spinner
        duration: How long to show the spinner in seconds (default: 2)
    """
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


def create_info_box(message: str, title: str = "ℹ️ INFO") -> None:
    """
    Create a standardized info box for displaying informational messages.
    
    Args:
        message: The informational message to display
        title: Title for the info box (default: "ℹ️ INFO")
    """
    create_box(message, title)


def create_success_box(message: str, title: str = "✅ SUCCESS") -> None:
    """
    Create a standardized success box for displaying success messages.
    
    Args:
        message: The success message to display
        title: Title for the success box (default: "✅ SUCCESS")
    """
    create_box(message, title)


def create_error_box(message: str, title: str = "❌ ERROR") -> None:
    """
    Create a standardized error box for displaying error messages.
    
    Args:
        message: The error message to display
        title: Title for the error box (default: "❌ ERROR")
    """
    create_box(message, title)


def create_warning_box(message: str, title: str = "⚠️ WARNING") -> None:
    """
    Create a standardized warning box for displaying warning messages.
    
    Args:
        message: The warning message to display
        title: Title for the warning box (default: "⚠️ WARNING")
    """
    create_box(message, title)


def print_separator(char: str = "=", length: int = 50) -> None:
    """
    Print a separator line for visual spacing.
    
    Args:
        char: Character to use for the separator (default: "=")
        length: Length of the separator line (default: 50)
    """
    print(char * length)


def clear_line() -> None:
    """
    Clear the current terminal line and move cursor to beginning.
    """
    print("\r" + " " * 80 + "\r", end="", flush=True)