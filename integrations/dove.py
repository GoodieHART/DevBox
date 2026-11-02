#!/usr/bin/env python3
# noqa: SIZE_OK
# Deliberately a single-file CLI: dove is copied verbatim into every image at /usr/local/bin/dove.
"""dove — one download command that adapts to the URL you give it.

Dispatches on URL shape instead of making you remember which tool to use:

    drive.google.com / docs.google.com   -> gdown
    mega.nz / mega.io / mega.co.nz       -> megadl
    t.me / telegram.me / telegram.dog    -> tgdl download-link
    terabox-family hosts                 -> TeraboxDL (library, needs a cookie)
    anything else                        -> urllib, with pointer resolution

A "pointer" is an indirection that is not a real file: a plain-text body that is
just a URL, an HTML <meta http-equiv="refresh">, or a JS location assignment.
dove follows those (bounded, cycle-checked) before deciding what to download.

Self-contained on purpose: this file is copied into every image at
/usr/local/bin/dove, so it must not import first-party DevBox modules.

Usage:
    dove URL [-o NAME] [-d DIR] [-q] [--probe] [--no-pointer]
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request

USER_AGENT = "dove/1.0 (+devbox)"
MAX_SNIFF_BYTES = 64 * 1024
MAX_POINTER_HOPS = 5
CHUNK = 1024 * 256

DRIVE_HOSTS = ("drive.google.com", "docs.google.com")
MEGA_HOSTS = ("mega.nz", "mega.io", "mega.co.nz")
TELEGRAM_HOSTS = ("t.me", "telegram.me", "telegram.dog")
TERABOX_HOSTS = (
    "terabox.com", "teraboxapp.com", "1024tera.com", "4funbox.com",
    "mirrobox.com", "nephobox.com", "momerybox.com", "tibibox.com", "terabox.app",
)

KIND_DRIVE = "drive"
KIND_MEGA = "mega"
KIND_TELEGRAM = "telegram"
KIND_TERABOX = "terabox"
KIND_DIRECT = "direct"

_META_TAG = re.compile(r"<meta[^>]+>", re.I)
_REFRESH_URL = re.compile(r"url\s*=\s*['\"]?([^'\">\s;]+)", re.I)
_JS_ASSIGN = re.compile(
    r"(?:window\.)?location(?:\.href)?\s*=\s*['\"]([^'\"]+)['\"]", re.I
)
_JS_REPLACE = re.compile(r"location\.replace\(\s*['\"]([^'\"]+)['\"]\s*\)", re.I)
_BARE_URL = re.compile(r"https?://\S+", re.I)
_BARE_PATH = re.compile(r"\.{0,2}/[^\s]+")


class DoveError(Exception):
    """Anything dove can explain to the user and exit non-zero on."""


def _host(url: str) -> str:
    try:
        host = urllib.parse.urlsplit(url).netloc.lower()
    except ValueError:
        return ""
    return host.split("@")[-1].split(":")[0]


def _on(host: str, domains: tuple[str, ...]) -> bool:
    return any(host == d or host.endswith("." + d) for d in domains)


def classify(url: str) -> str:
    """Map a URL to the backend that should handle it."""
    host = _host(url)
    if _on(host, DRIVE_HOSTS):
        return KIND_DRIVE
    if _on(host, MEGA_HOSTS):
        return KIND_MEGA
    if _on(host, TELEGRAM_HOSTS):
        return KIND_TELEGRAM
    if _on(host, TERABOX_HOSTS):
        return KIND_TERABOX
    return KIND_DIRECT


def is_drive_folder(url: str) -> bool:
    return "/folders/" in urllib.parse.urlsplit(url).path


def _int_or_none(value: str | None) -> int | None:
    try:
        return int(value) if value is not None else None
    except ValueError:
        return None


def extract_pointer(body: str, base_url: str = "") -> str | None:
    """Return the URL a text/HTML body points at, or None.

    Recognises, in order: a body that is nothing but a URL, an HTML
    meta-refresh, and a JS location assignment/replace.
    """
    text = body.strip()
    if not text:
        return None

    if _BARE_URL.fullmatch(text):
        return _absolute(text, base_url)

    # A single relative path in a text/plain body, e.g. "/files/a.zip".
    if base_url and _BARE_PATH.fullmatch(text):
        return _absolute(text, base_url)

    for tag in _META_TAG.findall(text):
        if "refresh" not in tag.lower():
            continue
        match = _REFRESH_URL.search(tag)
        if match:
            candidate = _absolute(match.group(1), base_url)
            if candidate:
                return candidate

    for pattern in (_JS_ASSIGN, _JS_REPLACE):
        match = pattern.search(text)
        if match:
            candidate = _absolute(match.group(1), base_url)
            if candidate:
                return candidate

    return None


def _absolute(candidate: str, base_url: str) -> str | None:
    candidate = candidate.strip().strip("'\"")
    if not candidate:
        return None
    resolved = urllib.parse.urljoin(base_url, candidate) if base_url else candidate
    if not resolved.lower().startswith(("http://", "https://")):
        return None
    return resolved


def safe_name(name: str, default: str = "download") -> str:
    """Reduce an arbitrary string to a safe single path component."""
    name = (name or "").replace("\\", "/").rsplit("/", 1)[-1]
    name = re.sub(r"[\x00-\x1f\x7f]", "", name).strip()
    name = name.strip(". ")
    if name in ("", ".", ".."):
        return default
    return name


def filename_from_content_disposition(value: str | None) -> str | None:
    """Parse a Content-Disposition header into a filename, if it has one."""
    if not value:
        return None

    extended = re.search(r"filename\*\s*=\s*([^;]+)", value, re.I)
    if extended:
        raw = extended.group(1).strip().strip('"')
        if "''" in raw:
            charset, _, encoded = raw.partition("''")
            try:
                return urllib.parse.unquote(encoded, encoding=charset or "utf-8")
            except (LookupError, UnicodeDecodeError):
                return urllib.parse.unquote(encoded)
        return urllib.parse.unquote(raw)

    plain = re.search(r'filename\s*=\s*"([^"]*)"', value, re.I)
    if plain:
        return plain.group(1)
    plain = re.search(r"filename\s*=\s*([^;]+)", value, re.I)
    if plain:
        return plain.group(1).strip().strip('"')
    return None


def filename_from_url(url: str) -> str | None:
    path = urllib.parse.urlsplit(url).path
    base = urllib.parse.unquote(path.rstrip("/").rsplit("/", 1)[-1])
    return safe_name(base) if base else None


def _request(url: str, *, resume_from: int = 0) -> urllib.request.Request:
    headers = {"User-Agent": USER_AGENT, "Accept-Encoding": "identity"}
    if resume_from:
        headers["Range"] = f"bytes={resume_from}-"
    return urllib.request.Request(url, headers=headers)


def _is_text(content_type: str) -> bool:
    ctype = (content_type or "").lower()
    return ctype.startswith("text/") or "html" in ctype or "xml" in ctype


def _is_attachment(content_disposition: str | None) -> bool:
    return "attachment" in (content_disposition or "").lower()


def _progress(done: int, total: int, quiet: bool) -> None:
    if quiet:
        return
    if total > 0:
        pct = done * 100.0 / total
        sys.stderr.write(f"\r  {pct:5.1f}%  {_human(done)} / {_human(total)}")
    else:
        sys.stderr.write(f"\r  {_human(done)}")
    sys.stderr.flush()


def _human(size: int) -> str:
    value = float(size)
    for unit in ("B", "KiB", "MiB", "GiB"):
        if value < 1024:
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return f"{value:.1f} TiB"


def _resolve_pointer_chain(url: str, quiet: bool) -> tuple[str, list[str]]:
    """Follow text/HTML pointers until something download-shaped appears."""
    chain = [url]
    seen = {url}
    current = url

    for _ in range(MAX_POINTER_HOPS):
        try:
            with urllib.request.build_opener().open(_request(current), timeout=30) as response:
                final = response.geturl()
                ctype = response.headers.get("Content-Type", "")
                disposition = response.headers.get("Content-Disposition")
                length = response.headers.get("Content-Length")

                if final != current and final not in seen:
                    chain.append(final)
                    seen.add(final)
                    current = final

                if not _is_text(ctype) or _is_attachment(disposition):
                    return current, chain
                declared = _int_or_none(length)
                if declared is not None and declared > MAX_SNIFF_BYTES:
                    return current, chain

                body = response.read(MAX_SNIFF_BYTES).decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            raise DoveError(f"{current} -> HTTP {exc.code} {exc.reason}") from exc
        except urllib.error.URLError as exc:
            raise DoveError(f"{current} -> {exc.reason}") from exc

        pointer = extract_pointer(body, current)
        if not pointer or pointer in seen:
            return current, chain
        chain.append(pointer)
        seen.add(pointer)
        current = pointer

    raise DoveError(
        f"stopped after {MAX_POINTER_HOPS} pointer hops (possible redirect loop): "
        + " -> ".join(chain)
    )


def _probe(url: str, quiet: bool) -> dict[str, str]:
    final, chain = _resolve_pointer_chain(url, quiet)
    with urllib.request.build_opener().open(_request(final), timeout=30) as response:
        disposition = response.headers.get("Content-Disposition")
        return {
            "kind": classify(url),
            "kind_resolved": classify(final),
            "url": url,
            "resolved": final,
            "chain": " -> ".join(chain),
            "content_type": response.headers.get("Content-Type", "unknown"),
            "content_length": response.headers.get("Content-Length", "unknown"),
            "filename": (
                filename_from_content_disposition(disposition)
                or filename_from_url(final)
                or "download"
            ),
        }


def download_direct(
    url: str,
    dest_dir: str,
    out_name: str | None,
    quiet: bool,
    follow_pointers: bool = True,
) -> str:
    """Download a direct URL, resuming if a partial file exists."""
    if follow_pointers:
        final, _ = _resolve_pointer_chain(url, quiet)
        if final != url:
            kind = classify(final)
            if kind != KIND_DIRECT:
                return dispatch(final, dest_dir, out_name, quiet, follow_pointers=False)
            url = final

    with urllib.request.build_opener().open(_request(url), timeout=60) as response:
        disposition = response.headers.get("Content-Disposition")
        name = safe_name(
            out_name
            or filename_from_content_disposition(disposition)
            or filename_from_url(response.geturl())
            or "download"
        )
        target = os.path.join(dest_dir, name)

        resume_from = 0
        if os.path.exists(target):
            resume_from = os.path.getsize(target)

        if resume_from:
            response.close()
            try:
                response = urllib.request.build_opener().open(
                    _request(url, resume_from=resume_from), timeout=60
                )
            except urllib.error.HTTPError as exc:
                if exc.code == 416:
                    if not quiet:
                        print(f"  already complete: {target}", file=sys.stderr)
                    return target
                raise DoveError(f"resume failed: HTTP {exc.code} {exc.reason}") from exc
            if response.status == 200:
                resume_from = 0
                if not quiet:
                    print("  server does not support resume, restarting", file=sys.stderr)

        total = (_int_or_none(response.headers.get("Content-Length")) or 0) + resume_from
        done = resume_from
        mode = "ab" if resume_from else "wb"

        try:
            with open(target, mode) as handle:
                while True:
                    block = response.read(CHUNK)
                    if not block:
                        break
                    handle.write(block)
                    done += len(block)
                    _progress(done, total, quiet)
        finally:
            response.close()
            if not quiet:
                sys.stderr.write("\n")

    return target


def _require(binary: str, hint: str) -> str:
    path = shutil.which(binary)
    if not path:
        raise DoveError(f"`{binary}` is not installed. {hint}")
    return path


def _run(argv: list[str], cwd: str) -> None:
    result = subprocess.run(argv, cwd=cwd)
    if result.returncode != 0:
        raise DoveError(f"`{' '.join(argv)}` exited {result.returncode}")


def _single_result(directory: str, dest_dir: str, out_name: str | None) -> str:
    """Move the one file a directory-based backend produced into place."""
    produced = [
        os.path.join(directory, entry)
        for entry in os.listdir(directory)
        if os.path.isfile(os.path.join(directory, entry))
    ]
    if not produced:
        raise DoveError("backend reported success but produced no file")
    if len(produced) > 1:
        raise DoveError(
            "backend produced multiple files; -o cannot name them. "
            f"Re-run with -d {dest_dir} and no -o."
        )
    target = os.path.join(dest_dir, safe_name(out_name) if out_name else os.path.basename(produced[0]))
    os.replace(produced[0], target)
    return target


def download_drive(url: str, dest_dir: str, out_name: str | None, quiet: bool) -> str:
    binary = _require("gdown", "Every DevBox image ships it; rebuild or install gdown.")
    argv = [binary, "--folder" if is_drive_folder(url) else "--fuzzy", url]
    if out_name:
        argv += ["-O", safe_name(out_name)]
        _run(argv, dest_dir)
        return os.path.join(dest_dir, safe_name(out_name))
    _run(argv, dest_dir)
    return dest_dir


def download_mega(url: str, dest_dir: str, out_name: str | None, quiet: bool) -> str:
    binary = _require("megadl", "Every DevBox image ships megatools.")
    if not out_name:
        _run([binary, "--path", dest_dir, url], dest_dir)
        return dest_dir
    with tempfile.TemporaryDirectory(dir=dest_dir) as staging:
        _run([binary, "--path", staging, url], staging)
        return _single_result(staging, dest_dir, out_name)


def download_telegram(url: str, dest_dir: str, out_name: str | None, quiet: bool) -> str:
    binary = _require("tgdl", "Every DevBox image ships tgdl.")
    if not out_name:
        _run([binary, "download-link", url, "-o", dest_dir], dest_dir)
        return dest_dir
    with tempfile.TemporaryDirectory(dir=dest_dir) as staging:
        _run([binary, "download-link", url, "-o", staging], staging)
        return _single_result(staging, dest_dir, out_name)


def download_terabox(url: str, dest_dir: str, out_name: str | None, quiet: bool) -> str:
    cookie = os.environ.get("DOVE_TERABOX_COOKIE") or os.environ.get("TERABOX_COOKIE")
    if not cookie:
        raise DoveError(
            "terabox links need a cookie. Set DOVE_TERABOX_COOKIE to the "
            "`lang=...; ndus=...` value from a logged-in browser session."
        )
    try:
        from TeraboxDL import TeraboxDL
    except ImportError as exc:
        raise DoveError("terabox-downloader is not installed in this image") from exc

    try:
        info = TeraboxDL(cookie).get_file_info(url)
    except Exception as exc:  # library raises bare Exception subclasses
        raise DoveError(f"terabox lookup failed: {exc}") from exc
    if not isinstance(info, dict) or "error" in info:
        raise DoveError(f"terabox lookup failed: {info}")

    if not out_name:
        result = TeraboxDL(cookie).download(info, save_path=dest_dir)
        if "error" in result:
            raise DoveError(f"terabox download failed: {result['error']}")
        return result.get("file_path") or os.path.join(dest_dir, info.get("file_name", ""))

    with tempfile.TemporaryDirectory(dir=dest_dir) as staging:
        result = TeraboxDL(cookie).download(info, save_path=staging)
        if "error" in result:
            raise DoveError(f"terabox download failed: {result['error']}")
        return _single_result(staging, dest_dir, out_name)


BACKENDS = {
    KIND_DRIVE: download_drive,
    KIND_MEGA: download_mega,
    KIND_TELEGRAM: download_telegram,
    KIND_TERABOX: download_terabox,
    KIND_DIRECT: download_direct,
}


def dispatch(
    url: str,
    dest_dir: str,
    out_name: str | None,
    quiet: bool,
    follow_pointers: bool = True,
) -> str:
    kind = classify(url)
    if kind == KIND_DIRECT:
        return download_direct(url, dest_dir, out_name, quiet, follow_pointers)
    return BACKENDS[kind](url, dest_dir, out_name, quiet)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dove",
        description="Download from Google Drive, Mega, Telegram, Terabox, or a direct URL.",
        epilog=(
            "dove picks the backend from the URL. Anything else is fetched directly, "
            "following HTTP redirects and text/HTML pointer pages."
        ),
    )
    parser.add_argument("url", help="the link to download")
    parser.add_argument("-o", "--output", help="output filename")
    parser.add_argument("-d", "--dir", default=".", help="destination directory (default: .)")
    parser.add_argument("-q", "--quiet", action="store_true", help="suppress progress output")
    parser.add_argument(
        "--probe",
        action="store_true",
        help="show the detected backend and resolved URL without downloading",
    )
    parser.add_argument(
        "--no-pointer",
        action="store_true",
        help="do not follow text/HTML pointer pages",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if not args.url.lower().startswith(("http://", "https://")):
        print(f"dove: not an http(s) URL: {args.url}", file=sys.stderr)
        return 2

    dest_dir = os.path.abspath(args.dir)
    try:
        os.makedirs(dest_dir, exist_ok=True)
    except OSError as exc:
        print(f"dove: cannot use {dest_dir}: {exc}", file=sys.stderr)
        return 2

    try:
        if args.probe:
            info = _probe(args.url, args.quiet)
            width = max(len(k) for k in info)
            for key, value in info.items():
                print(f"{key.replace('_', ' '):<{width}}  {value}")
            return 0

        kind = classify(args.url)
        if not args.quiet:
            print(f"  {kind} -> {args.url}", file=sys.stderr)

        result = dispatch(args.url, dest_dir, args.output, args.quiet, not args.no_pointer)
        if not args.quiet:
            print(f"  saved: {result}", file=sys.stderr)
        return 0
    except DoveError as exc:
        print(f"dove: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\ndove: interrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
