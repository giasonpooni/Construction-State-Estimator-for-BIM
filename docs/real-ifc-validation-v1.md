# Real-IFC validation v1

## What a public IFC audit is not

`gat audit` / `gat-ifc-audit` inventories whether a file is compatible with
the current CSE adapter. It is not a decision, not a partial import, and not
an authorization to ACCEPT a construction case.

An audit never:

- changes the IFC source;
- synthesizes missing quantities;
- commits a partial world;
- authorizes `ACCEPT` / `REJECT` / `REQUEST_EVIDENCE`;
- treats `pipeline_ready` as coverage of an as-built or structural scope;
- upgrades `GAUSSIAN_PROXY` clash, `LENGTH_ONLY` beams, or
  `NEEDS_GEOMETRY_DERIVATION` products into geometry authority.

`audit_authorizes_decisions` is false on every measured public-model
baseline. A later acceptance request must name a decision scope and prove
that every relevant entity and dependency is covered. Partial ingestion may
never produce `ACCEPT`.

The tables below are compatibility measurements, not field validation.

Status: implemented audit boundary, measured baseline, SI length-unit
normalization, bounded beam geometry derivation, and strict material-certificate
ingestion, and a bounded independently validated design-code calculation. The
next phase is headless and Blender/Bonsai exposure of that validated chain.

## Why this exists

CSE's authoritative IFC loader is fail-closed. That protects a decision from
being computed over an incomplete state, but it also means an unfamiliar file
used to stop at its first incompatibility. `gat audit` is the non-mutating
discovery boundary: it parses the file, inventories every product in the
adapter's declared scope, and then attempts the unchanged
lower -> compile -> verify pipeline.

An audit is not a partial importer. In particular:

- it never changes the IFC source;
- it never synthesizes missing quantities;
- it never commits a partial world;
- it never authorizes a decision; and
- skipped or unsupported entities remain explicit.

Use it with either installed entry point:

```console
gat audit model.ifc --text
gat audit model.ifc --output audit.json
gat-ifc-audit model.ifc --compact
```

Exit code `0` means the current supported scope completed the full pipeline,
`2` means the report was produced but the pipeline is blocked, and `3` means
the source or output could not be read or written.

## Report contract

`gat-ifc-audit-v1` binds its result to the exact source SHA-256 and byte size.
See the remainder of this file on `main` before this edit for the measured
baselines, corpus reproduction commands, and adapter-hardening order. The
audit still cannot authorize decisions.
