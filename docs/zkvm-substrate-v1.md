# zkVM substrate v1

SP1 + RISC-V is a second observability layer: the computation was evaluated
as declared. It sits beside the geometry work. It does not replace JSPT,
the ledger, RCI, or exact torus algebra.

Integrity first. Zero-knowledge is optional and off unless a measurement or
coefficient must stay private.

## Ownership

| Object | Host | Guest |
| --- | --- | --- |
| A2-A5, J, JVP, P' = TPT^T | JSPT | never |
| RCI record + digest | instrument / Python | never prove the tape |
| GAT disposition, ledger, F2-1 world | Python kernel | unchanged if SP1 is down |
| Beam-B1 arithmetic line | Python check first | optional SP1 after Beam-B1 |
| Torus / exact lengths | Python algebra | no guest |
| Jacobi vs s, sin s, sinh s | report contract in Python | no guest until the report exists |
| Lyapunov V | future host certificate | only a sampled decrease check |
| Atlas / spectral / factors | views | no guest |

## What a guest may attest

One arithmetic line already bound to a ledger digest. The Beam-B1 guest is
that line: quantized F2-1, PASS iff available >= demand. It does not attest
evidence truth, the Gaussian update, code applicability, or occupancy.

## What a guest may not become

A rewrite of JSPT. A geodesic integrator at every step. A second Kalman.
A factor-graph solver. Firmware on the instrument.

See [sp1-beam-guest-v1.md](sp1-beam-guest-v1.md) for the only implemented guest.
