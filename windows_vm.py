"""
Windows VM (RDP) sandbox logic.

Hosts the Windows 11 VM sandbox: the sandbox factory, entrypoint/RPC
upload, unattended-install orchestration, RDP tunnel, idle monitor, and
connection-info printing. Filled in by later todos.

Adapted from modal-projects/windows-sandboxes (MIT license):
https://github.com/modal-projects/windows-sandboxes/blob/main/sandbox.py
"""

from __future__ import annotations

import base64
from pathlib import Path

import modal
from modal.container_process import ContainerProcess

from config import WINDOWS_VM_CFG
from images import windows_vm_image

# Persistent disk + ISO storage for the Windows VM (kebab-case per Modal naming).
WINDOWS_VOLUME = modal.Volume.from_name("windows-vm-data", create_if_missing=True)

# Runtime files uploaded into the sandbox (reference pattern: base64 + sb.exec).
SANDBOX_DIR = "/sandbox"
ENTRYPOINT_REMOTE = f"{SANDBOX_DIR}/entrypoint.sh"
RPC_SERVER_REMOTE = f"{SANDBOX_DIR}/rpc_server.py"


def create_windows_sandbox(
    app_ref, boot_mode: str = "boot", region: str | list[str] | None = None
) -> modal.Sandbox:
    """
    Create a Modal VM sandbox running the Windows VM (QEMU/KVM).

    Args:
        app_ref: Modal app to create the sandbox under.
        boot_mode: "boot" to boot from the saved disk, "install" for a
            fresh unattended install. Consumed by the entrypoint launcher
            (todo 5), not by the sandbox create call itself.
        region: Modal region(s) to run the sandbox in (e.g. "aws-us-east-1").
            None = platform default. Useful because /dev/kvm availability in
            VM sandboxes varies by region.

    Returns:
        modal.Sandbox: the running VM sandbox.

    Raises:
        ValueError: if boot_mode is not "boot" or "install".
    """
    if boot_mode not in ("boot", "install"):
        raise ValueError(f"boot_mode must be 'boot' or 'install', got {boot_mode!r}")

    ports = WINDOWS_VM_CFG["ports"]
    return modal.Sandbox.create(
        app=app_ref,
        image=windows_vm_image(),
        cpu=WINDOWS_VM_CFG["cpu"],
        memory=WINDOWS_VM_CFG["memory"],
        timeout=WINDOWS_VM_CFG["timeout"],
        region=region,
        experimental_options={"vm_runtime": True},  # VM sandbox -> /dev/kvm
        unencrypted_ports=[ports["rdp"]],  # raw TCP — RDP cannot use TLS relay
        encrypted_ports=[ports["novnc"], ports["rpc"]],  # HTTPS relay
        volumes={"/vol": WINDOWS_VOLUME},
    )


def probe_kvm(sb: modal.Sandbox) -> str:
    """
    Probe whether the VM sandbox exposes /dev/kvm for hardware-accelerated QEMU.

    Args:
        sb: the running VM sandbox.

    Returns:
        str: "KVM_OK" if /dev/kvm exists, else "KVM_MISSING".
    """
    p = sb.exec("bash", "-c", "[ -e /dev/kvm ] && echo KVM_OK || echo KVM_MISSING")
    return p.stdout.read().strip()


def _write_b64(sb: modal.Sandbox, path: str, content: bytes) -> None:
    """Write bytes into the sandbox via base64 + sb.exec (reference pattern)."""
    b64 = base64.b64encode(content).decode()
    p = sb.exec(
        "bash", "-c",
        f'mkdir -p "$(dirname {path})"; echo {b64} | base64 -d > {path}',
    )
    p.wait()


def upload_runtime_files(sb: modal.Sandbox) -> None:
    """
    Upload entrypoint.sh + rpc_server.py into the sandbox at /sandbox/.

    Called once per sandbox, before start_entrypoint. Uses base64 + sb.exec
    (the windows-sandboxes reference pattern) rather than the filesystem API
    because the exec path is verified working on VM sandboxes.

    Args:
        sb: the running VM sandbox.
    """
    root = Path(__file__).resolve().parent
    _write_b64(sb, ENTRYPOINT_REMOTE, (root / "entrypoint.sh").read_bytes())
    _write_b64(sb, RPC_SERVER_REMOTE, (root / "rpc_server.py").read_bytes())
    p = sb.exec("bash", "-c", f"chmod +x {ENTRYPOINT_REMOTE} {RPC_SERVER_REMOTE}")
    p.wait()


def start_entrypoint(sb: modal.Sandbox, boot_mode: str = "boot") -> ContainerProcess:
    """
    Start the sandbox entrypoint (QEMU boot + RPC server) for the given mode.

    Does not block: returns the exec handle so callers (install orchestration,
    idle monitor) can poll logs and observe completion.

    Args:
        sb: the running VM sandbox (after upload_runtime_files).
        boot_mode: "boot" to boot from the persisted disk, "install" for a
            fresh unattended install (ISO SHA-256 gate inside the entrypoint).

    Returns:
        ContainerProcess: handle for the entrypoint exec.

    Raises:
        ValueError: if boot_mode is not "boot" or "install".
    """
    if boot_mode not in ("boot", "install"):
        raise ValueError(f"boot_mode must be 'boot' or 'install', got {boot_mode!r}")
    return sb.exec("bash", ENTRYPOINT_REMOTE, env={"BOOT_MODE": boot_mode})
