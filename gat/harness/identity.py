"""Shared sandbox identity: EntityId + cited world digests + project space.

Satellite. Aligns look surfaces. Does not condition belief.
A live IFC load and a post-certificate pin may differ in world digest;
they must still name the same EntityId.
"""

from __future__ import annotations

from typing import Mapping


def entity_id(ifc_class: str, global_id: str) -> str:
    return f"{ifc_class}:{global_id}"


def identity_from_disposition(
    disposition: Mapping[str, object],
    *,
    project_space_id: str | None = None,
) -> dict[str, object]:
    beam = disposition.get("beam")
    if not isinstance(beam, Mapping):
        beam = {}
    ifc_class = beam.get("ifc_class")
    global_id = beam.get("global_id")
    name = beam.get("name")
    prior = disposition.get("prior") if isinstance(disposition.get("prior"), Mapping) else {}
    revised = disposition.get("revised_after_certificate")
    if not isinstance(revised, Mapping):
        revised = {}
    cited = revised.get("world_digest") or (
        prior.get("world_digest") if isinstance(prior, Mapping) else None
    )
    return {
        "project_space_id": project_space_id,
        "entity": {
            "ifc_class": ifc_class,
            "global_id": global_id,
            "name": name,
            "entity_id": entity_id(str(ifc_class), str(global_id))
            if ifc_class and global_id
            else None,
        },
        "prior_world_digest": prior.get("world_digest") if isinstance(prior, Mapping) else None,
        "revised_world_digest": revised.get("world_digest"),
        "cited_world_digest": cited,
    }


def workbench_has_entity(state: Mapping[str, object], ifc_class: str, global_id: str) -> bool:
    wanted = entity_id(ifc_class, global_id)
    entities = state.get("entities")
    if not isinstance(entities, list):
        return False
    for row in entities:
        if not isinstance(row, dict):
            continue
        if row.get("entity") == wanted:
            return True
        if row.get("class") == ifc_class and str(row.get("entity", "")).endswith(global_id):
            return True
    return False


def assert_look_surfaces_aligned(
    *,
    disposition: Mapping[str, object],
    projection: Mapping[str, object],
    workbench_state: Mapping[str, object],
    project_space_id: str | None = None,
) -> None:
    ident = identity_from_disposition(disposition, project_space_id=project_space_id)
    entity = ident["entity"]
    if not isinstance(entity, dict) or not entity.get("global_id"):
        raise ValueError("disposition does not name an EntityId")
    ifc_class = str(entity["ifc_class"])
    global_id = str(entity["global_id"])
    if not workbench_has_entity(workbench_state, ifc_class, global_id):
        raise ValueError(
            f"workbench STATE does not contain {entity_id(ifc_class, global_id)}"
        )
    cited = ident["cited_world_digest"]
    if projection.get("canonical_world_digest") != cited:
        raise ValueError("USD projection canonical_world_digest does not match the pin")
    layers = projection.get("layers")
    if not isinstance(layers, dict):
        raise ValueError("USD projection missing layers")
    est = layers.get("estimate")
    if not isinstance(est, dict) or est.get("world_digest") != cited:
        raise ValueError("L_estimate world_digest does not match the pin")
    proj_identity = projection.get("identity")
    if isinstance(proj_identity, dict):
        named = proj_identity.get("entity")
        if isinstance(named, dict) and named.get("global_id") not in {None, global_id}:
            raise ValueError("USD projection EntityId disagrees with the pin")
    live = workbench_state.get("world_digest")
    if live == cited or live == ident["prior_world_digest"]:
        return
