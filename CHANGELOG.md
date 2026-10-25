# DevBox Changelog

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
