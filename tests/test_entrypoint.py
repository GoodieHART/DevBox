"""Unit tests for entrypoint.sh.

Sources the script (its top-level main() is guarded by BASH_SOURCE so sourcing
is side-effect free) and exercises the testable helpers with a temp dir + fake
ISO/sha files. No network, no sandbox, no QEMU.
"""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

ENTRYPOINT = Path(__file__).resolve().parents[1] / "entrypoint.sh"


def _run(fn_call: str, cwd: Path) -> subprocess.CompletedProcess:
    """Run one helper call in a shell that sources entrypoint.sh."""
    script = (
        f"source {ENTRYPOINT}\n"
        "set +e\n"  # the script enables errexit; we disable it to capture rcs
        f"{fn_call}\n"
        "echo __RC__=$?\n"
    )
    return subprocess.run(
        ["bash", "-c", script], capture_output=True, text=True, cwd=cwd, timeout=60
    )


def _rc(stdout: str) -> int:
    for line in stdout.splitlines():
        if line.startswith("__RC__="):
            return int(line.split("=", 1)[1])
    raise AssertionError(f"no __RC__ sentinel in stdout: {stdout!r}")


def _write_iso_pair(
    tmp_path: Path,
    content: bytes = b"fake-iso-bytes",
    hex_override: str | None = None,
    conventional: bool = False,
) -> tuple[Path, Path]:
    iso = tmp_path / "windows.iso"
    iso.write_bytes(content)
    sha = tmp_path / "windows.iso.sha256"
    hexval = hex_override if hex_override is not None else hashlib.sha256(content).hexdigest()
    sha.write_text(f"{hexval}  windows.iso\n" if conventional else f"{hexval}\n")
    return iso, sha


def test_check_kvm_aborts_when_dev_kvm_absent(tmp_path):
    """Given no /dev/kvm, check_kvm returns rc 1 with the clear error."""
    p = _run("check_kvm /nonexistent/kvm", tmp_path)
    assert _rc(p.stdout) == 1
    assert "/dev/kvm" in p.stderr
    assert "cannot run the Windows VM" in p.stderr
    assert "nested virtualization" in p.stderr


def test_check_kvm_passes_when_dev_kvm_present(tmp_path):
    """Given an existing device path, check_kvm returns rc 0 silently."""
    p = _run("check_kvm /dev/null", tmp_path)
    assert _rc(p.stdout) == 0
    assert p.stderr == ""


def test_sha_verify_aborts_when_sha256_file_missing(tmp_path):
    """Given a missing .sha256 file, install-mode verify aborts (no silent skip)."""
    iso = tmp_path / "windows.iso"
    iso.write_bytes(b"fake-iso-bytes")
    p = _run(f"verify_iso_sha256 {iso} {tmp_path}/windows.iso.sha256", tmp_path)
    assert _rc(p.stdout) == 1
    assert "missing" in p.stderr.lower()
    assert "windows.iso.sha256" in p.stderr


def test_sha_verify_aborts_on_mismatch(tmp_path):
    """Given a wrong checksum, verify aborts with rc 1."""
    iso, sha = _write_iso_pair(tmp_path, hex_override="0" * 64)
    p = _run(f"verify_iso_sha256 {iso} {sha}", tmp_path)
    assert _rc(p.stdout) == 1
    assert "FAILED" in p.stderr
    assert "SHA-256" in p.stderr


def test_sha_verify_proceeds_on_match(tmp_path):
    """Given a matching checksum (T2 bare-hex format), verify proceeds with rc 0."""
    iso, sha = _write_iso_pair(tmp_path)
    p = _run(f"verify_iso_sha256 {iso} {sha}", tmp_path)
    assert _rc(p.stdout) == 0
    assert "SHA-256 OK" in p.stdout


def test_sha_verify_proceeds_on_conventional_checksum_line(tmp_path):
    """Given a 'HEX  filename' checksum line, verify also proceeds (format-agnostic)."""
    iso, sha = _write_iso_pair(tmp_path, conventional=True)
    p = _run(f"verify_iso_sha256 {iso} {sha}", tmp_path)
    assert _rc(p.stdout) == 0
    assert "SHA-256 OK" in p.stdout


def test_sha_verify_aborts_when_iso_missing(tmp_path):
    """Given a missing ISO but a present sha file, verify aborts with rc 1."""
    sha = tmp_path / "windows.iso.sha256"
    sha.write_text("0" * 64 + "\n")
    p = _run(f"verify_iso_sha256 {tmp_path}/windows.iso {sha}", tmp_path)
    assert _rc(p.stdout) == 1
    assert "not found" in p.stderr
