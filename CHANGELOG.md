## Tmux Styling and Image Builds (2026-10-25)

### Added

- Added the Catppuccin Mocha tmux configuration to every DevBox image, with a top status header, styled window tabs, mouse support, true-color settings, pane borders, and a `Crafted by GoodieHART` marker.

### Fixed

- Moved the local tmux configuration file additions to the final step of each concrete image definition so Modal no longer rejects image builds that continue after `add_local_*` operations.

### Validation

- Test suite: 83 tests passed.

## Cost Tracking

### Added

- Added per-launch cost tracking: every DevBox launch now records resource allocation, wall-clock runtime, and an estimated USD cost to `/data/.cost/sessions/<session>.json` on the persistent volume.
- Added `runtime/cost_tracker.py` (start_session, checkpoint, register_cost_flush, summarize) mirroring the existing atexit backup pattern.
- Added `MODAL_PRICING_VERSION`, `get_pricing()`, and `estimate_cost_usd()` to `devbox_core/config.py` using Modal's published per-second rates.
- Added `show_costs` Modal function and `cost_report` local entrypoint (`modal run devbox.py::cost_report`, optional `--reconcile`).
- Added `tests/test_cost_tracker.py` (9 tests) and a structural packaging test for `runtime.cost_tracker`.

### Changed

- Threaded a `resources` dict and `devbox_type` through all `run_*` shared functions (including RDP, which previously had neither) so cost records distinguish CPU vs GPU boxes.
- Added periodic `checkpoint()` calls in every idle loop for crash safety.

# DevBox Changelog

## Security and GPU Hardening

### Added

- Added separate package denylists for cryptocurrency-mining tools and credential-cracking tools, including `hashcat` and John the Ripper variants.
- Added L40S GPU support to the standard and RDP launchers. L40S is documented with 48 GB of VRAM.
- Added structural coverage for prohibited-package enforcement and GPU launcher wiring.

### Changed

- Image package installation now validates packages before image construction.
- Runtime `extra_packages` validation now runs before `apt-get update`, preventing refused packages from being downloaded.
- Resource configuration dictionaries are explicitly typed to eliminate Modal function argument type errors.
- Standardized tracked text files on LF line endings and added `.gitattributes` enforcement.

### Fixed

- Removed stale REA root exports from persisted shell configuration. Valid REA environment variables remain available, and new SSH sessions no longer emit shell identifier errors.

### Validation

- Verified that `xmrig` and `hashcat=6.2.6-1` are rejected before package installation.
- Verified successful installation and execution of permitted packages in a live Modal container.
- Verified SSH access and denylist availability in a live container.
- Verified that Modal recognizes `L40S` as a valid GPU type; availability remains subject to account billing configuration.
- Test suite: 72 tests passed.
- Static analysis: zero basedpyright errors across the modified Python files.

## REA-Powered OpenCode Boxes

DevBox can now launch an OpenCode environment with Morluto's REA reverse-engineering tools connected from the first session.

### What shipped

- **REA is built into the OpenCode workflow.** OpenCode can discover and use REA through MCP without manual server registration.
- **Pinned toolchain versions.** Node.js and `rea-agents` versions are centralized so image builds and MCP configuration stay aligned.
- **Centralized OpenCode configuration.** The REA MCP definition is shipped with the image and seeded into the user's OpenCode configuration on first start.
- **User configuration is preserved.** Existing OpenCode edits are not overwritten when a container restarts.
- **Persistence now handles stale state safely.** OpenCode directories are repaired when their stored type is wrong, without deleting valid volume data when the home path is temporarily absent.
- **Restore is safer.** Backup archives are validated before `/root` is cleared, and session backups restore to the correct home directory.
- **Image tooling survives restore.** Image-installed OpenCode binaries are excluded from session backups and preserved across relaunches.
- **Validated against live Modal containers.** The OpenCode box was tested through real boot, configuration edits, container termination, respawn, MCP reconnection, and state comparison cycles.

### The user experience

Launch the OpenCode box, place a target under `/data`, and ask OpenCode to investigate it with REA:

```text
Analyze /data/targets/sample-binary with REA.
Identify its imported libraries, configuration parsing path,
and the evidence connecting that path to network behavior.
```

OpenCode starts with the REA MCP server connected, while `/data`, OpenCode state, reports, and user configuration remain available across container sessions.

### Persistence behavior

- Files under `/data` persist through container replacement.
- User state under `/root` is restored through the session backup layer during a clean stop and relaunch.
- Packages installed interactively with `apt` remain image-ephemeral and disappear after replacement.
- Programs intended to be available on every launch should be added to the Modal image definition.

### Verification

The live validation confirmed:

- `rea-agents` 6.5.0 is available in the container (bumped from 6.4.0).
- Native decompilation stack pre-installed on the OpenCode Box: Ghidra 12.1.4 (headless), Eclipse Temurin 21 JDK, jadx, apktool, plus gdb/binwalk/tshark/wabt and binutils.
- REA Android analysis enabled: jadx-headless-mcp 0.7.1 JAR (42.6 MB) downloaded and wired via REA_JADX_MCP_JAR; rea doctor reports jadx configured.
- REA env vars (`JAVA_HOME`, `GHIDRA_INSTALL_DIR`, `REA_GHIDRA_STARTUP_TIMEOUT_MS`, `REA_MCP_MAX_RESPONSE_BYTES`) baked into the image and persisted for SSH shells.
- REA MCP registration + `reverse-engineer-anything` skill installed at image build time via `rea setup --client opencode --yes`.
- Fabricated `REA_EVIDENCE_ROOTS_JSON` / `REA_INVESTIGATION_INPUT_ROOTS_JSON` env vars removed (REA reads absolute paths directly).
- OpenCode Box resources bumped to 2.0 vCPU / 8 GB RAM for Ghidra headroom.
- Live validation: REA's JADX provider analyzed an OSS Simple Calculator APK (771 classes, 396 resources, no permissions).
- Node.js 24 and OpenCode are installed and runnable.
- `opencode mcp list` reports `rea` as connected.
- User edits to the OpenCode MCP configuration survive a kill-and-relaunch cycle.
- Corrupt backup archives no longer trigger destructive cleanup before validation.
