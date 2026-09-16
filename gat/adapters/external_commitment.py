"""Bind an external record digest without turning it into GAT evidence.

Satellite. Does not condition belief. Does not invoke SP1. Does not
treat a millimetre record as yield strength.

Accepted schemas:
- rci-evidence-commitment-v1
- torus-report-commitment-v1
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Mapping

ALLOWED_SCHEMAS = {
    "rci-evidence-commitment-v1",
    "torus-report-commitment-v1",
}
CLAIM_SCOPE = "record-integrity-only"
BEAM_PROPERTIES = {"YieldStrengthMPa", "PlasticSectionModulusMajorM3"}


def canonical_digest(value: object) -> str:
    encoded = json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class ExternalCommitment:
    schema: str
    kind: str
    digest: str
    observation_id: str | None
    usable_as_calibrated_observation: bool = False

    def evidence_commitment_hex(self) -> str:
        return self.digest


def bind_external_commitment(document: Mapping[str, object]) -> ExternalCommitment:
    schema = document.get("schema")
    if schema not in ALLOWED_SCHEMAS:
        raise ValueError(f"unsupported external commitment schema {schema!r}")
    if document.get("claim_scope") != CLAIM_SCOPE:
        raise ValueError("claim_scope must be record-integrity-only")
    payload = document.get("payload")
    if not isinstance(payload, Mapping):
        raise ValueError("payload must be an object")
    digest = canonical_digest(payload)
    declared = document.get("digest")
    if declared != digest:
        raise ValueError("digest does not match payload")
    kind = document.get("kind")
    if not isinstance(kind, str) or not kind:
        raise ValueError("kind must be non-empty text")
    observation_id = document.get("observation_id")
    if observation_id is not None and not isinstance(observation_id, str):
        raise ValueError("observation_id must be text when present")
    quantity = payload.get("quantity") if isinstance(payload.get("quantity"), str) else None
    if quantity in BEAM_PROPERTIES:
        raise ValueError(
            "external instrument/report commitments cannot bind AISC beam properties"
        )
    return ExternalCommitment(
        schema=str(schema),
        kind=kind,
        digest=digest,
        observation_id=observation_id if isinstance(observation_id, str) else None,
        usable_as_calibrated_observation=False,
    )
