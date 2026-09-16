"""Who may enter a guest. Kernel does not care if SP1 is missing."""

from __future__ import annotations

from typing import Mapping

ALLOWED = frozenset({"beam-b1-f2-1"})
FORBIDDEN = frozenset(
    {
        "jspt-a2-a5",
        "rci-tape",
        "torus-length",
        "jacobi-field",
        "atlas-laplacian",
        "sum-product",
        "full-estimator",
    }
)


def admit_guest(guest_id: str, *, claim_scope: str) -> Mapping[str, object]:
    if claim_scope != "computational-integrity-only":
        raise ValueError("zkVM claim_scope must be computational-integrity-only")
    if guest_id in FORBIDDEN:
        raise ValueError(f"guest {guest_id} is forbidden")
    if guest_id not in ALLOWED:
        raise ValueError(f"guest {guest_id} is not an implemented guest")
    return {
        "guest_id": guest_id,
        "admitted": True,
        "zero_knowledge": False,
        "kernel_if_backend_down": "unchanged",
    }
