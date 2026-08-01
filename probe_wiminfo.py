"""Self-contained wiminfo probe for resolving the Windows ISO image index.

Runs in a REGULAR Modal function container (no VM sandbox, no /dev/kvm
needed — wiminfo only reads the ISO). This module deliberately imports ONLY
stdlib + modal at module level: the worker container must be able to import
it to find ``run_wiminfo``, and the VM image built here mounts ONLY this
module (``add_local_python_source("probe_wiminfo")`` — a NAMED mount; the
no-arg form used by windows_vm_image() mounts nothing, so importing repo
modules like config/images in this module would crash the container).

Usage::

    modal run probe_wiminfo.py            # prints RESOLVED_IMAGE_INDEX=<n>

wimlib >= 1.13 (Debian ``wimtools``) reads the WIM inside the ISO image
directly. Requires the ISO at /vol/isos/windows.iso on the windows-vm-data
volume (uploaded via the T2 CLI's printed ``modal volume put`` commands).
"""

from __future__ import annotations

import subprocess

import modal

#: Modal app hosting the probe function (kebab-case per AGENTS.md).
app = modal.App("windows-vm-wiminfo")

#: Persistent disk + ISO storage, shared with the Windows VM (duplicated
#: locally — importing it from windows_vm.py would recreate the module cycle).
WINDOWS_VOLUME = modal.Volume.from_name("windows-vm-data", create_if_missing=True)

#: wiminfo edition name to resolve (mirrors windows_vm.IOT_LTSC_EDITION —
#: kept here so this module stays fully self-contained).
IOT_LTSC_EDITION = "Windows 11 IoT Enterprise LTSC 2024"

#: Minimal image: wimtools provides /usr/bin/wiminfo; the NAMED
#: add_local_python_source mounts THIS module into the container so Modal
#: can import it to find run_wiminfo (no-arg form mounts nothing).
_WIMINFO_IMAGE = (
    modal.Image.debian_slim(python_version="3.12")
    .apt_install("wimtools")
    .add_local_python_source("probe_wiminfo")
)


@app.function(
    image=_WIMINFO_IMAGE,
    volumes={"/vol": WINDOWS_VOLUME},
    timeout=1800,
    cpu=1,
    memory=1024,
)
def run_wiminfo() -> str:
    """Run ``wiminfo /vol/isos/windows.iso`` and return the raw stdout."""
    result = subprocess.run(
        ["wiminfo", "/vol/isos/windows.iso"],
        capture_output=True, text=True, timeout=900,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"wiminfo failed (rc={result.returncode}): "
            f"{(result.stderr or result.stdout).strip()}"
        )
    return result.stdout


def probe() -> str:
    """Run the wiminfo probe in the cloud; returns the raw wiminfo stdout."""
    return run_wiminfo.remote()


def parse_wiminfo_index(stdout: str) -> int:
    """Extract the ``Imaging Index`` of the IoT LTSC 2024 edition from wiminfo.

    Mirrors windows_vm.parse_wiminfo_index (kept in sync by hand — this
    module must not import windows_vm). See that docstring for details.

    Raises:
        ValueError: if no matching edition block is found.
    """
    current_index: int | None = None
    for line in stdout.splitlines():
        stripped = line.strip()
        if stripped.startswith("Imaging Index:"):
            current_index = int(stripped.split(":", 1)[1].strip())
        elif (
            stripped.startswith("Name:")
            and IOT_LTSC_EDITION in stripped
            and current_index is not None
        ):
            return current_index
    raise ValueError(f"no '{IOT_LTSC_EDITION}' edition found in wiminfo output")


@app.local_entrypoint()
def probe_image_index() -> None:
    """CLI probe: resolve + print the ISO's IoT LTSC 2024 image index.

    ``modal run probe_wiminfo.py`` — must use @app.local_entrypoint() (modal
    1.5.3 ignores bare ``__main__``/``app.run()`` blocks).
    """
    index = parse_wiminfo_index(probe())
    print(f"RESOLVED_IMAGE_INDEX={index}")
