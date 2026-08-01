"""Builder for a FAT12 virtual floppy containing autounattend.xml.

Local helper for unit tests and QA only — the in-sandbox entrypoint
(todo 5) rebuilds its own floppy at runtime. The image is a standard
1.44 MB (2880 x 1 KiB) floppy that QEMU exposes via ``-fda`` so Windows
Setup auto-reads autounattend.xml at boot.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile

# Resolve tools at import time: prefer PATH, fall back to known locations
# (mtools is not on PATH on the dev machine; mkfs.fat lives in /usr/sbin
# which is often missing from non-root PATHs).
DD = shutil.which("dd") or "/usr/bin/dd"
MKFS_FAT = shutil.which("mkfs.fat") or "/usr/sbin/mkfs.fat"
MCOPY = shutil.which("mcopy") or "/tmp/mtools-prefix/usr/bin/mcopy"

FLOPPY_SIZE_KB = 2880
VOLUME_LABEL = "UNATTEND"


def _run(command: list[str]) -> None:
    """Run a command, raising with its output if it fails."""
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"command failed with exit code {result.returncode}: "
            f"{' '.join(command)}\n"
            f"stdout: {result.stdout}\n"
            f"stderr: {result.stderr}"
        )


def build_floppy(autounattend_xml: str, out_path: str) -> None:
    """Create a FAT12 floppy image at ``out_path`` containing autounattend.xml.

    Args:
        autounattend_xml: Full autounattend.xml document (see
            ``install_files.autounattend.build_autounattend``).
        out_path: Destination image path; the file is overwritten if it
            already exists.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        xml_path = os.path.join(tmp_dir, "autounattend.xml")
        with open(xml_path, "w", encoding="utf-8") as handle:
            handle.write(autounattend_xml)

        _run([DD, "if=/dev/zero", f"of={out_path}", "bs=1024", f"count={FLOPPY_SIZE_KB}"])
        _run([MKFS_FAT, "-F", "12", "-n", VOLUME_LABEL, out_path])
        _run([MCOPY, "-i", out_path, xml_path, "::/"])
