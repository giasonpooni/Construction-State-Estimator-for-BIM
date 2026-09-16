"""Integer scan residual a zkVM guest could later prove.

Pose is millimetres and milliradians. Ranges are millimetres. The grid is
binary. No IEEE-754 in the hot path. This is not a particle filter and
not a proof.
"""

from __future__ import annotations

from typing import Sequence

I32 = int
_MIN = -(1 << 31)
_MAX = (1 << 31) - 1


def _i32(value: object, name: str) -> I32:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be i32, not {type(value).__name__}")
    if value < _MIN or value > _MAX:
        raise OverflowError(f"{name} overflows i32")
    return value


def _add(a: I32, b: I32) -> I32:
    total = a + b
    if total < _MIN or total > _MAX:
        raise OverflowError("i32 add overflow")
    return total


def _mul(a: I32, b: I32) -> I32:
    product = a * b
    if product < _MIN or product > _MAX:
        raise OverflowError("i32 multiply overflow")
    return product


def sse_i32(residuals_mm: Sequence[object]) -> I32:
    """Sum of squared millimetre residuals."""
    acc = 0
    for i, raw in enumerate(residuals_mm):
        r = _i32(raw, f"r[{i}]")
        acc = _add(acc, _mul(r, r))
    return acc


def residual_i32(measured_mm: Sequence[object], predicted_mm: Sequence[object]) -> tuple[I32, ...]:
    if len(measured_mm) != len(predicted_mm):
        raise ValueError("measured and predicted lengths must match")
    out: list[I32] = []
    for i, (z, zhat) in enumerate(zip(measured_mm, predicted_mm)):
        out.append(_add(_i32(z, f"z[{i}]"), -_i32(zhat, f"zhat[{i}]")))
    return tuple(out)
