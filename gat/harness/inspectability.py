"""Fold on-disk receipts into an inspectability index.

Satellite. Read-only. Does not condition belief, recompute Beam-B1,
or treat a bound digest as a point-to-IfcGuid bind.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Iterable, Mapping

from gat.adapters.external_commitment import CLAIM_SCOPE, canonical_digest
from gat.harness.bundle import load_json

INDEX_FORMAT = "cse-inspectability-index-v1"
BIND_SCHEMA = "cse-point-bind-v1"
_NON_CLAIMS = (
    "not an occupancy permit",
    "not a replacement for a human inspector",
    "pace thesis is not a measured result",
)

TICKET_INSTRUMENT = {
    "bind.point_to_guid": "total-station-or-layout",
    "evidence.as_built": "calibrated-observation",
    "evidence.scan_gmm": "terrestrial-scan",
    "frame.station_setup": "total-station",
    "accessory.prism_height": "prism-pole",
    "frame.level_loop": "digital-level",
    "identity.space": "ifc-space-entity",
    "calibration.declared": "declared-calibration",
    "case.missing": "case-receipt",
}


@dataclass(frozen=True)
class InspectabilityIndex:
    document: dict[str, object]

    @property
    def inspectability(self) -> str:
        return str(self.document["inspectability"])

    def write(self, path: str | Path) -> Path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(self.document, indent=2, sort_keys=True, allow_nan=False)
            + "\n",
            encoding="utf-8",
        )
        return target


@dataclass(frozen=True)
class CrewTicket:
    space_id: str
    code: str
    asks_for: str
    instrument_class: str
    presentable: bool = False


def _as_dict(raw: object) -> dict[str, object] | None:
    return raw if isinstance(raw, dict) else None


def _space_from(document: Mapping[str, object] | None) -> dict[str, object]:
    if document is None:
        return {}
    ref = _as_dict(document.get("space_ref")) or {}
    space_id = document.get("space_id")
    ifc_class = ref.get("ifc_class")
    global_id = ref.get("global_id")
    name = ref.get("name")
    if ifc_class is None and document.get("ifc_class") == "IfcSpace":
        ifc_class = "IfcSpace"
        if global_id is None:
            global_id = document.get("global_id")
        if name is None:
            name = document.get("name")
    if ifc_class not in (None, "IfcSpace"):
        ifc_class = None
        global_id = None
        name = None
    if space_id is None and ifc_class == "IfcSpace" and isinstance(global_id, str) and global_id:
        space_id = f"space:ifc:{global_id}"
    out: dict[str, object] = {}
    if isinstance(space_id, str) and space_id:
        out["space_id"] = space_id
    if ifc_class == "IfcSpace" and (global_id or name):
        out["space_ref"] = {
            "ifc_class": ifc_class,
            "global_id": global_id,
            "name": name,
        }
    for key in ("project_id", "building_id"):
        value = document.get(key)
        if isinstance(value, str) and value:
            out[key] = value
    return out


def _merge_space(*documents: Mapping[str, object] | None) -> dict[str, object]:
    merged: dict[str, object] = {}
    for document in documents:
        piece = _space_from(document)
        if not piece:
            continue
        ref = _as_dict(merged.get("space_ref")) or {}
        incoming = _as_dict(piece.get("space_ref")) or {}
        if incoming.get("ifc_class") == "IfcSpace":
            ref = {**ref, **{k: v for k, v in incoming.items() if v not in (None, "")}}
        merged.update({k: v for k, v in piece.items() if k != "space_ref"})
        if ref:
            merged["space_ref"] = ref
    return merged


def _case_row(document: Mapping[str, object], source: str | None) -> dict[str, object]:
    disposition = document.get("disposition") or document.get("verdict")
    if disposition is None:
        payload = _as_dict(document.get("payload"))
        if payload is not None:
            disposition = payload.get("disposition") or payload.get("verdict")
    return {
        "case_id": document.get("case_id") or document.get("request_id"),
        "workflow": document.get("workflow"),
        "disposition": disposition,
        "source": source,
    }


def _is_bind(document: Mapping[str, object]) -> bool:
    if document.get("schema") != BIND_SCHEMA:
        return False
    point_id = document.get("point_id")
    global_id = document.get("global_id")
    return (
        isinstance(point_id, str)
        and bool(point_id.strip())
        and isinstance(global_id, str)
        and bool(global_id.strip())
    )


def _has_as_built(document: Mapping[str, object]) -> bool:
    digest = document.get("evidence_digest")
    return isinstance(digest, str) and len(digest) >= 16


def _has_space_identity(space: Mapping[str, object]) -> bool:
    ref = _as_dict(space.get("space_ref")) or {}
    global_id = ref.get("global_id")
    ifc_class = ref.get("ifc_class")
    return ifc_class == "IfcSpace" and isinstance(global_id, str) and bool(global_id)


def fold_inspectability(
    *,
    space: Mapping[str, object] | None = None,
    receipts: Iterable[tuple[Mapping[str, object], str | None]] = (),
    commitments: Iterable[tuple[Mapping[str, object], str | None]] = (),
    binds: Iterable[tuple[Mapping[str, object], str | None]] = (),
    extra_requests: Iterable[Mapping[str, str]] = (),
) -> InspectabilityIndex:
    receipt_list = list(receipts)
    commitment_list = list(commitments)
    bind_list = list(binds)
    space_doc = _merge_space(
        space,
        *[document for document, _source in receipt_list],
        *[document for document, _source in bind_list],
    )
    cases = [_case_row(document, source) for document, source in receipt_list]
    cited = []
    for document, source in commitment_list:
        cited.append(
            {
                "role": document.get("kind") or "commitment",
                "schema": document.get("schema"),
                "ref": source,
                "digest": document.get("digest"),
                "claim_scope": document.get("claim_scope") or CLAIM_SCOPE,
            }
        )
    bind_found = any(_is_bind(document) for document, _source in bind_list)
    as_built_found = any(_has_as_built(document) for document, _source in receipt_list)
    requests: list[dict[str, str]] = []
    if not _has_space_identity(space_doc):
        requests.append(
            {
                "code": "identity.space",
                "asks_for": "IfcSpace GlobalId for this project space",
            }
        )
    if not bind_found:
        requests.append(
            {
                "code": "bind.point_to_guid",
                "asks_for": "layout point bound to an IfcGuid",
            }
        )
    if not as_built_found:
        requests.append(
            {
                "code": "evidence.as_built",
                "asks_for": "ledger-bound ObserveLinearized or ObserveQuantity digest",
            }
        )
    for extra in extra_requests:
        code = extra.get("code")
        asks_for = extra.get("asks_for")
        if not isinstance(code, str) or not code or not isinstance(asks_for, str) or not asks_for:
            raise ValueError("extra_requests entries need code and asks_for")
        requests.append({"code": code, "asks_for": asks_for})
    case_dispositions = [row.get("disposition") for row in cases]
    rejected = any(
        value in {"REJECT", "VIOLATED"} for value in case_dispositions
    )
    if rejected:
        inspectability = "REJECT"
    elif requests:
        inspectability = "REQUEST_EVIDENCE"
    elif not cases:
        inspectability = "REQUEST_EVIDENCE"
        requests.append(
            {
                "code": "case.missing",
                "asks_for": "at least one on-disk case receipt for this space",
            }
        )
    else:
        inspectability = "ACCEPT"
    payload = {
        "format": INDEX_FORMAT,
        "project_id": space_doc.get("project_id"),
        "building_id": space_doc.get("building_id"),
        "space_id": space_doc.get("space_id"),
        "space_ref": space_doc.get("space_ref"),
        "inspectability": inspectability,
        "open_requests": requests,
        "cited": cited,
        "bound_cases": cases,
        "non_claims": list(_NON_CLAIMS),
        "claim_scope": CLAIM_SCOPE,
    }
    document = {
        **payload,
        "digest": canonical_digest(payload),
    }
    return InspectabilityIndex(document)


def tickets_from_index(index: InspectabilityIndex) -> tuple[CrewTicket, ...]:
    """Work orders from open requests. Presentable spaces emit no tickets."""
    if index.inspectability == "ACCEPT":
        return ()
    space_id = str(index.document.get("space_id") or "space:unidentified")
    tickets = []
    for raw in index.document.get("open_requests") or ():
        if not isinstance(raw, dict):
            continue
        code = str(raw.get("code") or "")
        asks_for = str(raw.get("asks_for") or "")
        if not code:
            continue
        tickets.append(
            CrewTicket(
                space_id=space_id,
                code=code,
                asks_for=asks_for,
                instrument_class=TICKET_INSTRUMENT.get(code, "unspecified"),
                presentable=False,
            )
        )
    return tuple(tickets)
