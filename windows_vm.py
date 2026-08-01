"""
Windows VM (RDP) sandbox logic.

Hosts the Windows 11 VM sandbox: the sandbox factory, entrypoint/RPC
upload, unattended-install orchestration (todo 8), RDP tunnel, idle
monitor, and connection-info printing.

Todo 8 install orchestration is KVM-INDEPENDENT by design: the image index
is resolved via ``wiminfo`` in a REGULAR Modal function container (see the
self-contained probe_wiminfo.py — no VM sandbox, no /dev/kvm),
autounattend.xml is delivered over RPC /write-file, and the UEFI navigation
+ setup polling only speak to the in-sandbox RPC server. The live boot gate
(VM sandbox + /dev/kvm) is deferred until the account has nested
virtualization (see task-8 evidence).

Adapted from modal-projects/windows-sandboxes (MIT license):
https://github.com/modal-projects/windows-sandboxes/blob/main/sandbox.py
"""

from __future__ import annotations

import base64
import dataclasses
import json
import time
import urllib.error
import urllib.request
from pathlib import Path

import modal
from modal.container_process import ContainerProcess

import probe_wiminfo
from config import WINDOWS_VM_CFG
from images import windows_vm_image
from install_files.autounattend import PRODUCT_KEY, build_autounattend

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


# ---------------------------------------------------------------------------
# Todo 8 — image-index resolution (KVM-independent: regular container)
# ---------------------------------------------------------------------------
# The wiminfo probe itself lives in probe_wiminfo.py — a self-contained
# module importing ONLY stdlib + modal, mounted into its own image via a
# NAMED add_local_python_source("probe_wiminfo"). (windows_vm_image() ends
# with a NO-ARG add_local_python_source, which mounts nothing — importing
# this module's repo deps inside that image would crash the container.)

#: wiminfo edition name to resolve (the single-edition IoT LTSC 2024 DVD
#: commonly indexes at 1; multi-edition media index it higher — never hardcode).
IOT_LTSC_EDITION = "Windows 11 IoT Enterprise LTSC 2024"


def parse_wiminfo_index(stdout: str) -> int:
    """Extract the ``Imaging Index`` of the IoT LTSC 2024 edition from wiminfo.

    wiminfo prints one ``Imaging Index: N`` / ``Name: <edition>`` block per
    image; we track the current index and return it when the Name matches.

    Args:
        stdout: raw wiminfo output (str — matches sb.exec stdout typing).

    Returns:
        int: the image index of the IoT LTSC 2024 edition.

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


def resolve_image_index(runner=None) -> int:
    """Resolve the IoT LTSC 2024 image index from the ISO on the volume.

    KVM-INDEPENDENT: by default runs wiminfo via ``probe_wiminfo.probe`` — a
    REGULAR modal function container (self-contained module + the
    windows-vm-data volume at /vol) — no VM sandbox, no /dev/kvm. Requires
    the ISO to have been uploaded first (T2 CLI: download + both ``modal
    volume put`` commands).

    Args:
        runner: optional callable returning wiminfo stdout (tests inject a
            fake; production uses probe_wiminfo.probe).

    Returns:
        int: the resolved image index.
    """
    if runner is None:
        runner = probe_wiminfo.probe
    return parse_wiminfo_index(runner())


# ---------------------------------------------------------------------------
# Todo 8 — RPC client (talks to the in-sandbox rpc_server.py via tunnels)
# ---------------------------------------------------------------------------


class RpcError(RuntimeError):
    """Raised when the in-sandbox RPC server is unreachable or errors."""


class WindowsVMClient:
    """HTTP client for the in-sandbox RPC server (rpc_server.py contract).

    The base_url is the Modal tunnel URL for port 8765 (``encrypted_ports``
    relay: TLS terminates at the Modal edge, the server speaks plaintext —
    see rpc_server.py docstring). Endpoints used by the install
    orchestration: GET /status, GET /screenshot, GET /health, POST
    /write-file, POST /sendkey, POST /type.
    """

    def __init__(self, base_url: str, timeout: float = 15.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _request(self, method: str, path: str, payload: dict | None = None) -> bytes:
        """Send one JSON request; returns the raw response body."""
        data = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(self.base_url + path, data=data, method=method)
        if data is not None:
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return resp.read()
        except urllib.error.URLError as exc:  # covers HTTPError too
            raise RpcError(f"RPC {method} {path} failed: {exc}") from None

    def get_status(self) -> str:
        """GET /status -> the single state string ('running|installing|installed|stopped')."""
        return json.loads(self._request("GET", "/status"))["status"]

    def wait_ready(self, timeout: float = 120.0, poll_interval: float = 2.0) -> bool:
        """Poll GET /health until the RPC server responds.

        The entrypoint starts the RPC server BEFORE QEMU (todo 8 timing
        contract), so a short wait here guarantees /write-file lands before
        the entrypoint's 15-min autounattend staging window expires.

        Raises:
            RpcError: if the server never becomes ready within ``timeout``.
        """
        deadline = time.monotonic() + timeout
        last_error: RpcError | None = None
        while time.monotonic() < deadline:
            try:
                self._request("GET", "/health")
                return True
            except RpcError as exc:
                last_error = exc
                time.sleep(poll_interval)
        raise RpcError(f"RPC server not ready within {timeout}s: {last_error}")

    def write_file(self, path: str, content: bytes) -> dict:
        """POST /write-file: stage bytes at ``path`` (base64 in the payload)."""
        body = json.loads(
            self._request("POST", "/write-file", {
                "path": path,
                "content_b64": base64.b64encode(content).decode(),
            })
        )
        return body

    def sendkey(self, key: str) -> dict:
        """POST /sendkey: press one HMP key name (e.g. 'ret', 'esc', 'down')."""
        return json.loads(self._request("POST", "/sendkey", {"key": key}))

    def type_text(self, text: str, *, enter: bool = False, delay: float = 0.12) -> dict:
        """POST /type: type text (optionally followed by a ret)."""
        return json.loads(
            self._request("POST", "/type", {"text": text, "delay": delay, "enter": enter})
        )

    def screenshot(self) -> bytes | None:
        """GET /screenshot: PNG bytes, or None when QEMU is down (500)/unreachable."""
        try:
            return self._request("GET", "/screenshot")
        except RpcError:
            return None


def rpc_client_for_sandbox(sb) -> WindowsVMClient:
    """Build the RPC client from a live sandbox's tunnel (port 8765 relay)."""
    return WindowsVMClient(sb.tunnels()[WINDOWS_VM_CFG["ports"]["rpc"]])


