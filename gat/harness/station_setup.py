"""Named total-station setup. Record-integrity only.

Closes inspectability code frame.station_setup. Not a JSPT chart.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Mapping

from gat.adapters.external_commitment import canonical_digest


SETUP_SCHEMA = "cse-station-setup-v1"
CLAIM_SCOPE = "record-integrity-only"


def _nonempty(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")
    return value.strip()


@dataclass(frozen=True)
class StationSetup:
    setup_id: str
    occupied_id: str
    backsight_id: str
    space_id: str | None
    prism_height_m: float | None
    digest: str

    def to_document(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "setup_id": self.setup_id,
            "occupied_id": self.occupied_id,
            "backsight_id": self.backsight_id,
        }
        if self.space_id:
            payload["space_id"] = self.space_id
        if self.prism_height_m is not None:
            payload["prism_height_m"] = self.prism_height_m
        return {
            "schema": SETUP_SCHEMA,
            "claim_scope": CLAIM_SCOPE,
            "payload": payload,
            "digest": self.digest,
        }


def bind_station_setup(document: Mapping[str, object]) -> StationSetup:
    if document.get("schema") != SETUP_SCHEMA:
        raise ValueError(f"unsupported setup schema {document.get('schema')!r}")
    if document.get("claim_scope") != CLAIM_SCOPE:
        raise ValueError("claim_scope must be record-integrity-only")
    payload = document.get("payload")
    if not isinstance(payload, Mapping):
        payload = document
    setup_id = _nonempty(payload.get("setup_id"), "setup_id")
    occupied_id = _nonempty(payload.get("occupied_id"), "occupied_id")
    backsight_id = _nonempty(payload.get("backsight_id"), "backsight_id")
    if occupied_id == backsight_id:
        raise ValueError("occupied and backsight must be distinct")
    space_id = payload.get("space_id")
    if space_id is not None:
        space_id = _nonempty(space_id, "space_id")
    prism = payload.get("prism_height_m")
    if prism is not None:
        if not isinstance(prism, (int, float)) or isinstance(prism, bool):
            raise ValueError("prism_height_m must be a number")
        prism = float(prism)
        if prism <= 0.0:
            raise ValueError("prism_height_m must be positive")
    digest_payload = {
        "setup_id": setup_id,
        "occupied_id": occupied_id,
        "backsight_id": backsight_id,
        "space_id": space_id,
        "prism_height_m": prism,
    }
    digest = canonical_digest(digest_payload)
    declared = document.get("digest")
    if declared is not None and declared != digest:
        raise ValueError("digest does not match setup payload")
    return StationSetup(
        setup_id=setup_id,
        occupied_id=occupied_id,
        backsight_id=backsight_id,
        space_id=space_id if isinstance(space_id, str) else None,
        prism_height_m=prism,
        digest=digest,
    )


def bind_station_setup_file(path: str | Path) -> StationSetup:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("setup file must be a JSON object")
    return bind_station_setup(raw)
