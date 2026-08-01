"""
RPC server for the Windows VM — runs INSIDE the Modal VM sandbox next to QEMU
(uploaded at runtime by windows_vm.upload_runtime_files, started by the
entrypoint BEFORE QEMU so the client can stage the answer file first).

Protocol (todo 5 contract, referenced by todos 8/9/11/12):

- State model: single status string ``running | installing | installed | stopped``.
    * ``installed``  — set ONLY by ``POST /mark``: the guest posts
      ``http://10.0.2.2:8765/mark`` (SLIRP gateway) from FirstLogonCommands #4
      once the unattended install reaches the desktop. No other endpoint or
      code path may set it.
    * ``installing`` — install mode (BOOT_MODE=install env): from server start
      until the /mark marker arrives. Covers the pre-QEMU staging phase.
    * ``running``    — boot mode with the QEMU process alive.
    * ``stopped``    — boot mode with the QEMU process not running (pre-QEMU
      startup or after system_powerdown completes).
- Transport: the sandbox serves PLAIN HTTP on 0.0.0.0:8765. Modal's
  ``encrypted_ports=[8765]`` tunnel terminates TLS at the Modal edge (the
  client speaks https:// to the relay with a valid certificate), so the
  in-sandbox server must speak plaintext — matching the reference repo's
  server.py, whose urllib client uses a default (verifying) SSL context.
- Key/typing: HMP ``sendkey`` names (e.g. ``ret``, ``esc``, ``ctrl-alt-delete``).
- Guest state comes ONLY from the /mark marker and external probes; there is
  NO in-guest command execution (no qemu-guest-agent, no guest-exec channel).
- /write-file stages files for the entrypoint: todo 8 POSTs
  autounattend.xml to /tmp/floppy_contents/ BEFORE QEMU starts (the entrypoint
  waits for it, builds the FAT12 floppy from that dir, then boots QEMU).

Adapted from modal-projects/windows-sandboxes server.py (MIT license):
https://github.com/modal-projects/windows-sandboxes/blob/main/server.py
Changes vs the reference: /status reports the single-state model (not a
qemu_running dict), /mark implements the installed-marker handshake, and the
state machine is unit-testable (module-level functions, no network).
"""

from __future__ import annotations

import base64
import json
import os
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HMP_SOCK = "/tmp/qemu-hmp.sock"
SCREENSHOT_PATH = "/tmp/screenshot.png"  # QEMU writes PNG for .png screendumps
DEFAULT_EXEC_TIMEOUT = 30  # /exec sandbox-side command bound (seconds)
MAX_EXEC_TIMEOUT = 300  # hard cap so one /exec cannot pin a thread forever

# Set by the entrypoint: BOOT_MODE=boot|install (read once at startup).
_BOOT_MODE = os.environ.get("BOOT_MODE", "boot")

_state_lock = threading.Lock()
_marked = False  # set ONLY by POST /mark


# ---------------------------------------------------------------------------
# HMP interaction
# ---------------------------------------------------------------------------

_SHIFT_MAP = {
    "!": "shift-1", "@": "shift-2", "#": "shift-3", "$": "shift-4",
    "%": "shift-5", "^": "shift-6", "&": "shift-7", "*": "shift-8",
    "(": "shift-9", ")": "shift-0", "_": "shift-minus", "+": "shift-equal",
    "{": "shift-bracket_left", "}": "shift-bracket_right",
    "|": "shift-backslash", ":": "shift-semicolon", '"': "shift-apostrophe",
    "<": "shift-comma", ">": "shift-dot", "?": "shift-slash",
    "~": "shift-grave_accent",
}
for _c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
    _SHIFT_MAP[_c] = f"shift-{_c.lower()}"

_NORMAL_MAP = {
    " ": "spc", "-": "minus", "=": "equal", "[": "bracket_left",
    "]": "bracket_right", "\\": "backslash", ";": "semicolon",
    "'": "apostrophe", ",": "comma", ".": "dot", "/": "slash",
    "`": "grave_accent",
}


def char_to_key(c: str) -> str | None:
    """Map one character to an HMP sendkey name, or None if unmappable."""
    if c in _SHIFT_MAP:
        return _SHIFT_MAP[c]
    if c in _NORMAL_MAP:
        return _NORMAL_MAP[c]
    if c.isalnum():
        return c
    return None


# ---------------------------------------------------------------------------
# HMP interaction
# ---------------------------------------------------------------------------

_hmp_lock = threading.Lock()


def hmp_send(command: str) -> str:
    """Send a command to QEMU's HMP socket and return the response."""
    with _hmp_lock:
        try:
            result = subprocess.run(
                ["socat", "-", f"UNIX-CONNECT:{HMP_SOCK}"],
                input=f"{command}\n",
                capture_output=True,
                text=True,
                timeout=5,
            )
            return result.stdout.strip()
        except subprocess.TimeoutExpired:
            return "timeout"
        except Exception as e:  # noqa: BLE001 - HMP must never crash the server
            return f"error: {e}"


def sendkey(key: str) -> str:
    return hmp_send(f"sendkey {key}")


def type_text(text: str, delay: float = 0.12) -> dict:
    typed = 0
    skipped: list[str] = []
    for c in text:
        key = char_to_key(c)
        if key is None:
            skipped.append(c)
            continue
        sendkey(key)
        typed += 1
        time.sleep(delay)
    return {"typed": typed, "skipped": skipped, "total": len(text)}


