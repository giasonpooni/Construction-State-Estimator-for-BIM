"""Project canonical GAT state to a look-only USD overlay document.

Satellite. Does not call usd-core. Does not mutate World. L_estimate is
display. L_simulation stays empty until a declared plant exists.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Mapping

from gat.adapters.external_commitment import canonical_digest
from gat.harness.bundle import DEFAULT_PROJECT_SPACE_ID
from gat.harness.identity import identity_from_disposition

PROJECTION_SCHEMA = "notation-systems-usd-projection-v1"
CLAIM_SCOPE = "record-integrity-only"


@dataclass(frozen=True)
class UsdProjection:
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


def _verdict(document: Mapping[str, object], key: str) -> str | None:
    block = document.get(key)
    if isinstance(block, dict):
        value = block.get("verdict")
        return str(value) if value is not None else None
    return None


def _digest_of(document: Mapping[str, object], key: str) -> str | None:
    block = document.get(key)
    if isinstance(block, dict):
        value = block.get("world_digest")
        return str(value) if value is not None else None
    return None


def project_canonical_state(
    *,
    disposition: Mapping[str, object] | None = None,
    bundle: Mapping[str, object] | None = None,
    project_space_id: str | None = None,
) -> UsdProjection:
    space = project_space_id
    if not space and isinstance(bundle, Mapping):
        raw = bundle.get("project_space_id")
        if isinstance(raw, str) and raw.strip():
            space = raw.strip()
    space = (space or DEFAULT_PROJECT_SPACE_ID).strip()
    if not space:
        raise ValueError("project_space_id must be non-empty")

    prior = _verdict(disposition or {}, "prior")
    revised = _verdict(disposition or {}, "revised_after_certificate")
    world = _digest_of(disposition or {}, "revised_after_certificate") or _digest_of(
        disposition or {}, "prior"
    )
    beam = None
    if isinstance(disposition, Mapping):
        raw_beam = disposition.get("beam")
        beam = raw_beam if isinstance(raw_beam, dict) else None

    commitments = []
    merkle_root = None
    if isinstance(bundle, Mapping):
        raw_commits = bundle.get("commitments")
        if isinstance(raw_commits, list):
            commitments = [
                row.get("digest")
                for row in raw_commits
                if isinstance(row, dict) and row.get("digest")
            ]
        raw_merkle = bundle.get("merkle")
        if isinstance(raw_merkle, dict):
            merkle_root = raw_merkle.get("root")

    ident = identity_from_disposition(disposition or {}, project_space_id=space)
    payload = {
        "schema": PROJECTION_SCHEMA,
        "claim_scope": CLAIM_SCOPE,
        "mutates_source": False,
        "project_space_id": space,
        "identity": ident,
        "demonstrator": "bim-construction-acceptance",
        "service_class": "maintained-evidence-service",
        "canonical_world_digest": world,
        "layers": {
            "geometry": {
                "role": "L_geometry",
                "authority": "from IFC adapter; GAUSSIAN_PROXY is not as-built",
                "mutates_source": False,
            },
            "bim": {
                "role": "L_BIM",
                "beam": beam,
                "entity_is_not_mesh": True,
                "mutates_source": False,
            },
            "telemetry": {
                "role": "L_telemetry",
                "commitment_digests": commitments,
                "merkle_root": merkle_root,
                "usable_as_calibrated_observation": False,
                "mutates_source": False,
            },
            "estimate": {
                "role": "L_estimate",
                "overlay_only": True,
                "prior_verdict": prior,
                "revised_verdict": revised,
                "world_digest": world,
                "mutates_source": False,
                "note": "Display of an already-computed GAT world. Not a second Kalman.",
            },
            "simulation": {
                "role": "L_simulation",
                "status": "empty",
                "reason": "No declared plant or RTX sensor in v0. Omniverse is not opened.",
                "mutates_source": False,
            },
        },
        "workbench": {
            "blender": "read-only overlay; does not write ObserveQuantity",
            "bonsai": "optional IFC look; not the quantity oracle",
            "omniverse": "not-in-v0",
            "autocad": "adapter-later",
        },
        "refusals": [
            "USD composition does not condition belief.",
            "Muting L_estimate must not change the ledger.",
            "A synthetic camera is an RCI record or it does not exist.",
            "Vision-to-Lyapunov is not this projection.",
        ],
    }
    return UsdProjection({**payload, "digest": canonical_digest(payload)})
