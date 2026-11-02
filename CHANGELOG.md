# DevBox Changelog

## DevBox Updates - 2026-11-01

### Added

- Added `dove`, a universal download helper shipped to every DevBox at `/usr/local/bin/dove`. It dispatches on URL type: `gdown` for Google Drive, `megadl` for Mega, `tgdl download-link` for Telegram, `TeraboxDL` for Terabox links, and a resumable `urllib` downloader for everything else.
- Added pointer-redirect resolution to `dove`: HTTP 3xx, bare-URL bodies, HTML `<meta http-equiv="refresh">`, and JS `location` assignments, capped at 5 hops with cycle detection.
- Added `dove --probe` to report the detected backend and resolved URL without downloading.
- Added `tests/test_dove.py` covering classification, pointer extraction, filename handling, backend routing, and the every-image wiring invariant.
- Added disk-image and credential-analysis tooling to the Forensics & Reverse Engineering box: `nmap`, `smbclient`, `chntpw`, `dislocker`, `libbde-utils`, `libvmdk-utils`, `pypykatz`, and `impacket`.
- Added `pspy64` (pinned to `v1.2.1`, SHA-256 verified at build time) for unprivileged cron and process discovery.
- Added `FORENSIC_APT_PACKAGES` and `FORENSIC_PIP_PACKAGES` to `devbox_core/config.py`, scoped to the forensics image so no other box inherits the weight.
- Added `tests/test_forensic_tooling.py` covering package definitions, denylist compliance, image scoping, the `pspy64` pin, and the FUSE warning.
- Added `KNOWN_ISSUES.md`, collecting Modal sandbox constraints, box-specific limitations, operational limits, and troubleshooting in one place.

### Changed

- The forensics banner now states that disk-image mounting is unavailable and points to `7z x` / `vmdkinfo` / `bdeinfo` instead.
- README section 7 now documents the toolset, the BitLocker unlocking-only scope, and the no-`/dev/kvm`, no-privileged, no-mount limitations.
- Corrected the documented forensics resources from 0.5 vCPU / 1GB to the actual 2 vCPU / 8GB.
- Corrected the mounting limitation text: `/dev/fuse` is present in Modal containers, but `mount(2)` is denied because there is no `CAP_SYS_ADMIN` and no `fusermount`/`fusermount3` helper.
- Moved the README's platform-constraint, forensics-limitation, downloader-note, REA-availability, and troubleshooting sections into `KNOWN_ISSUES.md`; the README now keeps short pointers instead.

### Fixed

- Fixed `dove`'s Mega backend being unusable on the CUDA box: the CUDA image built from the NVIDIA registry never installed `DOWNLOAD_APT_PACKAGES`, so `megadl` was absent. It now installs `megatools`, `p7zip-full`, and `perl` like the other boxes.
- Fixed a Modal build failure caused by `add_local_file` being followed by build steps. `dove` is now baked with `copy=True` in both base builders and the CUDA image, and a regression test rejects any mount-mode `add_local_*` followed by `apt_install` / `pip_install` / `run_commands`.

### Validation

- Test suite: 160 tests passed.
- Image builds verified in live Modal containers: the Forensics box reports all 13 expected tools (including `vol`, `pspy64`, `megadl`, `vmdkinfo`, `bdeinfo`), the Standard box reports `dove` plus all download backends, and the CUDA box now reports `megadl`.
- `dove` exercised against the live network inside a container: direct download (6034 bytes), `--probe`, and `--no-pointer` all exited 0.
- FUSE/mount capability probed empirically: `/dev/fuse` exists, `CAP_SYS_ADMIN` is unset, `mount -t tmpfs` returns `permission denied`, and no `fusermount` helper is installed.

## DevBox Updates - 2026-10-26

### Added

- Added configurable RDP quality and color-depth presets for low-bandwidth sessions, including `rdp_quality`, `rdp_max_bpp`, `RDP_QUALITY`, and `RDP_MAX_BPP`.
- Added PipeWire-based RDP audio output support to the RDP desktop image.
- Added PipeWire, WirePlumber, and pipewire-pulse startup to RDP sessions.

### Changed

- RDP desktop startup now preserves persisted XFCE state instead of deleting and recreating config directories.
- RDP idle detection now uses `pgrep` and treats probe failures as unknown rather than idle.
- RDP session startup now installs an executable `~/.xsession` launcher after persistence restoration.
- RDP quality settings now configure xrdp `max_bpp` and print recommended client resolution and color-depth settings.

### Fixed

- Fixed RDP startup failure when persisted `~/.config/xfce4` was represented by a stale empty file.
- Fixed RDP login aborts caused by unguarded persisted `~/.profile` references to a missing cargo environment file.
- Fixed RDP audio setup so PipeWire/PulseAudio-compatible clients connect to `xrdp-sink`; microphone/input redirection is not enabled.
- Fixed the output-only audio loader so it no longer attempts to load `xrdp-source`.

### Validation

- Test suite: 94 tests passed.


## DevBox Updates - 2026-10-25

### Added

- Added per-launch cost tracking under `/data/.cost/sessions/`, including resource profiles, elapsed runtime, estimated USD cost, periodic checkpoints, and the `modal run devbox.py::cost_report` reporting command.
- Added centralized Modal pricing helpers and cost-tracker tests.
- Added dedicated AI Coding and Forensics box wiring with separate resource profiles, secret sets, persistent workspaces, and OpenCode web + SSH lifecycle support.
- Added `integrations/opencode-coding.json` for the coding-focused OpenCode box.
- Added tmux to the SSH-capable DevBox images.
- Every SSH-capable DevBox now starts a detached `devbox` tmux session with three windows.
- SSH connection commands now attach directly with `tmux attach -t devbox`.
- Added a Catppuccin Mocha tmux header with styled window tabs, true color, pane borders, mouse support, clock, and a `Crafted by GoodieHART` marker.

### Changed

- Consolidated the coding and forensic launch paths around the shared OpenCode runtime.
- Coding sessions now use `/data/projects` for persistent work.
- Forensic sessions now use `/data/forensics`, with uploads stored under `/data/forensics/uploads`.
- Separated SSH, Gemini, forensic, and EXA secrets so launchers receive only the credentials they need.
- Updated launcher menus, README connection instructions, box names, and roadmap entries for the consolidated workflows.
- Made extra-package parameters compatible with Modal function registration.
- Updated the tmux runtime to load `/etc/devbox/tmux.conf` explicitly and restore its `/root` link after session restoration.
- Added mouse support for tmux window tabs, scrolling, and pane resizing.

### Fixed

- Moved tmux configuration additions to the final step of each concrete Modal image definition, avoiding Modal build failures caused by `add_local_*` operations followed by later image build steps.

### Validation

- Test suite: 83 tests passed.
- Python compilation passed for the modified runtime and image-definition modules.
- The tmux configuration loaded successfully under tmux 3.4.
- A three-window tmux session was created successfully.
