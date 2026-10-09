# DevBox Windows-boot R&D — State

Last updated: 2026-09-19T13:33Z (cycle 1, assessment)

## Branch reality (reconciled 2026-09-19)

- Task scope says `windows` branch. Reality:
  - `origin/windows` is STALE (11 files: windows_sandbox.py, test_windows.py,
    ascii_art.py era; diverged long before current main).
  - Active Windows VM work is `origin/feature/windows-vm-rdp`
    (14 commits on top of main@fddf297, 2026-08-01).
- Working branch: local `windows-vm-rdp` tracking
  `origin/feature/windows-vm-rdp` @ dc129f9.
- `origin/windows` intentionally NOT checked out (would regress the work).
  Open question: rename/merge strategy for `windows` vs `feature/windows-vm-rdp`
  to be decided with maintainer; no branch deletion without approval.

## What currently works (evidence-backed)

- Unit suite exists: tests/{test_autounattend, test_entrypoint,
  test_idle_monitor, test_install_orchestration, test_rpc_server,
  test_windows_iso, test_windows_vm}.py — NOT yet run on this machine.
- Modal CLI 1.5.3 authenticated (secret/volume/app list succeed).
- `windows-vm-data` volume EXISTS but is EMPTY (`ls --json` → `[]`).
  No ISO, no qcow2 disk, no OVMF vars. Ground zero for install state.

## What currently fails / blockers

- Local: `/dev/kvm` ABSENT, `qemu-system-x86_64` NOT installed, host CPU is
  aarch64 (Neoverse-N1) inside a KVM guest. Local QEMU boot of an x86_64
  Windows ISO is not viable here (would need TCG emulation + ~6 GB ISO +
  only 7.5 GB disk free).
- Modal regular containers: no `/dev/kvm` (documented in README). Windows VM
  design depends on Modal **VM sandbox** (`experimental_options={"vm_runtime":
  True}`) exposing `/dev/kvm` — UNVERIFIED on this account/region.
- ISO acquisition: massgrave.dev download (~5-6 GB) not attempted; disk space
  tight (7.5 GB free). Must be deliberate, not casual.

## Failure boundary

- Ladder stage 1 (static/unit validation): pending, runnable now.
- Ladder stage 2+ (image build, VM-sandbox KVM probe, ISO/wiminfo, install,
  live boot): all blocked behind the KVM-availability question.

## Current hypothesis

H1: The code is statically sound (unit tests pass), and the single decisive
gate for all downstream work is whether a Modal VM sandbox on this account
exposes /dev/kvm. Confidence: medium (code reviewed, infra unverified).

## Next experiment

E1: Run `python -m pytest tests/ -q` on this machine (safe, offline).
E2: KVM probe via minimal Modal VM sandbox (cloud, billable seconds only).
