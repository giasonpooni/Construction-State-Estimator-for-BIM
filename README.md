# Construction State Estimator (CSE)

Portable **evidence-to-decision** runtime for BIM. CSE compiles IFC design
intent into an auditable architectural belief, conditions that belief on
physical evidence, and returns a fail-closed disposition:

```text
intent + evidence + criterion
    → posterior belief
    → SATISFIED / VIOLATED / UNRESOLVED
    → ACCEPT / REJECT / REQUEST_EVIDENCE
    → verified state (replayable)
```

Public name: **CSE**. Python package: `gat-bim`. Import and CLI: `gat`
(historical engine namespace; not a learned neural Transformer). OpenUSD is
an optional signed restart carrier, not the product.

It is **not** a learned model, a Revit replacement, an FEM solver, or a
digital-twin platform.

Status: experimental v0. License: MIT. Core dependency: `numpy`.

Architecture notes, research questions, and naming live in
[`docs/treatise.md`](docs/treatise.md).
