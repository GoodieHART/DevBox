"""Unit tests for windows_iso.py — no network access, no real downloads."""

from __future__ import annotations

import hashlib
import subprocess
import sys

import pytest

import windows_iso

KNOWN_FILENAME = "en-us_windows_11_iot_enterprise_ltsc_2024_x64_dvd_f6b14814.iso"
KNOWN_URL = f"https://drive.massgrave.dev/{KNOWN_FILENAME}"
SAMPLE_DATA = b"hello windows vm"


def test_verify_sha256_matches(tmp_path):
    """Given a file with known content and its real hash, verify returns True."""
    iso = tmp_path / "test.iso"
    iso.write_bytes(SAMPLE_DATA)
    expected = hashlib.sha256(SAMPLE_DATA).hexdigest()

    assert windows_iso.verify_sha256(str(iso), expected) is True


def test_verify_sha256_mismatch_raises_with_both_hashes(tmp_path):
    """Given a wrong expected hash, verify raises ValueError citing both hashes."""
    iso = tmp_path / "test.iso"
    iso.write_bytes(SAMPLE_DATA)
    wrong = "0" * 64

    with pytest.raises(ValueError) as excinfo:
        windows_iso.verify_sha256(str(iso), wrong)

    message = str(excinfo.value)
    assert wrong in message
    assert hashlib.sha256(SAMPLE_DATA).hexdigest() in message


def test_filename_from_url_extracts_iso_name():
    """The ISO filename parses out of a massgrave.dev drive URL."""
    assert windows_iso.filename_from_url(KNOWN_URL) == KNOWN_FILENAME


def test_filename_from_url_with_query_and_slash():
    """A trailing-slash or query URL still yields the bare filename."""
    assert windows_iso.filename_from_url(f"{KNOWN_URL}?download=1") == KNOWN_FILENAME


def test_cli_download_dry_run_prints_both_volume_put_commands():
    """Dry-run prints both volume-put commands (ISO and .sha256) and exits 0."""
    result = subprocess.run(
        [sys.executable, "windows_iso.py", "download", "--dry-run", "--out", "isos/"],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert (
        f"modal volume put windows-vm-data isos/{KNOWN_FILENAME} /isos/windows.iso"
        in result.stdout
    )
    assert (
        f"modal volume put windows-vm-data isos/{KNOWN_FILENAME}.sha256 "
        "/isos/windows.iso.sha256"
        in result.stdout
    )


def test_cli_help_exits_zero_and_lists_subcommands():
    """--help exits 0 and shows both subcommands."""
    result = subprocess.run(
        [sys.executable, "windows_iso.py", "--help"],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "download" in result.stdout
    assert "verify" in result.stdout


def test_cli_verify_reports_missing_checksum_file(tmp_path):
    """Verify without a sibling .sha256 file exits non-zero with a clear error."""
    iso = tmp_path / "test.iso"
    iso.write_bytes(SAMPLE_DATA)

    result = subprocess.run(
        [sys.executable, "windows_iso.py", "verify", "--file", str(iso)],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "no checksum file" in result.stderr
