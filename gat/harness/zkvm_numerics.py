"""Guest arithmetic policy. Float kernels are refused."""

from __future__ import annotations

from typing import Mapping

ADMITTED = frozenset({"checked-integer", "scaled-integer"})
REFUSED = frozenset({"ieee754", "float32", "float64", "f32", "f64"})


def admit_numeric_profile(profile: Mapping[str, object]) -> Mapping[str, object]:
    arithmetic = profile.get("arithmetic")
    if not isinstance(arithmetic, str) or not arithmetic:
        raise ValueError("numeric profile must declare arithmetic")
    if arithmetic in REFUSED or arithmetic.startswith("ieee"):
        raise ValueError("IEEE-754 is refused in a guest; quantize on the host")
    if arithmetic not in ADMITTED:
        raise ValueError(f"unsupported guest arithmetic {arithmetic!r}")
    guest_id = profile.get("guest_id")
    if guest_id and guest_id != "beam-b1-f2-1":
        raise ValueError("only beam-b1-f2-1 has an implemented numeric profile")
    return {
        "admitted": True,
        "arithmetic": arithmetic,
        "guest_id": guest_id or "beam-b1-f2-1",
        "quantize_on": "host",
    }
