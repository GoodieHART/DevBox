# Known Issues & Limitations

DevBox runs inside Modal's sandboxed containers. Most surprises come from that
boundary rather than from DevBox itself. This file collects everything that does
not work, behaves differently from a normal Linux host, or needs a workaround.

- [Modal platform constraints](#modal-platform-constraints)
- [Forensics & Reverse Engineering box](#forensics--reverse-engineering-box)
- [dove (universal downloader)](#dove-universal-downloader)
- [Native reverse engineering (REA)](#native-reverse-engineering-rea)
- [Operational limits](#operational-limits)
- [Troubleshooting](#troubleshooting)

## Modal platform constraints

- **Init system**: Containers use `dumb-init`, not `systemd`. You won't have
  systemd services available.

  ```sh
  root@modal:/data# ps -p 1 -o comm=
  dumb-init
  root@modal:/data#
  ```

- **No virtualization**: Containers don't have access to `/dev/kvm`, so you
  can't run VMs or nested virtualization.

- **No mount permission**: `/dev/fuse` exists, but the container has no
  `CAP_SYS_ADMIN` and ships neither `fusermount` nor `fusermount3`. `mount -t
  tmpfs` returns `permission denied`, so FUSE-based disk-image mounting cannot
  work.

- **No Docker/containerd**: Running Docker or containerd inside a Modal
  container is not supported.

- **No Unix sockets**: Modal doesn't support Unix sockets. Services that rely
  on them (for example MariaDB) won't work out of the box.

- **No Homebrew**: `brew` does not work inside Modal containers.

- **No `sudo` by default**: You're already running as `root`, so `sudo` isn't
  needed (or installed by default).

- **`htop` readings are misleading**: Modal containers run on massive shared
  instances. `htop` shows host-level resource usage, not your container's
  allocated resources. Don't trust the CPU/RAM percentages you see there.

## Forensics & Reverse Engineering box

**Disk-image mounting is unavailable.** `bdemount`, `vmdkmount`, and
`dislocker` are installed but will fail at mount time because the container has
no mount permission (see above). Use `vmdkinfo` / `bdeinfo` to read metadata and
`7z x <image>.vmdk` to extract files instead. Booting a disk image as a VM is
out of scope for the same reason.

**No credential-cracking tools.** `john`, `hashcat`, and `bitlocker2john` are
refused by the package denylist (see [Warnings & Open
Letter](README.md#warnings--open-letter)). BitLocker *unlocking* with a known
key is supported; BitLocker *password recovery* is not.

## dove (universal downloader)

- **Terabox needs a cookie.** Export `DOVE_TERABOX_COOKIE` with the
  `lang=...; ndus=...` value from a logged-in browser session.
- **Telegram needs a prior login.** Run `tgdl login` first; `dove` reports the
  auth error if the session is missing.
- **Resume is server-dependent.** Direct downloads resume when the target file
  already exists and the server honours `Range`. If the server answers `200`
  instead of `206`, `dove` restarts the download from zero.

## Native reverse engineering (REA)

The Forensics box ships REA with a native decompiler stack. These are **not
available on this Linux box**:

- **Hopper, IDA, Kuna** — proprietary. Bring your own via
  `HOPPER_LAUNCHER_PATH` / `REA_IDA_MCP_CONFIG` / `REA_KUNA_*`.
- **Rizin / Cutter** — not installed.
- **macOS-only capabilities** — Mach-O UI inspection, asset catalogs, native
  Swift demangling.

## Operational limits

- **First build takes 30-45 minutes.** Modal builds the container image from
  scratch. Subsequent runs are instant because the image is cached.
- **Idle timeouts**: standard boxes shut down after 5 minutes without an active
  SSH connection; AI Coding and Forensics boxes after 30 minutes without SSH or
  web activity; the llama.cpp Research Center after 1 hour.
- **Cost figures are estimates.** `cost_report` uses Modal's published
  per-second rates and does not account for the default 60 s scaledown window
  or billing on `max(requested, used)`. Use `--reconcile` or `modal billing
  report` for authoritative numbers.
- **GPU functions need a payment method.** Modal validates every function at
  app startup, including GPU launchers you never pick. Without a GPU payment
  method, run in [CPU-only mode](README.md#cpu-only-mode-no-gpu-payment-method).

## Troubleshooting

### "Secret not found" errors

Make sure you've created all the required secrets. Run `modal secret list` to
check what's stored. If a secret is missing, recreate it with the
`modal secret create` commands from the [Setup](README.md#setup) section.

### SSH key not working or stale keys

If you've regenerated your SSH key or it's just not connecting, old keys might
be lingering on Modal's side. Delete the stale secret and reinsert it:

```bash
modal secret delete ssh-public-key
modal secret create ssh-public-key PUBKEY="$(cat ~/.ssh/id_rsa.pub)"
```

### First build taking forever

Yep, that's normal — see [Operational limits](#operational-limits). Grab a
coffee, stretch your legs; subsequent runs are instant.

### Container terminated unexpectedly

Usually caused by network hiccups on your end. If you're running in attached
mode (`modal run devbox.py`), a dropped connection can kill the container. Try
running in detached mode instead:

```bash
modal run -d devbox.py
```

Just don't forget to terminate it when you're done 🙂

### RDP not connecting

Double-check the address, username, and password printed when the container
started. Make sure your RDP client is connecting to the right port. If you're on
mobile, try a different client — some can be finicky.

### llama.cpp model download fails

Check your internet connection and make sure the HuggingFace URL is valid. Some
models require you to be logged in to HuggingFace — if it's a gated model,
you'll need to set up HF token authentication. Try a different model from the
catalog first to isolate the issue.

### "Payment method" errors on GPU functions

Modal is validating the GPU launchers at app startup — even if you only wanted a
CPU box. Either add a payment method, or run in [CPU-only
mode](README.md#cpu-only-mode-no-gpu-payment-method):

```bash
DEVBOX_CPU_ONLY=1 modal run devbox.py
```

On Windows PowerShell the assignment must target the environment:

```powershell
$env:DEVBOX_CPU_ONLY = "1"; modal run devbox.py
```
