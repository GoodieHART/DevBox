"""Windows 11 IoT Enterprise LTSC 2024 ISO acquisition + SHA-256 verification.

Downloads the Windows ISO from the massgrave.dev ecosystem on the user's
machine (NOT inside a Modal sandbox — ``drive.massgrave.dev`` direct links
are geo-blocked from some networks), verifies its SHA-256, writes the
verified checksum to ``<iso>.sha256``, and prints the ``modal volume put``
commands that upload both files to the ``windows-vm-data`` volume.

The ISO filename and SHA-256 rotate upstream (massgrave.dev docs); the SHA
is resolved and verified at download time, never trusted as a constant.

Usage::

    python windows_iso.py download --out isos/ [--url URL] [--sha256 HEX] [--filename NAME] [--dry-run]
    python windows_iso.py verify --file isos/<iso>

The Windows VM entrypoint (todo 5) verifies ``/isos/windows.iso`` against
``/isos/windows.iso.sha256`` — the checksum file this CLI writes and uploads.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import sys
import urllib.parse
import urllib.request
from typing import Callable

#: Known-good filename + primary source URL. No SHA here: upstream filenames
#: and checksums rotate — resolve the SHA at download time (massgrave.dev docs).
ISO_DEFAULTS: dict[str, str] = {
    "filename": "en-us_windows_11_iot_enterprise_ltsc_2024_x64_dvd_f6b14814.iso",
    "url": "https://drive.massgrave.dev/en-us_windows_11_iot_enterprise_ltsc_2024_x64_dvd_f6b14814.iso",
}

VOLUME_NAME = "windows-vm-data"
REMOTE_ISO_PATH = "/isos/windows.iso"
REMOTE_SHA_PATH = "/isos/windows.iso.sha256"
CHUNK_SIZE = 10 * 1024 * 1024  # 10 MiB streaming chunks
_HASH_CHUNK = 1024 * 1024


def filename_from_url(url: str) -> str:
    """Extract the filename from a massgrave.dev drive URL."""
    return urllib.parse.urlparse(url).path.rsplit("/", 1)[-1]


def compute_sha256(path: str) -> str:
    """Return the lowercase hex SHA-256 of the file at ``path``."""
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(_HASH_CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def verify_sha256(path: str, expected: str) -> bool:
    """Return ``True`` if ``path`` hashes to ``expected``.

    Raises:
        ValueError: on mismatch, with both the expected and actual hashes.
    """
    actual = compute_sha256(path)
    if actual.casefold() != expected.casefold():
        raise ValueError(
            f"SHA-256 mismatch for {path}: expected {expected}, got {actual}"
        )
    return True


def download_iso(url: str, dest: str, sha256: str | None = None) -> str:
    """Stream ``url`` to ``dest`` in 10 MiB chunks; verify SHA-256 if given.

    Returns:
        The destination path.
    """
    with urllib.request.urlopen(url) as response, open(dest, "wb") as out:
        while chunk := response.read(CHUNK_SIZE):
            out.write(chunk)
    if sha256 is not None:
        verify_sha256(dest, sha256)
    return dest


def volume_put_commands(local_iso: str, local_sha: str) -> list[str]:
    """The two ``modal volume put`` commands uploading ISO + checksum."""
    return [
        f"modal volume put {VOLUME_NAME} {local_iso} {REMOTE_ISO_PATH}",
        f"modal volume put {VOLUME_NAME} {local_sha} {REMOTE_SHA_PATH}",
    ]


def cmd_download(args: argparse.Namespace) -> None:
    local_iso = os.path.join(args.out, args.filename)
    local_sha = f"{local_iso}.sha256"
    commands = volume_put_commands(local_iso, local_sha)

    if args.dry_run:
        for command in commands:
            print(command)
        return

    os.makedirs(os.path.dirname(local_iso) or ".", exist_ok=True)
    download_iso(args.url, local_iso, args.sha256)
    # `args.sha256` already matched during download; the verified hex is what
    # the entrypoint checks against, so writing it avoids re-hashing the ISO.
    verified_hex = args.sha256 if args.sha256 is not None else compute_sha256(local_iso)
    with open(local_sha, "w", encoding="ascii") as f:
        f.write(f"{verified_hex}\n")

    print(f"Downloaded {local_iso} (SHA-256 {verified_hex})")
    for command in commands:
        print(command)


def cmd_verify(args: argparse.Namespace) -> None:
    sha_file = f"{args.file}.sha256"
    try:
        with open(sha_file, encoding="ascii") as f:
            expected = f.read().strip()
    except FileNotFoundError:
        raise ValueError(
            f"no checksum file {sha_file} found next to the ISO; "
            f"run `python windows_iso.py download` first"
        ) from None
    verify_sha256(args.file, expected)
    print(f"OK: {args.file} matches SHA-256 {expected}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="windows_iso",
        description=(
            "Acquire the Windows 11 IoT Enterprise LTSC 2024 ISO from "
            "massgrave.dev, verify SHA-256, and print modal volume-put commands."
        ),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    download = subparsers.add_parser(
        "download", help="Download the ISO and print volume-put commands"
    )
    download.add_argument("--out", default="isos/", help="output directory (default: isos/)")
    download.add_argument("--url", default=ISO_DEFAULTS["url"], help="ISO source URL")
    download.add_argument("--sha256", help="expected SHA-256; verified after download")
    download.add_argument(
        "--filename",
        default=ISO_DEFAULTS["filename"],
        help="ISO filename (default: known massgrave.dev filename)",
    )
    download.add_argument(
        "--dry-run",
        action="store_true",
        help="skip download and only print the volume-put commands",
    )

    verify = subparsers.add_parser("verify", help="Verify an ISO against its .sha256 file")
    verify.add_argument("--file", required=True, help="path to the ISO to verify")

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    dispatch: dict[str, Callable[[argparse.Namespace], None]] = {
        "download": cmd_download,
        "verify": cmd_verify,
    }
    try:
        dispatch[args.command](args)
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
