# Satellite effort v1

Satellite. A cost gate on optional tools. Not a Free Energy Principle.
Not a kernel change. See [kernel-v1.md](kernel-v1.md).

## Job

Decide whether a satellite may open:

```text
expected information on a named REQUEST_EVIDENCE hole
        minus declared cost_nats
        → invoke | defer | refuse
        → kernels unchanged
```

The table is [validation/satellite-effort-v1.json](../validation/satellite-effort-v1.json).
Costs are declared. They are not learned from GPU-seconds or tokens.

## Default

`python_uv` is allowed at cost 0. `rust_ingest`, `cuda_jspt`, `sp1_zkvm`,
and `dense_sigma_rebuild` are `allowed: false`. An INVOKE decision is
permission to open a gate later. The harness still does not run SP1,
CUDA, or Rust ingest.

## Rules

- Unknown satellite → refuse.
- `allowed: false` → refuse.
- Missing finite `cost_nats` → refuse.
- No named hole or no finite expected information → defer.
- `I - c <= 0` → defer.
- Otherwise invoke (policy only).

No finite `sigma` on an instrument is still `REQUEST_EVIDENCE` on the
instrument, not a reason to open CUDA.

## What this must not do

- Change a Beam-B1 verdict, world digest, or acceptance replay.
- Write `Sigma` or a sparse precision.
- Treat an LLM paragraph as a bind.
- Set `sp1.invoked` true.
- Re-rank after a no-op; wait for a new content hash.

Policy rows may be copied onto a causal `policy` event. Prior and result
world digests stay equal.
