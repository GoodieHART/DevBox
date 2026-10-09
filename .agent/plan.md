# DevBox Windows-boot R&D — Plan

Goal: reproducible, documented, validated live Windows boot on Modal infra.

## Boot-validation ladder (do not skip a stage without a documented reason)

- [ ] Stage 1 — Static inspection + unit validation (`pytest tests/`)
- [ ] Stage 2 — Image-build validation (`windows_vm_image` builds on Modal)
- [ ] Stage 3 — KVM gate (`probe_kvm` → KVM_OK in a VM sandbox, any region)
- [ ] Stage 4 — ISO acquisition + SHA-256 + volume upload
- [ ] Stage 5 — wiminfo image-index resolution (`modal run probe_wiminfo.py`)
- [ ] Stage 6 — Unattended install orchestration (BOOT_MODE=install → /mark)
- [ ] Stage 7 — Live boot confirmation (BOOT_MODE=boot → RDP reachable)
- [ ] Stage 8 — Reproducibility from clean/documented starting state

## Experiment log

| ID | Objective | Hypothesis | Result |
|----|-----------|------------|--------|
| E1 | pytest suite green on this machine | Code statically sound | pending |
| E2 | Minimal VM-sandbox KVM probe | /dev/kvm present in ≥1 region | pending |

## Rules of engagement

- Smallest, safest, most reversible experiment first.
- No ISO download (>5 GB) without explicit disk-space check.
- No destructive volume ops (`volume rm`), no branch deletes, no deploys
  without explicit human approval.
- Every experiment records: objective, hypothesis, prereqs, exact commands,
  expected vs actual observations, outcome class, conclusion, next action.
