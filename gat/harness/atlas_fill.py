"""Allowed fills only: T,c on one object, or a sigma-gated RCI edge."""

from __future__ import annotations

from typing import Mapping

from gat.harness.atlas import (
    OFFICE_WORLD,
    OPENING_WIDTH_M,
    OPENING_WIDTH_MM,
    Atlas,
    Edge,
    Slot,
)
from gat.harness.atlas_cov import bind_rci_observation


def opening_component_atlas(record: Mapping[str, object] | None = None) -> Atlas:
    atlas = Atlas()
    atlas.add_slot(Slot("IfcOpeningElement", "GATOPN0000000000000200", "Width", "m", OFFICE_WORLD))
    atlas.add_slot(Slot("IfcOpeningElement", "GATOPN0000000000000200", "Width", "mm", OFFICE_WORLD))
    atlas.add_edge(Edge(OPENING_WIDTH_M, OPENING_WIDTH_MM, "representation", 1000.0, 0.0, reason="SI m to mm"))
    atlas.add_edge(Edge(OPENING_WIDTH_MM, OPENING_WIDTH_M, "representation", 0.001, 0.0, reason="SI mm to m"))
    if record is not None:
        bind_rci_observation(atlas, record, OPENING_WIDTH_M)
    return atlas