# ---------------------------------------------------------------------------
# Todo 8 — install orchestration (deliver + UEFI nav + setup polling)
# ---------------------------------------------------------------------------

#: Entrypoint staging path: install mode waits for this file, builds the FAT12
#: floppy from its dir, then starts QEMU (entrypoint.sh contract, todo 8).
FLOPPY_STAGING_PATH = "/tmp/floppy_contents/autounattend.xml"
#: UEFI nav sequence: esc (boot menu), down/down (install), ret/ret (confirm
#: 'Press any key to boot from CD' + boot).
UEFI_NAV_KEYS: tuple[str, ...] = ("esc", "down", "down", "ret", "ret")
#: Screenshot frames smaller than this are blank/black — not setup-UI evidence.
MIN_FRAME_BYTES = 10_000
#: Static-screen duration (setup phase) that triggers the GVLK contingency.
FREEZE_SECONDS = 3 * 60
#: Default setup-confirmation window (acceptance: 'installing' within 10 min).
SETUP_TIMEOUT_SECONDS = 600
SETUP_POLL_INTERVAL = 10


@dataclasses.dataclass
class SetupPollResult:
    """Outcome of :func:`wait_for_setup` — state + evidence frames.

    Frames are evidence only, NEVER acceptance gates (plan: machine signals
    are /status + /mark; screenshots are diagnostic).
    """

    status: str
    saw_installing: bool
    gvlk_injected: bool
    frames: list[bytes]  # screenshots captured during the poll (evidence only)
    elapsed: float


class SetupTimeoutError(RuntimeError):
    """Raised by :func:`wait_for_setup` when setup never confirms in time."""

    def __init__(
        self,
        frames: list[bytes],
        saw_installing: bool,
        gvlk_injected: bool,
        elapsed: float,
        timeout: float,
    ):
        self.frames = list(frames)
        self.saw_installing = saw_installing
        self.gvlk_injected = gvlk_injected
        self.elapsed = elapsed
        self.timeout = timeout
        super().__init__(
            f"setup phase not confirmed within {timeout}s "
            f"(saw_installing={saw_installing}, gvlk_injected={gvlk_injected}, "
            f"frames={len(self.frames)})"
        )


def detect_key_prompt(frame: bytes | None, prev: bytes | None) -> bool:
    """Heuristic product-key-prompt detector: a static, non-blank dialog frame.

    The VM image has no OCR stack (images.py is frozen), so this is a
    conservative proxy: identical consecutive frames of meaningful size mean
    the installer is waiting on a static dialog — the key-entry prompt is the
    canonical case. Positive (OCR-level) identification is a todo 9 live-QA
    item; this heuristic only ever gates the idempotent GVLK contingency.
    """
    if frame is None or prev is None or frame != prev:
        return False
    return len(frame) >= MIN_FRAME_BYTES


def deliver_autounattend(vm, index: int) -> dict:
    """Build autounattend.xml for the resolved ``index`` and stage it via RPC.

    POSTs to /write-file at the entrypoint staging path
    (``/tmp/floppy_contents/autounattend.xml``). Timing contract: the RPC
    server starts BEFORE QEMU (entrypoint.sh), and install mode waits
    (bounded 15 min) for this file before building the floppy and booting —
    so delivery must happen after the server is up and before QEMU starts;
    :func:`install_windows` calls :meth:`WindowsVMClient.wait_ready` first.

    Args:
        vm: client-like object with ``write_file(path, content)``.
        index: resolved WIM image index (never hardcoded).

    Returns:
        dict: the /write-file response ({"written": N, "path": ...}).
    """
    xml = build_autounattend(index)
    return vm.write_file(FLOPPY_STAGING_PATH, xml.encode("utf-8"))


