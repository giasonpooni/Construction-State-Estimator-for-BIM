# CSE treatise

The public product is the **Construction State Estimator (CSE)**.

| Surface | Name |
|---|---|
| Public name | Construction State Estimator (CSE) |
| GitHub repository | `giasonpooni/Construction-State-Estimator-for-BIM` |
| Python package | `gat-bim` |
| Import / CLI | `gat` |
| Historical engine acronym | GAT (Gaussian Architectural Transformer) |

`gat` is a verified **state transform**, not a learned neural Transformer.
OpenUSD is an optional signed restart carrier. It is not the product.

The public entry point is [`README.md`](../README.md). This file holds the
naming contract and the proof language. Detailed contracts live in the
linked notes below.

## What CSE computes

```text
IFC design intent + physical evidence + criterion
    → posterior architectural belief
    → SATISFIED / VIOLATED / UNRESOLVED
    → ACCEPT / REJECT / REQUEST_EVIDENCE
    → verified state (replayable on a compatible runtime)
```

The v0 kernel is a restricted IFC inventory compiled into a dense
linear-Gaussian belief, with fail-closed decisions on the construction
acceptance slice (opening / prefabrication fit, as-built clearance, beam
certificate → capacity, design-change / RFI preview).

## Proof language

A proof manifest binds one accepted transition and, when present, a
bounded arithmetic guest. It does not prove the building is safe, the
Gaussian update is exact, or the observations were truthful.

A public IFC audit inventories compatibility against the current adapter
scope. It does not authorize a decision.

## Kernel freeze

See [`kernel-v1.md`](kernel-v1.md). A change that alters a disposition,
digest, or replay on the acceptance / beam / RFI slice is a version bump,
not a satellite.

## See also

- [`kernel-v1.md`](kernel-v1.md)
- [`geometry-authority-v1.md`](geometry-authority-v1.md)
- [`sparse-belief-v1.md`](sparse-belief-v1.md)
- [`ifcopenshell-adapter-v0.md`](ifcopenshell-adapter-v0.md)
- [`proof-carrying-state-v1.md`](proof-carrying-state-v1.md)
- [`real-ifc-validation-v1.md`](real-ifc-validation-v1.md)
