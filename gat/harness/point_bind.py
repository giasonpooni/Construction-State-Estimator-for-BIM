"""Layout point bound to an IFC GlobalId.

Satellite. Record-integrity only. Does not condition belief, register a scan, or
turn a display name into an entity. A bind without sigma is refused.

Three checks, in increasing strength, and it matters which is which:

    _looks_like_display_name   lint. Catches ``Opening-1``, misses ``RoomA``.
    ALLOWED_IFC_CLASSES        the class is one the lowerer carries.
    assert_bind_in_world       the Guid, with that class, is in the world.

Only the third establishes identity. The first is a spell-check and is documented
that way so nobody reads the regex as the Guid law.

The schema (``validation/cse-point-bind-v1.schema.json``) leaves the property bag
open, because a bind file carries prose a closed schema would reject. Open also
means an agent can write ``authorized: true``. ``FORBIDDEN_KEYS`` refuses those by
name anywhere in the document rather than dropping them silently, because a
dropped claim leaves its author believing the bind carried it.
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

#: Keys a bind may not carry, anywhere in the document.
#:
#: The schema leaves the bag open, because a bind file legitimately carries prose
#: -- a ``note``, an ``omitted_on_purpose`` block -- and closing it would reject
#: the next honest field. Open means an agent can also write ``authorized: true``
#: or ``traceable: true`` into a bind.
#:
#: Silently dropping those would be safe for this runtime and wrong for the
#: person who wrote them, who would believe the bind carried an authority it
#: never had. These are the words this system treats as meaning something, so a
#: bind that uses one is refused by name rather than quietly ignored. It is not
#: an open-ended blocklist; it is this repository's authority vocabulary.
FORBIDDEN_KEYS = frozenset(
    {
        "authorized",
        "may_authorize",
        "approval",
        "approved",
        "disposition",
        "traceable",
        "traceability",
        "verified",
        "usable_as_field_evidence",
    }
)
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
    """Lint, not an identity check. Do not mistake this for the Guid law.

    It catches the display names this project's own demos use -- ``Opening-1``,
    ``Beam-B1`` -- because pasting one in is the most common way a bind goes
    wrong. It catches nothing else. ``RoomA`` passes. A truncated Guid passes. A
    Guid from a different file passes.

    The identity check is elsewhere and is the real one:

        assert_bind_in_world   the Guid, with that class, is in the compiled world
        ALLOWED_IFC_CLASSES    the class is one the lowerer carries

    A bind that satisfies this function has been spell-checked. A bind that
    satisfies ``assert_bind_in_world`` names something that exists.
    """
    if " " in global_id:
        return True
    prefixes = ("Opening-", "Door-", "Office-", "L3-", "Wall-", "Beam-")
    return global_id.startswith(prefixes)


def _refuse_authority_claims(document: Mapping[str, object], _path: str = "") -> None:
    """Refuse a bind that claims something a bind cannot claim.

    Walks the whole document, not just the top level, because ``payload`` is where
    a second ``claim_scope`` or a stray ``authorized`` would most plausibly be
    written.
    """
    for key, value in document.items():
        here = f"{_path}.{key}" if _path else key
        if key in FORBIDDEN_KEYS:
            raise ValueError(
                f"bind carries {here!r}, which a bind cannot claim: a bind is a "
                "named identity claim at record-integrity-only scope. It does not "
                "authorize, does not assert traceability, and is not field "
                "evidence. Remove the key rather than expecting it to be ignored."
            )
        if _path == "" and key == "claim_scope":
            continue
        if key == "claim_scope":
            raise ValueError(
                f"bind carries a second claim_scope at {here!r}; one record has "
                "one scope, and a nested one reads like a narrower promise than "
                "the root makes"
            )
        if isinstance(value, Mapping):
            _refuse_authority_claims(value, here)


def _hex64(value: object, label: str) -> str:
    """A full 64-character lower-case sha256, not a prefix.

    Every receipt digest shipped in this repository is 64 characters. A short
    prefix appears only in test fixtures, which is not a reason to widen a
    schema: if a prefix is ever wanted it is a differently named field, so a
    reader never has to guess whether a 16-character string is a whole digest or
    the front of one.
    """
    if not isinstance(value, str):
        raise ValueError(f"{label} must be a string")
    text = value.strip()
    if len(text) != 64 or any(ch not in "0123456789abcdef" for ch in text):
        raise ValueError(
            f"{label} must be a full 64-character lower-case sha256, got "
            f"{text[:20]!r} ({len(text)} chars); a prefix is not a digest"
        )
    return text


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
    #: Which slot this bind licenses. Optional, and part of the identity: a bind
    #: licensing Width is a different claim from one licensing Height, so two
    #: binds identical but for quantity must not share a digest.
    quantity: str | None = None
    #: Optional links. Neither closes a hole -- see docs/cse-point-bind-v1.md on
    #: why identity and evidence stay separate -- but both are part of what was
    #: claimed, so both are inside the digest.
    receipt_digest: str | None = None
    world_digest: str | None = None

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
        # These used to be dropped here. The schema declared them and
        # gat.adapters.budget_cite read them, so a bind that was validated and
        # re-serialised lost its quantity -- and the budget seam then refused the
        # very bind bind_point had just accepted.
        if self.quantity:
            payload["quantity"] = self.quantity
        if self.receipt_digest:
            payload["receipt_digest"] = self.receipt_digest
        if self.world_digest:
            payload["world_digest"] = self.world_digest
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
    _refuse_authority_claims(document)
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
                "quantity",
                "receipt_digest",
                "world_digest",
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
    quantity = payload.get("quantity")
    if quantity is not None:
        quantity = _nonempty(quantity, "quantity")
    receipt_digest = payload.get("receipt_digest")
    if receipt_digest is not None:
        receipt_digest = _hex64(receipt_digest, "receipt_digest")
    world_digest = payload.get("world_digest")
    if world_digest is not None:
        world_digest = _hex64(world_digest, "world_digest")
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
        "quantity": quantity,
        "receipt_digest": receipt_digest,
        "world_digest": world_digest,
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
        quantity=quantity,
        receipt_digest=receipt_digest,
        world_digest=world_digest,
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
