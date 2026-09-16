"""Layout point bound to an IFC GlobalId.

Satellite. Record-integrity only. Does not condition belief, register a
scan, or turn a display name into an entity. A bind without sigma is refused.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import math
from pathlib import Path
from typing import Mapping

from gat.adapters.external_commitment import canonical_digest
from gat.engine.executor import World


BIND_SCHEMA = "cse-point-bind-v1"
CLAIM_SCOPE = "record-integrity-only"
ALLOWED_IFC_CLASSES = frozenset(
    {
        "IfcOpeningElement",
        "IfcDoor",
        "IfcWall",
        "IfcWallStandardCase",
        "IfcSpace",
        "IfcBeam",
    }
)


def _nonempty(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")
    return value.strip()


def _looks_like_display_name(global_id: str) -> bool:
    if " " in global_id:
        return True
    prefixes = ("Opening-", "Door-", "Office-", "L3-", "Wall-", "Beam-")
    return global_id.startswith(prefixes)


def _positive(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a positive number")
    number = float(value)
    if not math.isfinite(number) or number <= 0.0:
        raise ValueError(f"{label} must be a positive finite number")
    return number


@dataclass(frozen=True)
class PointBind:
    point_id: str
    global_id: str
    ifc_class: str
    name: str | None
    space_id: str | None
    frame_id: str
    epoch: str
    sigma: float
    sigma_unit: str
    sigma_reason: str
    digest: str

    def to_document(self) -> dict[str, object]:
        payload = {
            "point_id": self.point_id,
            "ifc_class": self.ifc_class,
            "global_id": self.global_id,
            "frame_id": self.frame_id,
            "epoch": self.epoch,
            "sigma": self.sigma,
            "sigma_unit": self.sigma_unit,
            "sigma_reason": self.sigma_reason,
        }
        if self.name:
            payload["name"] = self.name
        if self.space_id:
            payload["space_id"] = self.space_id
        return {
            "schema": BIND_SCHEMA,
            "claim_scope": CLAIM_SCOPE,
            "point_id": self.point_id,
            "global_id": self.global_id,
            "ifc_class": self.ifc_class,
            "payload": payload,
            "digest": self.digest,
        }


def bind_point(document: Mapping[str, object]) -> PointBind:
    """Validate a point-to-Guid bind. Does not observe a quantity."""
    schema = document.get("schema")
    if schema != BIND_SCHEMA:
        raise ValueError(f"unsupported bind schema {schema!r}")
    if document.get("claim_scope") != CLAIM_SCOPE:
        raise ValueError("claim_scope must be record-integrity-only")
    if document.get("global_id") is None and document.get("xyz") is not None:
        raise ValueError("coordinates without an IfcGuid are not a bind")
    payload = document.get("payload")
    if not isinstance(payload, Mapping):
        payload = {
            key: document[key]
            for key in (
                "point_id",
                "global_id",
                "ifc_class",
                "name",
                "space_id",
                "frame_id",
                "epoch",
                "sigma",
                "sigma_unit",
                "sigma_reason",
            )
            if key in document
        }
    point_id = _nonempty(payload.get("point_id"), "point_id")
    global_id = _nonempty(payload.get("global_id"), "global_id")
    ifc_class = _nonempty(payload.get("ifc_class"), "ifc_class")
    if ifc_class not in ALLOWED_IFC_CLASSES:
        raise ValueError(f"ifc_class {ifc_class!r} is not a bindable entity class")
    if _looks_like_display_name(global_id):
        raise ValueError("global_id must be an Ifc GlobalId, not a display name")
    name = payload.get("name")
    if name is not None:
        name = _nonempty(name, "name")
    space_id = payload.get("space_id")
    if space_id is not None:
        space_id = _nonempty(space_id, "space_id")
    frame_id = _nonempty(payload.get("frame_id"), "frame_id")
    epoch = _nonempty(payload.get("epoch"), "epoch")
    sigma = _positive(payload.get("sigma"), "sigma")
    sigma_unit = _nonempty(payload.get("sigma_unit"), "sigma_unit")
    sigma_reason = _nonempty(payload.get("sigma_reason"), "sigma_reason")
    digest_payload = {
        "point_id": point_id,
        "ifc_class": ifc_class,
        "global_id": global_id,
        "name": name,
        "space_id": space_id,
        "frame_id": frame_id,
        "epoch": epoch,
        "sigma": sigma,
        "sigma_unit": sigma_unit,
        "sigma_reason": sigma_reason,
    }
    digest = canonical_digest(digest_payload)
    declared = document.get("digest")
    if declared is not None and declared != digest:
        raise ValueError("digest does not match bind payload")
    return PointBind(
        point_id=point_id,
        global_id=global_id,
        ifc_class=ifc_class,
        name=name if isinstance(name, str) else None,
        space_id=space_id if isinstance(space_id, str) else None,
        frame_id=frame_id,
        epoch=epoch,
        sigma=sigma,
        sigma_unit=sigma_unit,
        sigma_reason=sigma_reason,
        digest=digest,
    )


def bind_point_file(path: str | Path) -> PointBind:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("bind file must be a JSON object")
    return bind_point(raw)


def assert_bind_in_world(bind: PointBind, world: World) -> None:
    """Fail closed if the Guid is not in the compiled world."""
    for entity in world.module.entities.values():
        if entity.id.global_id == bind.global_id and entity.id.ifc_class == bind.ifc_class:
            return
    raise ValueError(
        f"bind {bind.point_id} names {bind.ifc_class}:{bind.global_id} "
        "which is not in the compiled world"
    )
