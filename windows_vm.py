"""
Windows VM (RDP) sandbox logic.

Hosts the Windows 11 VM sandbox: the sandbox factory, entrypoint/RPC
upload, unattended-install orchestration, RDP tunnel, idle monitor, and
connection-info printing. Filled in by later todos.

Adapted from modal-projects/windows-sandboxes (MIT license):
https://github.com/modal-projects/windows-sandboxes/blob/main/sandbox.py
"""

from __future__ import annotations

import modal

from config import WINDOWS_VM_CFG
from images import windows_vm_image

# Persistent disk + ISO storage for the Windows VM (kebab-case per Modal naming).
WINDOWS_VOLUME = modal.Volume.from_name("windows-vm-data", create_if_missing=True)


def create_windows_sandbox(app_ref, boot_mode: str = "boot") -> modal.Sandbox:
    """
    Create a Modal VM sandbox running the Windows VM (QEMU/KVM).

    Args:
        app_ref: Modal app to create the sandbox under.
        boot_mode: "boot" to boot from the saved disk, "install" for a
            fresh unattended install. Consumed by the entrypoint launcher
            (todo 5), not by the sandbox create call itself.

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
