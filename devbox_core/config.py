"""
Configuration constants for DevBox Launcher.

This module centralizes all configuration constants, resource allocations,
and global settings used across DevBox

Author: GoodieHART
"""

from collections.abc import Iterable
from typing import Any

# Container will shut down if no one is connected via SSH for this many seconds.
# All Time Values are in seconds
IDLE_TIMEOUT_SECONDS = 300  # 5 minutes

# Version constants
LLAMACPP_VERSION = "b9058" # this will be made dynamic in future
STARSHIP_VERSION = "v1.22.1"
NODE_MAJOR_VERSION = "24"
REA_AGENTS_VERSION = "6.5.0"
JADX_HEADLESS_MCP_VERSION = "0.7.1"
GHIDRA_VERSION = "12.1.4"
GHIDRA_BUILD = "20260921"
TEMURIN_JDK_VERSION = "21.0.12.1+1"
JADX_VERSION = "1.5.6"
APKTOOL_VERSION = "3.0.3"
OPENCODE_VERSION = "1.19.0"

# Resource configurations for different DevBox types

# CPU-only DevBox resource arguments
CPU_DEVBOX_ARGS = {
    "secrets": None,
    "volumes": None,
    "cpu": 0.5,
    "memory": 1024,
    "timeout": 3600,
}

# Standard GPU DevBox resource arguments
GPU_DEVBOX_ARGS = {
    "secrets": None,
    "volumes": None,
    "cpu": 1.0,
    "memory": 2048,
    "timeout": 18000,
}

# RDP-specific resource arguments (higher resources for desktop environment)
CPU_DEVBOX_ARGS_RDP = {
    "secrets": None,
    "volumes": None,
    "cpu": 1.0,
    "memory": 2048,
    "timeout": 10800,
}

# RDP GPU resource arguments (highest resources)
GPU_DEVBOX_ARGS_RDP = {
    "secrets": None,
    "volumes": None,
    "cpu": 1.5,
    "memory": 4096,
    "timeout": 18000,
}

# llama.cpp Research Center resource arguments
LLAMACPP_DEVBOX_ARGS = {
    "secrets": None,
    "volumes": None,
    "cpu": 2.0,
    "memory": 8192,  # 8GB for 7B models
    "timeout": 14400,  # 4 hours max runtime
}

# GPU llama.cpp Research Center resource arguments
LLAMACPP_GPU_DEVBOX_ARGS = {
    "secrets": None,
    "volumes": None,
    "cpu": 2.0,
    "memory": 16384,  # 16GB for Gemma4-26B-A4B
    "timeout": 14400,  # 4 hours max runtime
    "gpu": "t4",
}

# llama.cpp idle timeout (separate from container timeout)
LLAMACPP_IDLE_TIMEOUT = 3600  # 1 hour idle

# OpenCode instance settings (dedicated OpenCode server box)
OPENCODE_PORT = 4096  # Default `opencode web` port
OPENCODE_HOSTNAME = "0.0.0.0"  # Bind so Modal tunnel can reach it
OPENCODE_IDLE_TIMEOUT_SECONDS = 1800  # 30 minutes idle (longer than SSH boxes, shorter than llamacpp)
OPENCODE_WORKDIR = "/data"  # Volume root — general OpenCode working dir
# Dedicated persistent dir for the OpenCode box (created if missing). Seeded as a
# git repo so OpenCode treats it as a project instead of its "global" fallback.
OPENCODE_SESSIONS_DIR = "/data/oc-sessions"
# Dedicated persistent dir for user-supplied files to be analyzed by REA MCP
# (and any other tool). Lives on the volume, so uploads survive relaunches.
OPENCODE_UPLOADS_DIR = "/data/uploads"

# OpenCode DevBox resource arguments (CPU-only, headroom for web server + TUI attach)
OPENCODE_DEVBOX_ARGS = {
    "secrets": None,
    "volumes": None,
    "cpu": 2.0,
    "memory": 8192,  # 8 GB headroom for Ghidra headless decompilation
    "timeout": 10800,  # 3 hours max runtime
}

# Assisted coding box: opencode TUI + rea mcp measured ~1.6GB RSS + 326MB child
ASSISTED_DEVBOX_ARGS = {
    "secrets": None,
    "volumes": None,
    "cpu": 1.0,
    "memory": 4096,
    "timeout": 10800,  # 3 hours max runtime
}

