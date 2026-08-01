#!/usr/bin/env bash
# windows-vm entrypoint — QEMU/KVM boot + RPC orchestration, runs INSIDE the
# Modal VM sandbox (uploaded at runtime by windows_vm.upload_runtime_files).
#
# BOOT_MODE=boot    boot from the persisted disk on /vol (no install media).
# BOOT_MODE=install fresh unattended install: verify ISO SHA-256, build the
#                   autounattend floppy from the XML staged via RPC /write-file,
#                   then boot from the ISO with the floppy attached.
#
# Adapted from modal-projects/windows-sandboxes (MIT license):
# https://github.com/modal-projects/windows-sandboxes/blob/main/sandbox.py
# Changes vs the reference: guest NIC (e1000e + SLIRP hostfwd 3389), RDP port,
# KVM abort instead of TCG fallback, ISO from /vol (not baked into the image),
# SHA-256 gate in install mode, /write-file -> /tmp/floppy_contents staging so
# the RPC server can deliver autounattend.xml BEFORE QEMU starts (todo 8
# contract), and the shutdown contract (exit 0 once QEMU exits -> sandbox ends).
#
# Protocol summary (documented in rpc_server.py):
#   rpc_server.py starts BEFORE QEMU (BOOT_MODE env). Install mode then waits
#   for /tmp/floppy_contents/autounattend.xml (delivered by POST /write-file),
#   builds the floppy from that staging dir, and only then starts QEMU.
#   Boot mode starts QEMU immediately. When the guest fully powers down
#   (HMP system_powerdown via the RPC server), QEMU exits and this entrypoint
#   exits 0, terminating the sandbox.

set -euo pipefail

MODE="${BOOT_MODE:-boot}"

VOL="/vol"
DISK_PATH="$VOL/windows-disk.qcow2"
OVMF_VARS="$VOL/OVMF_VARS_4M.fd"
OVMF_CODE="/usr/share/OVMF/OVMF_CODE_4M.fd"
ISO_PATH="$VOL/isos/windows.iso"
SHA_FILE="$VOL/isos/windows.iso.sha256"
FLOPPY="/tmp/floppy.img"
FLOPPY_CONTENTS="/tmp/floppy_contents"
RPC_SERVER="/sandbox/rpc_server.py"
HMP_SOCK="/tmp/qemu-hmp.sock"
AUTOUNATTEND_WAIT_SECONDS=900  # 15 min for T8 to deliver the XML via /write-file
QEMU_GRACE_SECONDS=10          # keep RPC /status reachable ('stopped') before exit

# ---------------------------------------------------------------------------
# Testable helpers (sourced by tests/test_entrypoint.py; main() guarded below)
# ---------------------------------------------------------------------------

check_kvm() {
    # Abort (rc 1) when /dev/kvm is absent — no TCG fallback in product code.
    # Path is parameterized for tests; production always uses /dev/kvm.
    local dev_kvm="${1:-/dev/kvm}"
    if [ ! -e "$dev_kvm" ]; then
        echo "ERROR: /dev/kvm not available (checked '$dev_kvm'). A Modal VM sandbox" >&2
        echo "without KVM cannot run the Windows VM; contact Modal support to enable" >&2
        echo "nested virtualization. Aborting (no TCG fallback)." >&2
        return 1
    fi
}

verify_iso_sha256() {
    # Verify <iso> against <sha_file> (T2's CLI writes the bare hex, e.g.
    # "abc123...\n" — windows_iso.py cmd_download). Compare the first token
    # directly: sha256sum -c would reject bare-hex files ("no properly
    # formatted SHA checksum lines"), and first-token parsing also accepts
    # conventional "HEX  filename" checksum files. Aborts (rc 1) on a missing
    # sha256 file, missing ISO, empty/mismatched checksum.
    local iso="${1:?iso path required}"
    local sha_file="${2:?sha256 file path required}"
    if [ ! -f "$sha_file" ]; then
        echo "ERROR: SHA-256 file '$sha_file' is missing. Install mode requires it —" >&2
        echo "upload it next to the ISO (e.g. 'modal volume put windows-vm-data" >&2
        echo "<iso>.sha256 /isos/windows.iso.sha256'). Aborting install." >&2
        return 1
    fi
    if [ ! -f "$iso" ]; then
        echo "ERROR: ISO '$iso' not found. Install mode requires the ISO at" >&2
        echo "$VOL/isos/windows.iso. Aborting install." >&2
        return 1
    fi
    local expected actual
    expected=$(awk 'NR==1 {print $1}' "$sha_file")
    actual=$(sha256sum "$iso" | awk '{print $1}')
    if [ -z "$expected" ] || [ "$expected" != "$actual" ]; then
        echo "ERROR: SHA-256 verification FAILED for '$iso' (expected $expected," >&2
        echo "got $actual). Aborting install." >&2
        return 1
    fi
    echo "SHA-256 OK: $iso"
}