def navigate_uefi_boot(vm) -> list[str]:
    """Send the UEFI boot-menu navigation keys (esc, down, down, ret, ret).

    Reference sequence: esc to raise the boot menu, down/down to the install
    entry, ret to confirm 'Press any key to boot from CD', ret again.

    Args:
        vm: client-like object with ``sendkey(key)``.

    Returns:
        list[str]: the keys sent (evidence/tests).
    """
    sent: list[str] = []
    for key in UEFI_NAV_KEYS:
        vm.sendkey(key)
        sent.append(key)
    return sent


def wait_for_setup(vm, timeout: float = SETUP_TIMEOUT_SECONDS,
                   poll_interval: float = SETUP_POLL_INTERVAL) -> SetupPollResult:
    """Poll the RPC server until the Windows Setup phase is confirmed.

    Polls /status (expecting ``installing`` — install mode reports it from
    RPC-server start) and /screenshot frames as setup-UI evidence. Returns a
    :class:`SetupPollResult` once setup is CONFIRMED:

    * status ``installed`` (the guest's /mark install-done marker), or
    * status ``installing`` with two consecutive valid, non-identical frames
      (the setup screen is progressing).

    Freeze contingency (M8): while polling, if the setup screen stays static
    for > :data:`FREEZE_SECONDS`, the frame is captured and — when
    :func:`detect_key_prompt` agrees — the GVLK is typed once via /type+ret
    (idempotent; Setup ignores stray keys on non-input screens).

    Args:
        vm: client-like object with ``get_status()`` and ``screenshot()``.
        timeout: hard cap for the setup confirmation (seconds).
        poll_interval: seconds between polls.

    Returns:
        SetupPollResult: the confirmed status + evidence frames.

    Raises:
        SetupTimeoutError: if setup is not confirmed within ``timeout``
            (the frames captured so far are attached for evidence).
    """
    start = time.monotonic()
    deadline = start + timeout
    saw_installing = False
    frames: list[bytes] = []
    last_frame: bytes | None = None
    static_since: float | None = None
    injected = False
    last_status: str | None = None

    while time.monotonic() < deadline:
        try:
            last_status = vm.get_status()
        except RpcError:
            last_status = None  # transient — keep polling until the cap
        if last_status == "installed":
            return SetupPollResult("installed", True, injected, frames,
                                   time.monotonic() - start)
        if last_status == "installing":
            saw_installing = True

        try:
            frame = vm.screenshot()
        except RpcError:
            frame = None
        if frame is not None:
            frames.append(frame)

        # Freeze detection: static frame > FREEZE_SECONDS during setup phase.
        if last_status == "installing" and frame is not None:
            if frame == last_frame:
                if static_since is None:
                    static_since = time.monotonic()
                elif (
                    time.monotonic() - static_since >= FREEZE_SECONDS
                    and not injected
                ):
                    injected = True
                    if detect_key_prompt(frame, last_frame):
                        vm.type_text(PRODUCT_KEY, enter=True)
            else:
                static_since = None
        else:
            static_since = None

        # Setup confirmed: installing observed + two valid, progressing frames.
        if (
            saw_installing
            and frame is not None
            and last_frame is not None
            and len(frame) >= MIN_FRAME_BYTES
            and frame != last_frame
        ):
            return SetupPollResult(last_status or "installing", True, injected,
                                   frames, time.monotonic() - start)

        last_frame = frame
        time.sleep(poll_interval)

    raise SetupTimeoutError(frames=frames, saw_installing=saw_installing,
                            gvlk_injected=injected,
                            elapsed=time.monotonic() - start, timeout=timeout)


def install_windows(vm, *, index: int | None = None,
                    timeout: float = SETUP_TIMEOUT_SECONDS,
                    poll_interval: float = SETUP_POLL_INTERVAL) -> SetupPollResult:
    """Orchestrate the unattended install (KVM-independent portion, todo 8).

    Order (plan M7): wait for the RPC server (started by the entrypoint
    BEFORE QEMU), deliver autounattend.xml via /write-file into the
    entrypoint's floppy staging dir (the entrypoint builds the FAT12 floppy
    from it and only then starts QEMU), send the UEFI boot-navigation keys,
    then wait for the setup phase.

    The sandbox lifecycle (create / upload runtime files / start entrypoint
    in install mode) is the caller's job (todos 9/11) — this function only
    needs a VM client; unless ``index`` is given it resolves the image index
    via wiminfo in a regular container.

    Args:
        vm: client-like object (WindowsVMClient or test double).
        index: pre-resolved image index (skips the wiminfo probe).
        timeout: setup-confirmation cap, forwarded to wait_for_setup.
        poll_interval: poll interval, forwarded to wait_for_setup.

    Returns:
        SetupPollResult: the confirmed setup state + evidence frames.
    """
    if index is None:
        index = resolve_image_index()
    vm.wait_ready(timeout=120)
    deliver_autounattend(vm, index)
    navigate_uefi_boot(vm)
    return wait_for_setup(vm, timeout=timeout, poll_interval=poll_interval)
