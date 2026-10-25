# DevBox Roadmap

Planned improvements and future work for DevBox.

## Planned Improvements

- [x] Per-launch cost tracking (estimated USD, persisted to `/data/.cost`)

- [ ] Better shell welcome with oh-my-zsh/starship
- [ ] Startup banner
- [ ] Move into the `/data` directory on login
- [ ] Try to add support for systemd
- [ ] Clear screen on login
- [ ] Allow VMs with software virtualization
- [ ] Allow Dockerfile config importation
- [ ] Automatic install of popular packages and frameworks (e.g. `rust`)
- [ ] Preinstall necessary programs for LLM playgrounds
- [x] Support for multiple SSH key storage with unified access (done: PUBKEYS one-per-line in ssh-public-key secret)
- [ ] Session restore/backup function
- [x] Allow for `tmux` sessions (done: every box starts a detached `devbox` tmux session with 3 windows; printed SSH command bundles `tmux attach -t devbox`)
- [ ] Dynamically select llama-cpp version (currently hardcoded)
- [ ] Setup forensics image with welcome banner
- [ ] Add support for VS Code Server
- [ ] Add `oh-my-opencode` to `assisted_coding_image`
- [ ] Add Ollama models
- [ ] Make significant changes to the backup_utils structure
- [ ] Migrate to Modal Sandbox system
- [x] Add `gdown` to environment settings
- [ ] Predownload symbol files for Volatility
- [ ] Add `croc` for file sharing capabilities
- [x] Add megatools for downloading Mega.nz files
- [ ] Use tldr for welcome messages from installed packages
- [x] Install `p7zip-full` for 7z files
- [ ] Add notes of file verification tools present
- [x] Rearrange file structures (done: devbox_core/runtime/integrations/ui packages)
- [ ] Fix `build_devbox_args`: `gpu_devbox_args` passes `is_rdp=True`, so `GPU_DEVBOX_ARGS` is dead and every GPU box gets the RDP profile (1.5 vCPU / 4096 MB) — the RDP/non-RDP split for GPU boxes currently does nothing
- [ ] Reconcile GPU configuration: `runtime/gpu_utils.py` is 100% unreferenced and non-functional as written (`BASE_GPU_ARGS["secrets"]` is a *string* of Python source, not a `Secret` object). Either delete it, or make it the single source of truth for GPU type + resources + menu names — the live path is currently split across `config.py` + `devbox.py` + `ui/launcher_menu.py` + `shared_runtime.py`
- [ ] Add per-GPU resource profiles: all four GPUs share one profile today, so L40S (48 GB VRAM) gets the same 1.5 vCPU / 4096 MB host RAM as a T4. The richer per-GPU model only exists in the dead `gpu_utils` module
- [ ] Make `runtime/shared_runtime.py` write its REA env block to a dedicated `/root/.config/devbox/env.sh` (fully rewritten each launch) instead of appending to the persisted `/root/.bashrc` — the current marker check prevents duplicates but can never remove a stale block
