# CSE kernel freeze v1

Status: project convention. Not a feature freeze of bugs.

Public name: Construction State Estimator (CSE). Code namespace: `gat`.

## Why

v0 already answers the original milestone: when one architectural parameter
changes, CSE can transform state and propagate dependents through mandatory
verification. Additional layers are useful only when they change a
disposition, a world digest, or a replay on the construction-acceptance
slice.

## Version bump rule

If a change alters a disposition, digest, or replay on

1. opening / prefabrication fit,
2. as-built clearance,
3. beam certificate → capacity verdict,
4. design-change / RFI preview,

it is a **version bump of the kernel**, not a satellite merge. Document the
changed contract in the validation JSON that pins that slice.

## Kernel

These modules are the product surface. Changes here need tests that speak
the decision contract (`SATISFIED` / `VIOLATED` / `UNRESOLVED` and
`ACCEPT` / `REJECT` / `REQUEST_EVIDENCE`).

- `gat/ir/` — declarative architectural IR
- `gat/gaussian/` — raw belief and full view
- `gat/engine/propagate.py`, `transform.py`, `verify.py`, `executor.py`
- `gat/engine/decision.py`, `gat/engine/active_inference.py`
- `gat/evidence.py`
- `gat/workflows/acceptance.py`, `gat/workflows/change_impact.py`
- `gat/ledger.py`, `gat/state_snapshot.py`
- `gat/adapters/ifc/` — fail-closed quantities, placements, beam status
- `gat/headless.py` — read-only JSON boundary
- `gat/engineering/` — bounded AISC F2-1 beam chain

## Satellites

These may exist, demo, and test, but they are not allowed to block a kernel
release or expand the public claim.

- `gat/geometry/attention.py` — deterministic kernel message passing
- splat PLY export and viewer cosmetics
- Blender sidebar coloring
- SP1 guest packaging and any proving service
- `gat/adapters/external_commitment.py` — bind RCI/torus record digests
- `gat/harness/` — multi-tool experiment bundle; digest binding only
- `gat/harness/effort.py` — satellite cost gate; policy only
- `gat/inspectability/` — space-id readiness fold; not an inspection stamp
- temporal process demos beyond the linear-Gaussian forecast already used
  by the decision slice
- `gat/localize/` — SE(2) MCL on a declared occupancy slice; not pose evidence

## Rule

If a change does not alter a disposition, digest, or replay on the four
slice items above, it belongs on a satellite branch.
