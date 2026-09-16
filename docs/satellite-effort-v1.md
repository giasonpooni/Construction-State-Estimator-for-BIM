# Satellite effort v1

Satellite. A cost gate on optional tools. Not a Free Energy Principle.
Not a kernel change. See [kernel-v1.md](kernel-v1.md).

## Authority split

Python can *propose*. Rust can *authorize* anything past the ingest gate.

```text
MCP / LLM / gat.harness.effort   (dry-run, authority=python)
        →  REFUSE rust_ingest / cuda_jspt / sp1_zkvm / dense_sigma_rebuild
        →  may INVOKE only python_uv

rust/effort_gate                 (live, authority=rust-effort-gate)
        →  only place that may INVOKE a rust-gated satellite
        →  still does not run CUDA or SP1 in v1
        →  still does not change Beam-B1
```

An MCP agent that only sees the Python package cannot open CUDA by
flipping a flag in process memory. The live table is the same JSON;
the live *decision* is the Rust binary.

## Job

```text
expected information on a named REQUEST_EVIDENCE hole
        minus declared cost_nats
        → invoke | defer | refuse
        → kernels unchanged
```

Costs are declared. They are not learned from GPU-seconds or tokens.

## Default

`python_uv` is allowed at cost 0 under Python authority. `rust_ingest`,
`cuda_jspt`, `sp1_zkvm`, and `dense_sigma_rebuild` are `allowed: false`
and `authority: rust-effort-gate`. Flipping `allowed` in the JSON does
not make the Python harness an authority for those keys.

## Rules

- Unknown satellite → refuse.
- Caller authority ≠ row authority → refuse (Python vs rust-effort-gate).
- `allowed: false` → refuse.
- Missing finite `cost_nats` → refuse.
- No named hole or no finite expected information → defer.
- `I - c <= 0` → defer.
- Otherwise invoke (policy only; `invoked` stays false in v1).

## Rust gate

```bash
cargo run --manifest-path rust/effort_gate/Cargo.toml -- \
  --table validation/satellite-effort-v1.json \
  --satellite rust_ingest \
  --hole bind.point_to_guid \
  --information-nats 20
```

## What this must not do

- Change a Beam-B1 verdict, world digest, or acceptance replay.
- Write `Sigma` or a sparse precision.
- Treat an LLM paragraph as a bind.
- Set `sp1.invoked` true from either side.
- Let Python countersign a rust-gated INVOKE.
