"""Optional IfcOpenShell adapter — second loader, not the authority.

The hand-written ``gat.adapters.ifc`` path remains fail-closed and
authoritative. This module exists so a later implementation can
differential-test quantities and pull solids/voids CSE does not yet read.

v0 only answers: is IfcOpenShell installed, and if so can it open the file
without claiming section or clearance authority.
"""

from __future__ import annotations

from dataclasses import dataclass


class IfcOpenShellAdapterError(RuntimeError):
    """Raised when the optional adapter cannot be used honestly."""


def ifcopenshell_available() -> bool:
    try:
        import ifcopenshell  # noqa: F401
    except ImportError:
        return False
    return True


@dataclass(frozen=True)
class IfcOpenShellInventory:
    path: str
    schema: str
    product_count: int
    beam_global_ids: tuple[str, ...]
    geometry_authority: str = "INSUFFICIENT"


def inventory_with_ifcopenshell(path: str) -> IfcOpenShellInventory:
    """Open a file for identity inventory only. Never invent section properties."""
    if not ifcopenshell_available():
        raise IfcOpenShellAdapterError(
            "ifcopenshell is not installed; pip install '.[ifcopenshell]'"
        )
    import ifcopenshell

    model = ifcopenshell.open(path)
    beams = tuple(
        beam.GlobalId
        for beam in model.by_type("IfcBeam")
        if getattr(beam, "GlobalId", None)
    )
    products = model.by_type("IfcProduct")
    return IfcOpenShellInventory(
        path=path,
        schema=str(model.schema),
        product_count=len(products),
        beam_global_ids=beams,
        geometry_authority="INSUFFICIENT",
    )
