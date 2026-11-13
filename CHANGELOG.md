# DevBox Changelog

## DevBox Updates - 2026-11-13

### Added

- Added an XFCE desktop over RDP to both Forensics boxes, built on the same xrdp, PipeWire audio, and session startup used by the RDP Desktop Box.
- Added Firefox ESR, netcat, and ping to the Forensics box for browser-based targets and network diagnostics.
- Added WPScan 3.8.28 to the Forensics box, along with the Ruby toolchain its native extensions require.
- Added HTB Starting Point access to both HTB VPN boxes, with a `htb-starting-point` secret (`HTB_SP_OVPN_CONFIG`).

### Changed

- The HTB VPN launchers now ask which network to join: Labs, Starting Point, or both at once.
- Forensics boxes now reset the idle timer on RDP, SSH, or OpenCode web activity.
- The Forensics HTB VM starts xrdp after the VPN is up and exposes RDP on port 3389 alongside SSH and OpenCode.
- The Forensics image now derives from the shared RDP desktop layer instead of the minimal base image.

### Removed

- Removed the loopback Chromium/noVNC browser from the Forensics HTB VM, including `runtime/vnc_browser.py`, `VNC_BROWSER_PACKAGES`, the `DEVBOX_VNC_*` settings, and their tests.

### Fixed

- Fixed RDP image packaging so `runtime.htb_vm` ships with the RDP Desktop Box, matching the standard image.
- A missing HTB VPN secret now fails before the VM starts, with the `modal secret create` command needed to fix it.

### Validation

- Test suite: 190 tests passed.
- Verified on Modal: Forensics box runs xrdp, Firefox, netcat, ping, and WPScan; the HTB Starting Point VM reaches `10.129.0.1` over `tun1` while normal internet traffic keeps its default route.


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