# Package groups for reusable configurations
CORE_DEV_PACKAGES = [
    "openssh-server",
    "git",
    "nano",
    "neovim",
    "curl",
    "wget",
    "unzip",
    "procps",
]

EXTENDED_DEV_PACKAGES = [
    "clang",
    "cmake",
    "htop",
    "zlib1g-dev",
    "build-essential",
    "pkg-config",
    "python3-dev",
]

# Download tool packages for all DevBox images
DOWNLOAD_APT_PACKAGES = [
    "megatools",
    "p7zip-full",
]

DOWNLOAD_PIP_PACKAGES = [
    "gdown",
    "tgdl",
    "terabox-downloader",
]

# ---------------------------------------------------------------------------
# Prohibited package denylist
# ---------------------------------------------------------------------------
# Modal's Terms of Service (https://modal.com/legal/terms, §1.5) make
# "cryptocurrency mining or related blockchain related activities" a
# Prohibited Purpose, and Modal's runtime detects offending programs by
# syscall analysis and bans the workspace (https://modal.com/blog/catching-cryptominers).
# Refused at image-build time and before every runtime `apt-get install`.
#
# Scope: a denylist, not a sandbox — it stops `apt-get install xmrig` but
# cannot stop a binary fetched from a URL at runtime.

# Cryptocurrency mining / GPU-abuse tooling.
MINING_PACKAGES_DENYLIST = frozenset({
    # Monero / CryptoNight family
    "xmrig",
    "xmrig-proxy",
    "xmr-stak",
    "xmr-stak-amd",
    "xmr-stak-nvidia",
    "kdevtmpfsi",
    "tprminer",
    "tprminers",
    "cpuminer",
    "cpuminer-multi",
    "cpuminer-opt",
    "ccminer",
    "ckbminer",
    "nheqminer",
    "nanominer",
    "verusminer",
    "minerd",
    # OpenCL / CUDA GPU miners
    "cgminer",
    "bfgminer",
    "bfminer",
    "ethminer",
    "eth-miner",
    "phoenixminer",
    "lolminer",
    "teamredminer",
    "srdeminer",
    "wildrig",
    "nbminer",
    "gminer",
    "trex",
    "trexminer",
    "kryptex",
    "spaceminer",
    "confluxminer",
    "bitcoin-miner",
    "ethereum-miner",
})

# Credential-cracking tooling. DevBox ships analysis tools (Ghidra, binwalk,
# tshark, volatility3) but no password crackers.
CREDENTIAL_CRACKING_PACKAGES_DENYLIST = frozenset({
    "hashcat",
    "hashcat-utils",
    "hashcat-opencl",
    "hashcat-data",
    "john",
    "john-data",
})

# Everything refused by the two denylists above.
PROHIBITED_PACKAGES_DENYLIST = (
    MINING_PACKAGES_DENYLIST | CREDENTIAL_CRACKING_PACKAGES_DENYLIST
)


def _package_name_candidates(spec: str) -> list[str]:
    """
    Every bare name an apt spec could refer to.

    apt accepts several forms for the same package, and a denied package must
    not slip through by wearing a different hat:
        "hashcat"            -> "hashcat"
        "hashcat=6.2.6-1"    -> "hashcat"   (version pin)
        "hashcat/stable"     -> "hashcat"   (release qualifier)
        "hashcat:amd64"      -> "hashcat"   (architecture qualifier)
        "./xmrig.deb"        -> "xmrig"     (local package file)
    """
    raw = spec.strip().lower()
    if not raw:
        return []

    candidates: list[str] = []
    for candidate in (raw, raw.rsplit("/", 1)[-1]):
        for separator in ("=", ":", "/"):
            candidate = candidate.split(separator, 1)[0]
        candidate = candidate.strip()
        if candidate.endswith(".deb"):
            candidate = candidate[: -len(".deb")]
        if candidate and candidate not in candidates:
            candidates.append(candidate)
    return candidates


def _matches_denylist(name: str, denylist: frozenset[str]) -> bool:
    """True if `name` is denied, either outright or as a variant of a denied name."""
    if name in denylist:
        return True
    # "xmrig-custom" is the same tool as "xmrig"; "john-data" is the same tool
    # as "john". The boundary check keeps unrelated names ("johnny") allowed.
    for entry in denylist:
        if name.startswith(entry) and not name[len(entry)].isalnum():
            return True
    return False


