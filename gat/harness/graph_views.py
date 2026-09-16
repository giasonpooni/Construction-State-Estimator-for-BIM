"""Three graph views of existing objects. Not a second estimator.

Spectral: eigenvalues of the atlas adjacency. Connectivity invariant.
Functional: ledger events as out-degree-1 world transitions.
Factor: declared factorization of a slot. No sum-product.
"""

from __future__ import annotations

from typing import Mapping, Sequence

import numpy as np

from gat.harness.atlas import Atlas


def atlas_adjacency(atlas: Atlas) -> tuple[list[str], np.ndarray]:
    names = sorted(atlas.slots)
    index = {name: i for i, name in enumerate(names)}
    n = len(names)
    adj = np.zeros((n, n), dtype=float)
    for edge in atlas.edges:
        i = index[edge.source]
        j = index[edge.target]
        adj[i, j] = 1.0
        if edge.kind == "representation":
            adj[j, i] = 1.0
    return names, adj


def spectral_atlas(atlas: Atlas) -> dict[str, object]:
    names, adj = atlas_adjacency(atlas)
    if not names:
        raise ValueError("atlas has no slots")
    degree = np.diag(adj.sum(axis=1))
    lap = degree - adj
    eig = np.sort(np.real(np.linalg.eigvals(lap)))
    return {
        "schema": "cse-spectral-atlas-v1",
        "claim_scope": "record-integrity-only",
        "matrix": "unnormalized Laplacian of atlas adjacency",
        "nodes": names,
        "edge_count": len(atlas.edges),
        "eigenvalues": [float(v) for v in eig],
        "algebraic_connectivity": float(eig[1]) if len(eig) > 1 else 0.0,
        "note": "Spectrum is a connectivity invariant of the atlas. Not a belief.",
    }


def functional_ledger(events: Sequence[Mapping[str, object]]) -> dict[str, object]:
    transitions = []
    seen: dict[str, str] = {}
    forks = []
    for event in events:
        prior = event.get("prior_world_digest")
        result = event.get("result_world_digest")
        if not isinstance(prior, str) or not isinstance(result, str):
            continue
        if prior in seen and seen[prior] != result:
            forks.append({"prior": prior, "first": seen[prior], "again": result})
        seen[prior] = result
        transitions.append(
            {"prior": prior, "result": result, "event_hash": event.get("event_hash")}
        )
    return {
        "schema": "cse-functional-ledger-v1",
        "claim_scope": "record-integrity-only",
        "kind": "functional-digraph",
        "out_degree": 1,
        "transitions": transitions,
        "forks": forks,
        "functional": not forks,
        "note": "A fork means two next worlds from one prior. That is a ledger bug, not a mixture.",
    }


def opening_factorization() -> dict[str, object]:
    return {
        "schema": "cse-factor-declaration-v1",
        "claim_scope": "record-integrity-only",
        "estimator": "dense-GAT",
        "sum_product": False,
        "factors": [
            {"id": "f-opening-width", "variables": ["Opening-1.Width"], "kind": "prior-slot"},
            {"id": "f-door-width", "variables": ["Door-1.Width"], "kind": "prior-slot"},
            {
                "id": "f-obs-p204",
                "variables": ["Opening-1.Width", "rci:office-a-p204:1"],
                "kind": "observation",
                "requires_sigma": True,
            },
            {
                "id": "f-fit-margin",
                "variables": ["Opening-1.Width", "Door-1.Width"],
                "kind": "constraint",
                "statement": "Width_opening - Width_door >= 0.05 m",
            },
        ],
        "refusals": [
            "A factor list is not inference.",
            "Do not replace dense Beam-B1 with sum-product.",
            "Observation factor without sigma is refused by the atlas.",
        ],
    }
