# SP1 guest claim v0

Satellite. Parallel to geometry, not a replacement. Default refuse.
See [satellite-effort-v1.md](satellite-effort-v1.md).

## Split

```text
geometry / morphisms     maps between plant spaces; what measurements reconstruct
zkVM guest               maps from a program trace to a succinct integrity claim
```

RISC-V is the guest ISA because it is small enough to arithmetize and is
already a plausible OT target. SP1 is one concrete zkVM, not the kernel.
Proving is orders of magnitude slower than native RISC-V. Certificates
attach to kernels, not to a CFD timestep or to Beam-B1 replay.

Zero-knowledge is optional. Industrial certificates want *integrity*:
the declared map was evaluated. Hiding measurements or coefficients is
an extra flag, not the default.

## What may be claimed

| Object | Guest claim (public in, public out) |
|---|---|
| JSPT J / JVP | `(x, dx, J_digest) → J dx` matches the declared recurrence |
| Geodesic + Jacobi | same tableau stepped the flow and the variational equation |
| PLSR `V` | `V` decreases on the published discrete trajectory |
| FSRT reconstruct | published state is a critical point of the declared residual |
| CSE observe | posterior mean is the ObserveQuantity of `(y, R, prior)` |

The guest does **not** claim presentability, occupancy, or IBC. Those
stay in the present-process packet. A valid proof cannot close
`bind.point_to_guid` or flip `may_authorize`.

## Public tape

```text
program_id || input_digest || output_digest || claim_kind
```

`input_digest` covers the declared model bytes and the published
measurements. Private inputs, if any, are not in that digest. The
verifier checks the proof against the public tape. It does not re-run
Python.

## Authority

- Python / MCP: dry-run only. Cannot set `sp1.invoked`.
- `rust-effort-gate`: only live INVOKE. Table row `sp1_zkvm` is
  `allowed: false`.
- Guest binary, if it exists later, lives under `rust/sp1_guest/` and
  cannot import `gat` world digests as trusted constants.
- CI: `workflow_dispatch` only. A red 45-minute job must not land on
  `main` by default.

## Refusals

- Prove the whole BIM session or NOAA month.
- Treat a proof as an `Observe*`.
- SNARK-wrap as authorization.
- "zk digital twin."
- Changing Beam-B1, opening-fit replay, or a world digest because a
  guest exists.

v0 ships the claim JSON and this page. It does not ship a prover.
