# IfcOpenShell as a second adapter (v0)

Status: inventory extra. Not the authoritative loader. Not a mesh authority.

## Why a second adapter

GAT's hand-written IFC path exists so the engine can fail closed on units,
missing quantities, and unsupported beam bodies without inheriting a large
C++ world. That personality stays.

IfcOpenShell is the practical way to differential-test identities and to
obtain solids / openings the v0 adapter does not read. It is an adapter,
not a replacement religion.

## Contract

- Optional extra: `pip install ".[ifcopenshell]"` (package `ifcopenshell`).
- The authoritative loader remains `gat.adapters.ifc`.
- Geometry authority on this adapter is always `INSUFFICIENT`.
- Triangles from `ifcopenshell.geom` are not `SWEPT_SOLID`.
- A missing GlobalId is recorded in `omitted`, never skipped as "no product".

## What v0 does

`inventory_identities_cse` and `inventory_with_ifcopenshell` collect:

- GlobalIds for storey / wall / space / opening / door / beam
- QTO quantity names attached via `IfcRelDefinesByProperties`
- representation type *labels* on the IfcOpenShell side only

`diff_identity_inventories` fails a test when Guid sets or QTO names
diverge on the shipped demo files.

It does not:

- tessellate or return BRep
- invent `I`, `W`, or `Sx` from a mesh
- write `Sigma` or a world digest
- close clearance acceptance

## Next (not this commit)

Scoped geometry iterator into the disposable OpenUSD `View` / Bonsai
draw, still `INSUFFICIENT` unless the IFC item is `IfcExtrudedAreaSolid`
*and* the CSE beam deriver already said `COMPLETE`.
