# IfcOpenShell as a second adapter (v0 plan)

Status: planned extra. Not the authoritative v0 loader.

## Why a second adapter

CSE's hand-written IFC path exists so the engine can fail closed on units,
missing quantities, and unsupported beam bodies without inheriting a large
C++ world. That personality stays.

IfcOpenShell is the practical way to differential-test the parser and to
obtain solids / openings the v0 adapter does not read. It is an adapter,
not a replacement religion.

## Contract

- Optional extra: `pip install ".[ifcopenshell]"` (package `ifcopenshell`).
- The authoritative loader remains `gat.adapters.ifc`.
- An IfcOpenShell adapter, when written, must:

  1. emit the same `EntityId` / `VarId` identities for quantities both
     loaders can see;
  2. refuse to invent section properties CSE would have marked
     `LENGTH_ONLY`;
  3. expose mesh / solid support as an explicit geometry authority
     (`SWEPT_SOLID` or `INSUFFICIENT`), including voids when present;
  4. never silently skip unsupported entities.

## v0 action

`gat/adapters/ifcopenshell_adapter.py` inventories products when the extra
is installed and otherwise fails closed. It never claims solid or section
authority (`geometry_authority=INSUFFICIENT`). Kernel tests do not require
the extra.
