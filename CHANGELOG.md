# DevBox Changelog

## DevBox Updates - 2026-11-15

### Added

- zsh is now the login shell on every box, with `zsh-autosuggestions`, `zsh-syntax-highlighting`, and `zsh-completions`.
- The setup lives in `/etc/devbox/zshrc`, baked into each image and sourced from `/etc/zsh/zshrc`, so Function boxes, RDP terminals, and the HTB VM get the same shell.
- zsh keeps the bash behaviour: Starship, the login banner, and the Forensics aliases and environment.
- `.zsh_history` is persisted alongside `.bash_history`.
- `zsh-completions` is pinned to 0.36.0 and installed from its release tarball, because Debian does not package it.

### Validation

- Test suite: 229 tests passed.
- Verified on Modal: root logs in as `/usr/bin/zsh`, `ZSH_HIGHLIGHT_VERSION` is `0.7.1-2_debian`, the autosuggestion style and functions are loaded, 180 completion files register `compdef`, and the banner prints in an interactive login shell.
- Verified in an HTB VM Sandbox: `/etc/devbox/zshrc` is present, all three tmux panes run `zsh`, and the banner renders with a quote in the pane.

## DevBox Updates - 2026-11-14

### Added

- The Forensics toolchain is now on `PATH`: `ghidra`, `ghidra-headless`, `jadx`, and `jadx-gui`, each setting up the bundled Temurin 21 JDK itself.
- Added Ghidra and JADX desktop icons and application-menu entries to the Forensics box, with projects under `/data/forensics/ghidra`.
- Added `vol3`, `vol.py`, `volshell3`, `pspy`, `ll`, and `la` aliases, and the JDK/Ghidra environment for non-login shells such as the XFCE terminal.
- Added the AWT X11 libraries (`libxtst6`, `libxi6`, `libxrender1`, `libxext6`) that Ghidra and JADX need to draw their GUIs.

### Changed

- `jadx` is a wrapper script instead of a symlink, so it also works from the desktop and from `bash -c`, where no login profile has run.
- Existing volumes have `/opt/jadx/bin` stripped from persisted shell profiles, so the wrapper is not shadowed.

### Removed

- Removed the Document Processing Box, including `doc_processing_image` and `launch_doc_processor`. `pandoc` and `texlive-full` were used by that box alone.
- Launcher choices are now 1-7: Standard at 1, AI Coding at 2, LLM Playroom at 3, RDP Desktop at 4, llama.cpp CPU at 5, Forensics at 6, llama.cpp GPU at 7.

### Fixed

- Fixed the OpenCode idle watchdog: it treated any HTTP 200 from port 4096 as user activity, so AI Coding and Forensics boxes never idled and always ran to their 3-hour hard timeout. Activity now comes from established connections to the port.

### Validation

- Test suite: 203 tests passed.
- Verified on Modal: `ghidra`, `ghidra-headless`, `jadx`, and `jadx-gui` resolve to the wrappers, Ghidra and JADX GUI windows open under Xvfb, `ghidra-headless` imports a binary into `/data/forensics/ghidra`, both desktop icons land in the persisted `~/Desktop`, and the interactive shell exposes the new aliases.
- Verified on Modal with a 2-minute override: idle advanced while nothing was attached, reset to 0 while an SSE client was connected, and the box shut itself down when the client dropped.

## DevBox Updates - 2026-11-13

### Added

- Added an XFCE desktop over RDP to both Forensics boxes, built on the same xrdp, PipeWire audio, and session startup used by the RDP Desktop Box.
- Added Firefox ESR, netcat, and ping to the Forensics box for browser-based targets and network diagnostics.
- Added WPScan 3.8.28 to the Forensics box, along with the Ruby toolchain its native extensions require.
- Added HTB Starting Point access to both HTB VPN boxes, with a `htb-starting-point` secret (`HTB_SP_OVPN_CONFIG`).

### Changed

- The HTB VPN launchers now ask which network to join: Labs, Starting Point, or both at once.
- Forensics boxes now reset the idle timer on RDP, SSH, or an open OpenCode tab.
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