build_floppy() {
    # FAT12 virtual floppy from the /write-file staging dir (T7 recipe).
    dd if=/dev/zero of="$FLOPPY" bs=1024 count=2880 status=none
    mkfs.fat -F 12 -n UNATTEND "$FLOPPY"
    for f in "$FLOPPY_CONTENTS"/*; do
        if [ -f "$f" ]; then
            mcopy -i "$FLOPPY" "$f" "::/$(basename "$f")"
        fi
    done
    echo "Floppy contents:"
    mdir -i "$FLOPPY" ::
}

# ---------------------------------------------------------------------------
# Main flow
# ---------------------------------------------------------------------------

main() {
    case "$MODE" in
        boot|install) ;;
        *)
            echo "ERROR: invalid BOOT_MODE '$MODE' (expected boot|install). Aborting." >&2
            exit 1
            ;;
    esac
    echo "=== windows-vm entrypoint: BOOT_MODE=$MODE ==="

    # (a) OVMF vars: persistent copy on the volume (code pflash is read-only).
    if [ ! -f "$OVMF_VARS" ]; then
        echo "Copying OVMF vars to volume..."
        cp /usr/share/OVMF/OVMF_VARS_4M.fd "$OVMF_VARS"
    fi

    # (b) Disk: create once; boot mode must never re-create it (persistence).
    if [ ! -f "$DISK_PATH" ]; then
        echo "Creating 60G qcow2 disk..."
        qemu-img create -f qcow2 "$DISK_PATH" 60G
    fi

    # (c) KVM gate — production guardrail, no TCG fallback.
    check_kvm || exit 1

    # (c2) Install mode only: SHA-256 gate before anything touches the ISO.
    if [ "$MODE" = "install" ]; then
        echo "=== INSTALL MODE ==="
        verify_iso_sha256 "$ISO_PATH" "$SHA_FILE" || exit 1
    fi

    # (f) RPC server FIRST so the client can /write-file the answer file while
    # QEMU is not yet running (todo 8 contract: XML lands before QEMU starts).
    echo "Starting RPC server (BOOT_MODE=$MODE) on :8765 ..."
    BOOT_MODE="$MODE" python3 "$RPC_SERVER" &
    echo "RPC server started."

    # (e) noVNC web proxy (Debian novnc package ships /usr/share/novnc).
    echo "Starting websockify (noVNC) on :6080 -> 127.0.0.1:5900 ..."
    websockify --web=/usr/share/novnc 0.0.0.0:6080 127.0.0.1:5900 >/tmp/websockify.log 2>&1 &
    echo "websockify started."

    QEMU_ARGS=(
        -enable-kvm
        -m 4096
        -cpu host
        -smp 4
        -drive "file=$DISK_PATH,if=ide,format=qcow2"
        -drive "if=pflash,format=raw,readonly=on,file=$OVMF_CODE"
        -drive "if=pflash,format=raw,file=$OVMF_VARS"
        -netdev "user,id=n1,hostfwd=tcp::3389-:3389"
        -device e1000e,netdev=n1
        -vnc 127.0.0.1:0
        -usb
        -device usb-tablet
        -vga std
        -display none
        -monitor "unix:$HMP_SOCK,server,nowait"
    )

    if [ "$MODE" = "install" ]; then
        wait_for_autounattend || exit 1
        build_floppy
        QEMU_ARGS+=(-cdrom "$ISO_PATH" -fda "$FLOPPY" -boot order=d)
    fi

    echo "=== Starting QEMU ==="
    set +e  # capture QEMU's rc; errexit would skip the grace window below
    qemu-system-x86_64 "${QEMU_ARGS[@]}"
    QEMU_RC=$?
    set -e
    echo "=== QEMU exited (rc=$QEMU_RC) — guest fully off ==="

    # (g) Shutdown contract: keep the sandbox alive a few seconds so the
    # orchestrator can observe /status == 'stopped', then exit 0 (the exec'd
    # entrypoint ending terminates the sandbox).
    sleep "$QEMU_GRACE_SECONDS"
    exit 0
}

wait_for_autounattend() {
    # Bounded wait for the answer file delivered via RPC /write-file.
    local waited=0
    echo "Waiting for $FLOPPY_CONTENTS/autounattend.xml via RPC /write-file" \
        "(max ${AUTOUNATTEND_WAIT_SECONDS}s)..."
    while [ "$waited" -lt "$AUTOUNATTEND_WAIT_SECONDS" ]; do
        if [ -f "$FLOPPY_CONTENTS/autounattend.xml" ]; then
            echo "autounattend.xml delivered after ${waited}s."
            return 0
        fi
        sleep 5
        waited=$((waited + 5))
    done
    echo "ERROR: autounattend.xml was not delivered via RPC /write-file within" >&2
    echo "${AUTOUNATTEND_WAIT_SECONDS}s. Aborting install." >&2
    return 1
}

if [[ "${BASH_SOURCE[0]:-}" == "$0" ]]; then
    main "$@"
fi
