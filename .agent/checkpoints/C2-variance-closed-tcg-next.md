# Checkpoint C2 — variance closed, root cause found, TCG PoC next

Checkpoint ID: C2
Timestamp: 2026-09-19T13:50Z
Current branch and commit: windows-vm-rdp @ dc129f9 (+2 uncommitted hunks, see below)
Repository/worktree status:
  - M tests/test_autounattend.py (+3: mcopy skipif guard)
  - M windows_vm.py (1-word docstring fix: "aws-us-east-1" → "us-east")
  - ?? .agent/ (state.md, plan.md, checkpoints/C1)
  - NOT committed (no commit requested). Safe to commit on request.
Infrastructure state: unchanged (local aarch64/no-KVM; volume EMPTY; Modal 1.5.3).

## Failure record (protocol §1)

| # | Action | Expected | Actual | Repro? | Category |
|---|--------|----------|--------|--------|----------|
| F2a | E2: probe_kvm default region (sb-TRWH23bkot3WzRr0LXaHUz) | KVM_OK | KVM_MISSING, x86_64 | yes | infra: feature disabled by default |
| F2b | E3: probe_kvm us-west (sb-cBLXP3oNussq7FLsbwTPxH) | KVM_OK | KVM_MISSING | yes | same |
| F2c | E3: create with region "us-east-1" | sandbox | InvalidError: regions not supported | yes | config/doc error (fixed) |
| F2d | E5: probe_kvm us-central (sb-KCJr4I4ZnjM1VUKvWSKtqK) | KVM_OK | KVM_MISSING | yes | same as F2a |
| F1 | pytest floppy test (mcopy) | pass | FileNotFoundError (no mtools on host) | yes | env dependency → FIXED via skip guard |

Root cause (E4 docs evidence): Modal "Nested KVM virtualization is disabled
by default. Please reach out to us" (https://modal.com/docs/guide/vm-sandboxes).
KVM_MISSING everywhere is documented default-off behavior, not a config bug.
Valid region forms: us-east/us-west/us-central/… (no "aws-" prefix, no "-1"
suffix). No self-serve KVM flag exists.

## Alternatives considered → ranked (protocol §3-4)

1. Support allowlist request (Slack/support@modal.com) — HIGHEST value: only
   path to real KVM (OSWorld precedent: QEMU+KVM on Modal VM runtime works
   once enabled). Needs HUMAN action → escalated, not executed.
2. E6 TCG plumbing PoC (temporary/simulated): boot OVMF EFI shell under
   `-accel tcg` in an ephemeral sandbox, screenshot via HMP → validates
   QEMU/OVMF/HMP/RPC-screenshot plumbing KVM-independently. Cheap (no ISO),
   reversible, labeled non-production. SELECTED as next experiment.
3. wiminfo probe (KVM-independent but needs 5-6 GB ISO → disk has 7.5 GB
   free). DEFERRED: risky on disk, and still doesn't unlock boot without KVM.
4. Local aarch64 TCG emulation of x86_64 Windows. REJECTED: no qemu
   installed, glacial speed, near-zero evidence value for the Modal target.
5. us-central probe (E5). DONE → closed variance route (3/3 MISSING).
6. Floppy skip guard + docstring fix. DONE → stage 1 green (82+1 skip).

## E1-followup result

Suite: **82 passed, 1 skipped in 6.13s** (was 82+1 failed). Stage 1 COMPLETE.
In-cloud path unaffected (images.py installs mtools in VM image).

## Rejected approaches log

- R1: more regions after us-central → rejected (3 attempts agree + docs say
  default-off account-wide; 4th probe adds no information).
- R2: entrypoint TCG fallback in production code → rejected (design
  explicitly aborts; TCG Windows install would take hours; PoC only).
- R3: ISO download now → rejected (disk tight + KVM gate still closed).

## Next action

E6: TCG OVMF-to-EFI-shell screenshot PoC (ephemeral sandbox, no volume
writes, no repo edits, terminate always). Success = PNG bytes of EFI shell
retrieved via HMP screendump, proving QEMU/HMP/RPC plumbing without KVM.

## Rollback/recovery

- Uncommitted hunks: `git stash` or `git checkout -- <file>` reverts.
- Cloud: all 3 sandboxes verified dead (poll 137/None). Volume untouched.
- No production/shared infra touched at any point.

## Required human approval

- To UNBLOCK real Windows boot: contact Modal (Slack or support@modal.com)
  requesting nested-KVM enablement for the account (cite
  https://modal.com/docs/guide/vm-sandboxes "Nested KVM virtualization is
  disabled by default"). Nothing else unblocks stages 3-7.
- No approval needed for E6 (ephemeral, reversible).
