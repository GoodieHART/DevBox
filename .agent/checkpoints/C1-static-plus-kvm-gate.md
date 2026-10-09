# Checkpoint C1 — static validation + default-region KVM gate

Checkpoint ID: C1
Timestamp: 2026-09-19T13:40Z
Current branch and commit: windows-vm-rdp @ dc129f9 (tracks origin/feature/windows-vm-rdp)
Repository/worktree status: clean except untracked .agent/ (state.md, plan.md).
  NOTE: task scope names the `windows` branch, but origin/windows is a stale
  ancestor (11 files, pre-main era). Active work lives on
  feature/windows-vm-rdp; checked out as local windows-vm-rdp instead.
  No branch deleted, no history rewritten.
Infrastructure state:
  - Local: aarch64 (Neoverse-N1, KVM guest), no /dev/kvm, no qemu, 7.5 GB free.
  - Modal 1.5.3 authenticated. Volume windows-vm-data exists, EMPTY ([]).
Objective: ladder stage 1 (unit validation) + stage 3 gate (KVM in VM sandbox).
Current hypothesis (updated):
  H1-CONFIRMED-PARTIAL: code is statically sound (82/83 green; 1 env failure).
  H2-RESULT: default-region VM sandbox exposes NO /dev/kvm → install/boot
  work is infra-blocked until a KVM-bearing region is found or Modal enables
  nested virt. Confidence: high for default region, low for other regions.
Actions performed (all via subagents, read-only except noted):
  - E1: pytest via `uv run --with pytest --with modal` (ephemeral env, no repo mods).
  - E2: ONE ephemeral VM sandbox (sb-TRWH23bkot3WzRr0LXaHUz), 2 diagnostic
    execs only, terminated via finally; poll()=137 verified dead.
Evidence collected:
  - E1: 82 passed, 1 failed in 6.30s. Failure:
    test_autounattend.py::test_floppy_is_fat12_and_contains_autounattend_xml —
    FileNotFoundError /tmp/mtools-prefix/usr/bin/mcopy (mtools absent).
    38 tests collectible without modal; modal import required by 3 modules.
  - E2: probe_kvm → 'KVM_MISSING' (2.11s); guest arch x86_64; life ~5s;
    cost negligible/invisible. No entrypoint started, no volume writes.
Result: E1 Partially confirmed (1 env failure) / E2 Rejected (default region has no KVM).
Known failures:
  - F1: floppy test needs mtools at /tmp/mtools-prefix (env, not code).
  - F2: /dev/kvm absent in default-region VM sandbox (infra, not code).
Working assumptions:
  - /dev/kvm availability varies by Modal region (per windows_vm region param).
  - Valid region names accepted by modal.Sandbox.create (to verify in E3).
Open questions:
  - Q1: does ANY Modal region expose /dev/kvm to VM sandboxes on this account?
  - Q2: what provisions /tmp/mtools-prefix (CI setup? docs?) for F1?
Next recommended action:
  E3: bounded region-variance probe (≤2 explicit regions, same create+probe+
  terminate pattern, verify C1 sandbox still dead). Then E1-followup (mtools).
Rollback or recovery procedure:
  - No repo files modified; nothing to revert. Cloud: sb-TRWH23bkot3WzRr0LXaHUz
    terminated (poll 137). Volume untouched (still empty).
Required human approval: none for E3/E1-followup (ephemeral, reversible).
  Approval WILL be required before: ISO download (>5 GB), any volume write,
  `modal deploy`, branch renames/deletes.
