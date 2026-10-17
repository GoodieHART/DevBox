# DevBox Changelog

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
