"""Walkable slot atlas. Representation edges carry T, c. Observation edges need sigma.

Satellite. Not an estimator. Not a JSPT fork.
x' = T x + c is declared here; P' = T P T^T stays in JSPT.
"""

from __future__ import annotations

from dataclasses import dataclass
import math


def slot_id(ifc_class: str, global_id: str, quantity: str, unit: str) -> str:
    return f"{ifc_class}:{global_id}.{quantity}[{unit}]"


@dataclass(frozen=True)
class Slot:
    ifc_class: str
    global_id: str
    quantity: str
    unit: str
    world: str

    @property
    def id(self) -> str:
        return slot_id(self.ifc_class, self.global_id, self.quantity, self.unit)

    def entity_id(self) -> str:
        return f"{self.ifc_class}:{self.global_id}"


@dataclass(frozen=True)
class Edge:
    source: str
    target: str
    kind: str
    scale: float
    offset: float
    observation_id: str | None = None
    sigma: float | None = None
    sigma_unit: str | None = None
    reason: str = ""

    def apply(self, value: float) -> float:
        return self.scale * value + self.offset


class AtlasError(ValueError):
    pass


def _finite(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AtlasError(f"{label} must be a number")
    number = float(value)
    if not math.isfinite(number):
        raise AtlasError(f"{label} must be finite")
    return number


class Atlas:
    def __init__(self) -> None:
        self.slots: dict[str, Slot] = {}
        self.edges: list[Edge] = []

    def add_slot(self, slot: Slot) -> Slot:
        existing = self.slots.get(slot.id)
        if existing is not None and existing.world != slot.world:
            # slot_id() is built from ifc_class, global_id, quantity and unit --
            # the world is deliberately NOT in it, so the same quantity in two
            # worlds collapses to one dict key. Before this guard, re-declaring a
            # slot in another world silently replaced it, and every edge already
            # pointing at that id had its world changed underneath it. add_edge
            # validates worlds when the edge is inserted and never again, so a
            # redeclaration could turn a validated same-world edge into a
            # cross-world one retroactively -- producing a document that asserts
            # "every edge stays inside one world" while carrying an edge that
            # does not. Found by probing the gate rather than by a failing test,
            # which is why the guard is here and not in add_edge.
            raise AtlasError(
                f"slot refused: {slot.id} is already declared in world "
                f"{existing.world!r} and cannot be re-declared in "
                f"{slot.world!r}. A slot's world is fixed once declared, because "
                "edges are validated against it. Relate the two worlds by citing "
                "them side by side (atlas_cov.cite_disposition_worlds)."
            )
        self.slots[slot.id] = slot
        return slot

    def add_edge(self, edge: Edge) -> Edge:
        if edge.source not in self.slots or edge.target not in self.slots:
            raise AtlasError("edge endpoints must be atlas slots")
        if edge.kind not in {"representation", "observation", "coupling"}:
            raise AtlasError("edge kind must be representation, observation, or coupling")
        source_world = self.slots[edge.source].world
        target_world = self.slots[edge.target].world
        if source_world != target_world:
            # identity_gap states the rule in prose -- "share Guid; cite digest;
            # do not equate worlds" -- and forced_common_world stays false. An
            # atlas edge is transport: it carries a value from one coordinate to
            # another and so asserts they measure one thing. No kind of edge may
            # do that across worlds, a coupling with a written reason least of
            # all, because a reason is prose and this is the one claim the
            # system exists to refuse. Relate two worlds by citing them side by
            # side (atlas_cov.cite_disposition_worlds), never by transporting
            # between them.
            raise AtlasError(
                f"edge refused: {edge.source} is in world {source_world!r} and "
                f"{edge.target} is in world {target_world!r}; worlds are cited, "
                "not transported"
            )
        _finite(edge.scale, "scale")
        _finite(edge.offset, "offset")
        if edge.kind == "observation":
            if edge.sigma is None or edge.sigma <= 0.0:
                raise AtlasError("observation edge refused: declared sigma required")
            if not edge.observation_id:
                raise AtlasError("observation edge refused: observation_id required")
            if not edge.sigma_unit:
                raise AtlasError("observation edge refused: sigma_unit required")
        if edge.kind == "coupling" and not edge.reason:
            raise AtlasError("coupling edge refused: reason required")
        self.edges.append(edge)
        return edge

    def worlds(self) -> tuple[str, ...]:
        """Every world this atlas has slots in, in sorted order."""
        return tuple(sorted({slot.world for slot in self.slots.values()}))

    def walk(self, source: str, target: str, value: float) -> dict[str, object]:
        if source == target:
            return {"value": float(value), "path": [source], "kind": "identity"}
        for edge in self.edges:
            if edge.source == source and edge.target == target:
                return {
                    "value": edge.apply(float(value)),
                    "path": [source, target],
                    "kind": edge.kind,
                    "scale": edge.scale,
                    "offset": edge.offset,
                    "observation_id": edge.observation_id,
                    "sigma": edge.sigma,
                }
        raise AtlasError(f"no declared edge {source} -> {target}")

    def to_document(self) -> dict[str, object]:
        return {
            "schema": "cse-atlas-v1",
            "claim_scope": "record-integrity-only",
            "law": "x' = T x + c; covariance transform remains JSPT",
            "worlds": list(self.worlds()),
            "world_rule": "every edge stays inside one world; worlds are cited, not transported",
            "slots": [
                {
                    "id": slot.id,
                    "entity_id": slot.entity_id(),
                    "quantity": slot.quantity,
                    "unit": slot.unit,
                    "world": slot.world,
                }
                for slot in self.slots.values()
            ],
            "edges": [
                {
                    "source": edge.source,
                    "target": edge.target,
                    "kind": edge.kind,
                    "T": edge.scale,
                    "c": edge.offset,
                    "observation_id": edge.observation_id,
                    "sigma": edge.sigma,
                    "sigma_unit": edge.sigma_unit,
                    "reason": edge.reason,
                }
                for edge in self.edges
            ],
        }


OFFICE_WORLD = "office-a-ifc"
BEAM_WORLD = "beam-b1-ifc"
TANK_WORLD = "industrial-tank-t1"

OPENING_WIDTH_M = slot_id("IfcOpeningElement", "GATOPN0000000000000200", "Width", "m")
OPENING_WIDTH_MM = slot_id("IfcOpeningElement", "GATOPN0000000000000200", "Width", "mm")
OPENING_HEIGHT_M = slot_id("IfcOpeningElement", "GATOPN0000000000000200", "Height", "m")
DOOR_WIDTH_M = slot_id("IfcDoor", "GATDOR0000000000000210", "Width", "m")
TANK_LEVEL_M = slot_id("IndustrialSlot", "TANK-T1", "Level", "m")
BEAM_B1 = slot_id("IfcBeam", "GATBEAMELEMENT00000100", "Capacity", "N*m")


def office_a_atlas() -> Atlas:
    atlas = Atlas()
    atlas.add_slot(Slot("IfcOpeningElement", "GATOPN0000000000000200", "Width", "m", OFFICE_WORLD))
    atlas.add_slot(Slot("IfcOpeningElement", "GATOPN0000000000000200", "Width", "mm", OFFICE_WORLD))
    atlas.add_slot(Slot("IfcOpeningElement", "GATOPN0000000000000200", "Height", "m", OFFICE_WORLD))
    atlas.add_slot(Slot("IfcDoor", "GATDOR0000000000000210", "Width", "m", OFFICE_WORLD))
    atlas.add_slot(Slot("IndustrialSlot", "TANK-T1", "Level", "m", TANK_WORLD))
    atlas.add_slot(Slot("IfcBeam", "GATBEAMELEMENT00000100", "Capacity", "N*m", BEAM_WORLD))
    atlas.add_edge(
        Edge(
            OPENING_WIDTH_M,
            OPENING_WIDTH_MM,
            "representation",
            1000.0,
            0.0,
            reason="SI metre to millimetre. Same object.",
        )
    )
    atlas.add_edge(
        Edge(
            OPENING_WIDTH_MM,
            OPENING_WIDTH_M,
            "representation",
            0.001,
            0.0,
            reason="millimetre to SI metre. Same object.",
        )
    )
    return atlas


def identity_gap(
    *,
    office_live_digest: str,
    beam_live_digest: str,
    beam_prior_digest: str,
    beam_revised_digest: str,
    beam_global_id: str = "GATBEAMELEMENT00000100",
) -> dict[str, object]:
    """Guid is shared. Worlds are not merged."""
    same_live = office_live_digest == beam_live_digest
    pin_is_live = beam_live_digest in {beam_prior_digest, beam_revised_digest}
    return {
        "schema": "cse-identity-gap-v1",
        "claim_scope": "record-integrity-only",
        "beam_entity_id": f"IfcBeam:{beam_global_id}",
        "office_live_world_digest": office_live_digest,
        "beam_live_world_digest": beam_live_digest,
        "beam_prior_world_digest": beam_prior_digest,
        "beam_revised_world_digest": beam_revised_digest,
        "office_contains_beam": False,
        "forced_common_world": False,
        "live_worlds_equal": same_live,
        "beam_pin_is_live_ifc": pin_is_live,
        "identity_rule": "share Guid; cite digest; do not equate worlds",
        "refusals": [
            "Office-A IFC is not the Beam-B1 certificate world.",
            "A lattice edge is not a covariance update.",
            "Equal names do not imply equal world_digest.",
        ],
    }
