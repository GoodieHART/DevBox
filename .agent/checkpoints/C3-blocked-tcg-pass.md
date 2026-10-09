# Checkpoint C3 — E6 PoC-PASS, objective BLOCKED pending human unblock

Checkpoint ID: C3 (resume-from-here)
Timestamp: 2026-09-19T14:00Z
Current branch and commit: windows-vm-rdp @ dc129f9 (+2 uncommitted hunks:
  tests/test_autounattend.py skip guard; windows_vm.py docstring region fix)
Repository/worktree status: 2 modified files (uncommitted, by design —
  commit NOT requested), .agent/ untracked. Nothing else touched.
Infrastructure state: local aarch64/no-KVM; volume windows-vm-data EMPTY;
  all 5 cloud sandboxes verified dead; ~3 min total cloud time this cycle.

## Blocker statement (escalation protocol)

LIVE WINDOWS BOOT IS INFRA-BLOCKED: Modal disables nested KVM virtualization
by default on this account, so no VM sandbox in any tested region exposes
/dev/kvm and the entrypoint correctly aborts before creating any disk.
Evidence: KVM_MISSING ×3 (default, us-west, us-central; all x86_64) +
documented default-off
(https://modal.com/docs/guide/vm-sandboxes: "Nested KVM virtualization is
disabled by default. Please reach out to us").
Escalation threshold met: failure reproduced 3×; 3+ materially different
approaches evaluated (region variance, docs root-cause, TCG substitute);
exact missing capability identified (account-level nested-KVM allowlist).

## Work completed (with evidence)

- Stage 1 COMPLETE: 82 passed, 1 skipped (mtools host-gap, documented).
- KVM gate characterized across 3 regions; wrong docstring example fixed.
- E6 PoC-PASS (temporary/simulated): QEMU 7.2 + OVMF (pflash) + HMP +
  screendump all work under TCG without KVM — 3,072,016-byte PPM retrieved
  (P6 1280×800; blank framebuffer, shell text not claimed). Plumbing proven;
  ONLY acceleration missing. PoC scripts live in /tmp/opencode/ (ephemeral).

## Remaining viable routes (no human needed)

- R-a: wiminfo/ISO path — needs 5-6 GB download, 7.5 GB free: tight, and
  cannot unlock boot without KVM. Only if human wants ISO staged early.
- R-b: commit the 2 hunks + open PR (needs explicit commit approval).
- R-c: draft the Modal support request text (no sending without approval).

## Recommended workaround / smallest external action (NEEDS HUMAN)

Contact Modal (Slack or support@modal.com) requesting nested-KVM
enablement for the account, citing the vm-sandboxes doc line. On KVM_OK,
resume EXACTLY here: re-run probe_kvm (E2 pattern, 5 s), then proceed to
ISO → wiminfo → install → boot per .agent/plan.md ladder stages 4-7.

## Rollback/recovery

- `git stash` reverts hunks; sandboxes all dead; volume empty; /tmp PoC
  scripts are outside the repo and decay with the host.
