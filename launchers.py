"""
Launcher functions for DevBox.

This module provides the main launch functions for different DevBox types,
using the refactored modular architecture.

Author: DevBox Launcher
"""

import modal
import sys
from config import get_resource_config
from images import (standard_devbox_image, cuda_devbox_image, doc_processing_image,
                   gemini_cli_image, llm_playroom_image, llamacpp_cpu_image, rdp_devbox_image)
from gpu_utils import get_gpu_config
from shared_runtime import handle_devbox_startup
from ui_utils import create_box, show_spinner
from quotes_loader import get_random_quote, format_quote


def launch_standard_devbox(extra_packages: list[str] | None = None):
    """
    Launch a standard CPU-only DevBox environment.
    
    Args:
        extra_packages: Additional apt packages to install
    """
    print("🚀 Launching Standard DevBox...", file=sys.stderr)
    
    # Get configuration for standard CPU DevBox
    config = get_resource_config("cpu", is_rdp=False)
    config["image"] = standard_devbox_image
    
    @app.function(**config)
    def standard_devbox():
        return handle_devbox_startup(extra_packages, "ssh")
    
    return standard_devbox


def launch_gpu_devbox(gpu_type: str, extra_packages: list[str] | None = None):
    """
    Launch a GPU-powered DevBox environment.
    
    Args:
        gpu_type: Type of GPU ("t4", "l4", "a10g", "l40s")
        extra_packages: Additional apt packages to install
    """
    print(f"🚀 Launching {gpu_type.upper()} GPU DevBox...", file=sys.stderr)
    
    # Get configuration for GPU DevBox
    config = get_resource_config("gpu", gpu_type=gpu_type, is_rdp=False)
    config["image"] = cuda_devbox_image
    config["gpu"] = gpu_type
    
    @app.function(**config)
    def gpu_devbox():
        return handle_devbox_startup(extra_packages, "ssh")
    
    return gpu_devbox


def launch_doc_processor(extra_packages: list[str] | None = None):
    """
    Launch a document processing DevBox with Pandoc and LaTeX support.
    
    Args:
        extra_packages: Additional apt packages to install
    """
    print("📄 Launching Document Processor DevBox...", file=sys.stderr)
    
    # Get configuration for document processor
    config = get_resource_config("cpu", is_rdp=False)
    config["image"] = doc_processing_image
    
    @app.function(**config)
    def doc_processor():
        return handle_devbox_startup(extra_packages, "ssh")
    
    return doc_processor


def launch_gemini_cli(extra_packages: list[str] | None = None):
    """
    Launch a Gemini CLI DevBox with Node.js and Google AI tools.
    
    Args:
        extra_packages: Additional apt packages to install
    """
    print("🤖 Launching Gemini CLI DevBox...", file=sys.stderr)
    
    # Get configuration for Gemini CLI
    config = get_resource_config("cpu", is_rdp=False)
    config["image"] = gemini_cli_image
    
    @app.function(**config)
    def gemini_cli():
        return handle_devbox_startup(extra_packages, "ssh")
    
    return gemini_cli


def launch_llm_playroom(extra_packages: list[str] | None = None):
    """
    Launch an LLM Playroom with Ollama for large language models.
    
    Args:
        extra_packages: Additional apt packages to install
    """
    print("🤖 Launching LLM Playroom (GPU L40S)...", file=sys.stderr)
    
    # Get configuration for LLM playroom with L40S GPU
    config = get_resource_config("gpu", gpu_type="l40s", is_rdp=False)
    config["image"] = llm_playroom_image
    config["gpu"] = "l40s"
    config["memory"] = 4096  # Higher memory for LLM workloads
    
    @app.function(**config)
    def llm_playroom():
        return handle_devbox_startup(extra_packages, "llm")
    
    return llm_playroom


def launch_llamacpp_playroom(extra_packages: list[str] | None = None):
    """
    Launch a llama.cpp CPU-based playroom for large language models.
    
    Args:
        extra_packages: Additional apt packages to install
    """
    print("🔤 Launching llama.cpp CPU Playroom...", file=sys.stderr)
    
    # Get configuration for llama.cpp CPU
    config = get_resource_config("cpu", is_rdp=False)
    config["image"] = llamacpp_cpu_image
    
    @app.function(**config)
    def llamacpp_playroom():
        return handle_devbox_startup(extra_packages, "ssh")
    
    return llamacpp_playroom


def launch_rdp_desktop(gpu_type: str = None, extra_packages: list[str] | None = None):
    """
    Launch an RDP desktop DevBox with XFCE4 environment.
    
    Args:
        gpu_type: Type of GPU for RDP ("t4", "l4", "a10g", None for CPU)
        extra_packages: Additional apt packages to install
    """
    if gpu_type:
        print(f"🖥️ Launching {gpu_type.upper()} GPU RDP Desktop...", file=sys.stderr)
    else:
        print("🖥️ Launching CPU RDP Desktop...", file=sys.stderr)
    
    # Get configuration for RDP desktop
    config_type = "gpu" if gpu_type else "cpu"
    config = get_resource_config(config_type, gpu_type=gpu_type, is_rdp=True)
    config["image"] = rdp_devbox_image
    if gpu_type:
        config["gpu"] = gpu_type
    
    @app.function(**config)
    def rdp_desktop():
        persistence_type = f"rdp_{gpu_type}" if gpu_type else "rdp"
        return handle_devbox_startup(extra_packages, persistence_type)
    
    return rdp_desktop


# GPU launch functions with specific GPU types
def launch_rdp_t4(extra_packages: list[str] | None = None):
    return launch_rdp_desktop("t4", extra_packages)

def launch_rdp_l4(extra_packages: list[str] | None = None):
    return launch_rdp_desktop("l4", extra_packages)

def launch_rdp_a10g(extra_packages: list[str] | None = None):
    return launch_rdp_desktop("a10g", extra_packages)

# Backward compatibility functions (mapping to original names)
def launch_devbox(extra_packages: list[str] | None = None):
    """Backward compatibility wrapper for standard_devbox"""
    return launch_standard_devbox(extra_packages)

def launch_devbox_t4(extra_packages: list[str] | None = None):
    """Backward compatibility wrapper for T4 GPU"""
    return launch_gpu_devbox("t4", extra_packages)

def launch_devbox_l4(extra_packages: list[str] | None = None):
    """Backward compatibility wrapper for L4 GPU"""
    return launch_gpu_devbox("l4", extra_packages)

def launch_devbox_a10g(extra_packages: list[str] | None = None):
    """Backward compatibility wrapper for A10G GPU"""
    return launch_gpu_devbox("a10g", extra_packages)