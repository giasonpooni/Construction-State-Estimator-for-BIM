"""Assemble a multi-tool experiment bundle without fusing claims.

Satellite. Does not condition belief. Does not import JSPT, RCI, or
flat_torus. Does not invoke SP1. A bound millimetre stays a millimetre.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Iterable, Mapping

from gat.adapters.external_commitment import (
    CLAIM_SCOPE,
    ExternalCommitment,
    bind_external_commitment,
    canonical_digest,
)

BUNDLE_SCHEMA = "notation-systems-harness-bundle-v1"
ALLOWED_SP1_STATUS = frozenset(
    {"NOT_REQUESTED", "BACKEND_REQUIRED", "UNAVAILABLE"}
)


@dataclass(frozen=True)
class HarnessBundle:
    document: dict[str, object]

    @property
    def digest(self) -> str:
        return str(self.document["digest"])

    def write(self, path: str | Path) -> Path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(self.document, indent=2, sort_keys=True, allow_nan=False)
            + "\n",
            encoding="utf-8",
        )
        return target


def load_json(path: str | Path) -> dict[str, object]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return raw


def bind_commitment_file(path: str | Path) -> ExternalCommitment:
    return bind_external_commitment(load_json(path))


def _bound_record(bound: ExternalCommitment, source: str | None) -> dict[str, object]:
    return {
        "schema": bound.schema,
        "kind": bound.kind,
        "digest": bound.digest,
        "observation_id": bound.observation_id,
        "usable_as_calibrated_observation": bound.usable_as_calibrated_observation,
        "source": source,
    }


def _disposition_slice(document: Mapping[str, object] | None) -> dict[str, object] | None:
    if document is None:
        return None
    beam = document.get("beam")
    criterion = document.get("criterion")
    prior = document.get("prior")
    revised = document.get("revised_after_certificate")
    return {
        "format": document.get("format"),
        "model": document.get("model"),
        "beam": beam if isinstance(beam, dict) else None,
        "criterion": criterion if isinstance(criterion, dict) else None,
        "prior_verdict": prior.get("verdict") if isinstance(prior, dict) else None,
        "revised_verdict": (
            revised.get("verdict") if isinstance(revised, dict) else None
        ),
        "prior_world_digest": (
            prior.get("world_digest") if isinstance(prior, dict) else None
        ),
        "revised_world_digest": (
            revised.get("world_digest") if isinstance(revised, dict) else None
        ),
    }


def assemble_bundle(
    *,
    commitments: Iterable[tuple[ExternalCommitment, str | None]] = (),
    disposition: Mapping[str, object] | None = None,
    sp1_status: str = "NOT_REQUESTED",
    note: str | None = None,
) -> HarnessBundle:
    if sp1_status not in ALLOWED_SP1_STATUS:
        raise ValueError(
            "sp1_status must be NOT_REQUESTED, BACKEND_REQUIRED, or UNAVAILABLE"
        )
    records = [_bound_record(bound, source) for bound, source in commitments]
    for record in records:
        if record["usable_as_calibrated_observation"]:
            raise ValueError("harness refuses to promote a record into GAT evidence")
    payload = {
        "schema": BUNDLE_SCHEMA,
        "status": "in-development",
        "released": False,
        "claim_scope": CLAIM_SCOPE,
        "disposition": _disposition_slice(disposition),
        "commitments": records,
        "sp1": {
            "invoked": False,
            "proof_verified": False,
            "status": sp1_status,
            "note": "A guest may attest one already-computed arithmetic claim. It does not prove A2-A5, Sigma, or a physical stream.",
        },
        "refusals": [
            "Does not import JSPT into a guest.",
            "Does not prove on an instrument.",
            "Does not treat an RCI millimetre as YieldStrengthMPa.",
            "Does not treat a torus length as a covariance.",
            "Does not fuse axioms, Sigma, and a bench into one theorem.",
        ],
        "note": note
        or "Bundle of independently replayable records. Alignment is digest binding, not fusion.",
    }
    document = {
        **payload,
        "digest": canonical_digest(payload),
    }
    return HarnessBundle(document)