def find_prohibited_packages(packages: Iterable[str] | None) -> list[str]:
    """
    Return the entries of `packages` that are on the denylist, in input order.

    Args:
        packages: iterable of apt package specs

    Returns:
        list: the offending specs, as they were given
    """
    denied: list[str] = []
    for spec in packages or []:
        for candidate in _package_name_candidates(spec):
            if _matches_denylist(candidate, PROHIBITED_PACKAGES_DENYLIST):
                denied.append(spec)
                break
    return denied


def validate_prohibited_packages(packages: Iterable[str] | None) -> None:
    """
    Raise ValueError if any of `packages` is on the denylist.

    Called when every image is built and again before any runtime
    `apt-get install`, so a prohibited package is refused before Modal's
    runtime ever sees it.
    """
    denied = find_prohibited_packages(packages)
    if not denied:
        return
    raise ValueError(
        "Refusing to install prohibited package(s): "
        + ", ".join(sorted(set(denied)))
        + ". Cryptocurrency mining and credential-cracking tools are prohibited "
        + "by Modal's Terms of Service (https://modal.com/legal/terms) and are "
        + "blocked by DevBox. See the 'Warnings & Open Letter' section of the "
        + "README for the full policy."
    )


def get_resource_config(config_type="cpu", is_rdp=False, secrets=None, volume=None) -> dict[str, Any]:
  """
    Get complete resource configuration for DevBox type.
    
    Args:
        config_type: "cpu" or "gpu"
        is_rdp: Whether this is for RDP environment
        
    Returns:
        dict: Complete configuration with Modal objects
    """
  if config_type == "cpu":
    base_config = CPU_DEVBOX_ARGS_RDP if is_rdp else CPU_DEVBOX_ARGS
  elif config_type == "gpu":
    base_config = GPU_DEVBOX_ARGS_RDP if is_rdp else GPU_DEVBOX_ARGS
  else:
    raise ValueError(f"Unknown config_type: {config_type}")

  config: dict[str, Any] = dict(base_config)
  config["secrets"] = secrets
  config["volumes"] = {"/data": volume}
  return config


def build_devbox_args(secrets, volume) -> dict[str, dict[str, Any]]:
  """
    Build all eight Modal function arg dicts from live handles.

    Args:
        secrets: list of Modal Secret handles (all boxes share them).
        volume: Modal Volume handle mounted at /data.

    Returns:
        dict: all seven arg dicts keyed by their devbox.py names.
  """
  cpu_devbox_args = get_resource_config("cpu", secrets=secrets, volume=volume)

  cpu_devbox_args_rdp = get_resource_config("cpu", secrets=secrets, volume=volume, is_rdp=True)

  gpu_devbox_args = get_resource_config("gpu", secrets=secrets, volume=volume, is_rdp=True)

  gpu_devbox_args_rdp = get_resource_config("gpu", secrets=secrets, volume=volume, is_rdp=True)

  opencode_devbox_args: dict[str, Any] = dict(OPENCODE_DEVBOX_ARGS)
  opencode_devbox_args["secrets"] = secrets
  opencode_devbox_args["volumes"] = {"/data": volume}

  assisted_devbox_args: dict[str, Any] = dict(ASSISTED_DEVBOX_ARGS)
  assisted_devbox_args["secrets"] = secrets
  assisted_devbox_args["volumes"] = {"/data": volume}

  llamacpp_devbox_args: dict[str, Any] = dict(LLAMACPP_DEVBOX_ARGS)
  llamacpp_devbox_args["secrets"] = secrets
  llamacpp_devbox_args["volumes"] = {"/data": volume}

  llamacpp_gpu_devbox_args: dict[str, Any] = dict(LLAMACPP_GPU_DEVBOX_ARGS)
  llamacpp_gpu_devbox_args["secrets"] = secrets
  llamacpp_gpu_devbox_args["volumes"] = {"/data": volume}

  return {
    "cpu_devbox_args": cpu_devbox_args,
    "cpu_devbox_args_rdp": cpu_devbox_args_rdp,
    "gpu_devbox_args": gpu_devbox_args,
    "gpu_devbox_args_rdp": gpu_devbox_args_rdp,
    "opencode_devbox_args": opencode_devbox_args,
    "assisted_devbox_args": assisted_devbox_args,
    "llamacpp_devbox_args": llamacpp_devbox_args,
    "llamacpp_gpu_devbox_args": llamacpp_gpu_devbox_args,
  }
