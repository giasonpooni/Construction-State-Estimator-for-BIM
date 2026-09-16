"""RCI bind, JSPT variance push, disposition world cites."""

from __future__ import annotations

from typing import Mapping

from gat.harness.atlas import Atlas, AtlasError, Edge, Slot


def bind_rci_observation(atlas: Atlas, record: Mapping[str, object], target: str) -> Edge:
    quality = record.get("quality") if isinstance(record.get("quality"), Mapping) else {}
    if quality.get("acquisition") not in {None, "received"}:
        raise AtlasError("RCI record is not a received observation")
    if target not in atlas.slots:
        raise AtlasError("observation target is not an atlas slot")
    slot = atlas.slots[target]
    unit = record.get("sigma_unit") or record.get("indicated_unit")
    if unit != slot.unit:
        raise AtlasError("observation unit must match the target slot unit")
    added = atlas.add_slot(Slot("RCI", str(record.get("observation_id")), "indicated", str(unit), slot.world))
    return atlas.add_edge(
        Edge(
            added.id,
            target,
            "observation",
            1.0,
            0.0,
            observation_id=str(record.get("observation_id")),
            sigma=float(record.get("sigma")),
            sigma_unit=str(unit),
            reason=f"bound {record.get('calibration_id')}",
        )
    )


def push_variance(scale: float, variance: float) -> float:
    from gat.adapters.jspt import chart_covariance
    import numpy as np

    mapped = chart_covariance([[scale]], [[variance]])
    return float(np.asarray(mapped).reshape(()))


def cite_disposition_worlds(pin: Mapping[str, object], *, beam_live_digest: str) -> dict[str, object]:
    prior = pin.get("prior") if isinstance(pin.get("prior"), Mapping) else {}
    revised = pin.get("revised_after_certificate") if isinstance(pin.get("revised_after_certificate"), Mapping) else {}
    beam = pin.get("beam") if isinstance(pin.get("beam"), Mapping) else {}
    return {
        "schema": "cse-disposition-world-cite-v1",
        "claim_scope": "record-integrity-only",
        "entity_id": f"{beam.get('ifc_class')}:{beam.get('global_id')}",
        "worlds": {
            "beam-b1-ifc": {"kind": "live-ifc", "world_digest": beam_live_digest},
            "beam-b1-pin-prior": {
                "kind": "certificate-pin",
                "world_digest": prior.get("world_digest"),
                "verdict": prior.get("verdict"),
            },
            "beam-b1-pin-revised": {
                "kind": "certificate-pin",
                "world_digest": revised.get("world_digest"),
                "verdict": revised.get("verdict"),
            },
        },
        "same_entity": True,
        "same_world": False,
    }