# ---------------------------------------------------------------------------
# State machine
# ---------------------------------------------------------------------------


def qemu_running() -> bool:
    try:
        result = subprocess.run(
            ["pgrep", "-c", "qemu-system"],
            capture_output=True, text=True, timeout=5,
        )
        return result.stdout.strip() != "0"
    except Exception:  # noqa: BLE001 - probe failure => treat as not running
        return False


def compute_status() -> str:
    """Single state model: installed > installing > running > stopped."""
    with _state_lock:
        marked = _marked
    if marked:
        return "installed"
    if _BOOT_MODE == "install":
        # Install mode: 'installing' from server start until the /mark marker
        # (covers the pre-QEMU staging phase). A QEMU crash mid-install still
        # reports 'installing' — diagnose via /exec + /screenshot.
        return "installing"
    if qemu_running():
        return "running"
    return "stopped"


def mark_installed(payload: str) -> None:
    """Record the guest's install-done marker. THE only path to 'installed'."""
    global _marked
    with _state_lock:
        _marked = True
    ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    # T9 evidence: the server-side /mark log line.
    print(f"[{ts}] /mark received (payload={payload!r}) -> status=installed", flush=True)


def take_screenshot() -> bytes | None:
    """HMP screendump to /tmp/screenshot.png; None when QEMU is down."""
    hmp_send(f"screendump {SCREENSHOT_PATH}")
    time.sleep(1)
    try:
        with open(SCREENSHOT_PATH, "rb") as f:
            return f.read()
    except OSError:
        return None


# ---------------------------------------------------------------------------
# HTTP API
# ---------------------------------------------------------------------------


class VMHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):  # noqa: A002 - silence default noise
        pass

    def _json_response(self, data: dict, status: int = 200):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self) -> dict:
        length = int(self.headers.get("Content-Length", 0))
        if length == 0:
            return {}
        return json.loads(self.rfile.read(length))

    def _read_raw_body(self) -> str:
        length = int(self.headers.get("Content-Length", 0))
        if length == 0:
            return ""
        return self.rfile.read(length).decode("utf-8", "replace")

    def do_GET(self):
        if self.path == "/health":
            self._json_response({"ok": True})
        elif self.path == "/status":
            self._json_response({"status": compute_status()})
        elif self.path == "/screenshot":
            data = take_screenshot()
            if data is None:
                self._json_response({"error": "no screenshot (QEMU down?)"}, 500)
                return
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        else:
            self._json_response({"error": "not found"}, 404)

    def do_POST(self):
        if self.path == "/mark":
            # Guest posts raw 'installed' (PowerShell Invoke-WebRequest -Body).
            payload = self._read_raw_body()
            mark_installed(payload)
            self._json_response({"status": "installed"})

        elif self.path == "/sendkey":
            body = self._read_body()
            key = body.get("key", "")
            result = sendkey(key)
            self._json_response({"result": result, "key": key})

        elif self.path == "/type":
            body = self._read_body()
            text = body.get("text", "")
            delay = body.get("delay", 0.12)
            if body.get("enter", False):
                result = type_text(text, delay)
                sendkey("ret")
            else:
                result = type_text(text, delay)
            self._json_response(result)

        elif self.path == "/hmp":
            body = self._read_body()
            result = hmp_send(body.get("command", ""))
            self._json_response({"result": result})

        elif self.path == "/shutdown":
            hmp_send("system_powerdown")
            self._json_response({"result": "shutdown sent"})

        elif self.path == "/reset":
            hmp_send("system_reset")
            self._json_response({"result": "reset sent"})

        elif self.path == "/exec":
            # Sandbox-side command helper ONLY — never guest execution.
            body = self._read_body()
            cmd = body.get("command", "")
            timeout = min(int(body.get("timeout", DEFAULT_EXEC_TIMEOUT)), MAX_EXEC_TIMEOUT)
            try:
                result = subprocess.run(
                    ["bash", "-c", cmd],
                    capture_output=True, text=True, timeout=timeout,
                )
                self._json_response({
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                    "returncode": result.returncode,
                })
            except subprocess.TimeoutExpired:
                self._json_response({"error": "timeout"}, 504)
            except Exception as e:  # noqa: BLE001
                self._json_response({"error": str(e)}, 500)

        elif self.path == "/write-file":
            # Stage files in the sandbox (e.g. /tmp/floppy_contents/autounattend.xml).
            body = self._read_body()
            path = body.get("path", "")
            try:
                content = base64.b64decode(body.get("content_b64", ""))
                os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
                with open(path, "wb") as f:
                    f.write(content)
                self._json_response({"written": len(content), "path": path})
            except Exception as e:  # noqa: BLE001
                self._json_response({"error": str(e)}, 500)

        else:
            self._json_response({"error": "not found"}, 404)


def build_server(host: str = "0.0.0.0", port: int = 8765) -> ThreadingHTTPServer:
    """Build the RPC server (plain HTTP — see module docstring re: Modal edge TLS)."""
    server = ThreadingHTTPServer((host, port), VMHandler)
    server.daemon_threads = True
    return server


def main() -> None:
    port = int(os.environ.get("RPC_PORT", "8765"))
    server = build_server("0.0.0.0", port)
    print(f"VM RPC server listening on :{port} (BOOT_MODE={_BOOT_MODE})", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
