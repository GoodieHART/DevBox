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

OPENCODE_PORT = 4096  # Default `opencode web` port
OPENCODE_HOSTNAME = "0.0.0.0"  # Bind so Modal tunnel can reach it
OPENCODE_IDLE_TIMEOUT_SECONDS = 1800  # 30 minutes idle (longer than SSH boxes, shorter than llamacpp)
OPENCODE_WORKDIR = "/data/projects"
OPENCODE_SESSIONS_DIR = "/data/projects"
OPENCODE_UPLOADS_DIR = "/data/uploads"
FORENSICS_WORKDIR = "/data/forensics"
FORENSICS_UPLOADS_DIR = "/data/forensics/uploads"

# OpenCode DevBox resource arguments (CPU-only, headroom for web server + TUI attach)
OPENCODE_DEVBOX_ARGS = {
    "secrets": None,
    "volumes": None,
    "cpu": 2.0,
    "memory": 8192,  # 8 GB headroom for Ghidra headless decompilation
    "timeout": 10800,  # 3 hours max runtime
}

ASSISTED_DEVBOX_ARGS = {
    "secrets": None,
    "volumes": None,
    "cpu": 1.0,
    "memory": 4096,
    "timeout": 10800,  # 3 hours max runtime
}

FORENSICS_DEVBOX_ARGS = {
    "secrets": None,
    "volumes": None,
    "cpu": 2.0,
    "memory": 8192,
    "timeout": 10800,
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
    "tmux",
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
    "perl",
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


def build_devbox_args(secrets, volume, *, secret_sets=None) -> dict[str, dict[str, Any]]:
  """
    Build all eight Modal function arg dicts from live handles.

    Args:
        secrets: list of Modal Secret handles (all boxes share them).
        volume: Modal Volume handle mounted at /data.

    Returns:
        dict: all seven arg dicts keyed by their devbox.py names.
  """
  secret_sets = secret_sets or {}
  ssh_secrets = secret_sets.get("ssh", secrets)
  coding_secrets = secret_sets.get("coding", ssh_secrets)
  forensic_secrets = secret_sets.get("forensics", ssh_secrets)
  exa_secrets = secret_sets.get("exa", ssh_secrets)

  cpu_devbox_args = get_resource_config("cpu", secrets=ssh_secrets, volume=volume)

  cpu_devbox_args_rdp = get_resource_config("cpu", secrets=ssh_secrets, volume=volume, is_rdp=True)

  gpu_devbox_args = get_resource_config("gpu", secrets=ssh_secrets, volume=volume, is_rdp=True)

  gpu_devbox_args_rdp = get_resource_config("gpu", secrets=ssh_secrets, volume=volume, is_rdp=True)

  opencode_devbox_args: dict[str, Any] = dict(ASSISTED_DEVBOX_ARGS)
  opencode_devbox_args["secrets"] = coding_secrets
  opencode_devbox_args["volumes"] = {"/data": volume}

  assisted_devbox_args: dict[str, Any] = dict(ASSISTED_DEVBOX_ARGS)
  assisted_devbox_args["secrets"] = coding_secrets
  assisted_devbox_args["volumes"] = {"/data": volume}

  forensics_devbox_args: dict[str, Any] = dict(FORENSICS_DEVBOX_ARGS)
  forensics_devbox_args["secrets"] = forensic_secrets
  forensics_devbox_args["volumes"] = {"/data": volume}

  llamacpp_devbox_args: dict[str, Any] = dict(LLAMACPP_DEVBOX_ARGS)
  llamacpp_devbox_args["secrets"] = exa_secrets
  llamacpp_devbox_args["volumes"] = {"/data": volume}

  llamacpp_gpu_devbox_args: dict[str, Any] = dict(LLAMACPP_GPU_DEVBOX_ARGS)
  llamacpp_gpu_devbox_args["secrets"] = exa_secrets
  llamacpp_gpu_devbox_args["volumes"] = {"/data": volume}

  return {
    "cpu_devbox_args": cpu_devbox_args,
    "cpu_devbox_args_rdp": cpu_devbox_args_rdp,
    "gpu_devbox_args": gpu_devbox_args,
    "gpu_devbox_args_rdp": gpu_devbox_args_rdp,
    "opencode_devbox_args": opencode_devbox_args,
    "assisted_devbox_args": assisted_devbox_args,
    "forensics_devbox_args": forensics_devbox_args,
    "llamacpp_devbox_args": llamacpp_devbox_args,
    "llamacpp_gpu_devbox_args": llamacpp_gpu_devbox_args,
  }


# ---------------------------------------------------------------------------
# Cost tracking — Modal published per-second rates (estimate only).
# Source: https://modal.com/pricing  (per-second billing, no minimums;
# charged on max(requested, used); 0.125 core / 128 MiB minimums).
# Reconcile estimates against `modal billing report` for authoritative numbers.
# ---------------------------------------------------------------------------
MODAL_PRICING_VERSION = "2026-10"

# CPU is priced per physical core; Modal exposes 1 physical core = 2 vCPU.
CPU_USD_PER_PHYSICAL_CORE_S = 0.0000131
# Memory priced per GiB.
MEM_USD_PER_GIB_S = 0.00000222
# GPU rates (USD per second while attached). Keys are Modal gpu= strings (lower-cased
# for lookup); None means CPU-only.
GPU_USD_PER_S = {
    None: 0.0,
    "t4": 0.000164,
    "l4": 0.000222,
    "a10g": 0.000306,
    "l40s": 0.000542,
    "a100-40gb": 0.000583,
    "a100-80gb": 0.000694,
    "rtx-pro-6000": 0.000842,
    "h100": 0.001097,
    "h200": 0.001261,
    "b200": 0.001736,
    "b300": 0.001972,
}

# Modal's default scaledown window after the last input (seconds). Used by the
# reporter to approximate billed wall-clock; in-container tracker bills raw
# elapsed (conservative-ish; actual includes this window).
SCALEDOWN_WINDOW_S = 60

# Minimum billable resources per container (Modal enforced).
MIN_BILLABLE_CORES = 0.125
MIN_BILLABLE_MEM_GIB = 128 / 1024.0


def get_pricing(cpu: float, memory_mb: int | float, gpu: str | None) -> dict[str, float]:
    """Return the per-second rate breakdown for a resource profile.

    Args:
        cpu: Modal cpu= value (vCPU-ish; converted to physical cores internally).
        memory_mb: memory in MiB.
        gpu: Modal gpu= string or None.

    Returns:
        dict with keys: cpu_rate, mem_rate, gpu_rate, total_rate (USD/sec).
    """
    physical_cores = max(MIN_BILLABLE_CORES, float(cpu) / 2.0)
    mem_gib = max(MIN_BILLABLE_MEM_GIB, float(memory_mb) / 1024.0)
    gpu_key = None if gpu is None else str(gpu).lower()
    gpu_rate = GPU_USD_PER_S.get(gpu_key, 0.0)
    cpu_rate = physical_cores * CPU_USD_PER_PHYSICAL_CORE_S
    mem_rate = mem_gib * MEM_USD_PER_GIB_S
    return {
        "cpu_rate": cpu_rate,
        "mem_rate": mem_rate,
        "gpu_rate": gpu_rate,
        "total_rate": cpu_rate + mem_rate + gpu_rate,
    }


def estimate_cost_usd(cpu: float, memory_mb: int | float, gpu: str | None, elapsed_s: float) -> float:
    """Estimate USD cost for `elapsed_s` seconds at the given resource profile."""
    if elapsed_s < 0:
        elapsed_s = 0.0
    rate = get_pricing(cpu, memory_mb, gpu)["total_rate"]
    return round(rate * float(elapsed_s), 6)
