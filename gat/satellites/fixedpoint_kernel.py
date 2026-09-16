"""Integer discrete maps that a zkVM guest could later prove.

No IEEE-754 in the hot path. Not a prover. Not a geodesic.
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


def _mat2(matrix: Sequence[Sequence[object]], name: str) -> tuple[tuple[I32, I32], tuple[I32, I32]]:
    if len(matrix) != 2 or any(len(row) != 2 for row in matrix):
        raise ValueError(f"{name} must be 2x2")
    return (
        (_i32(matrix[0][0], f"{name}[0][0]"), _i32(matrix[0][1], f"{name}[0][1]")),
        (_i32(matrix[1][0], f"{name}[1][0]"), _i32(matrix[1][1], f"{name}[1][1]")),
    )


def _vec2(vector: Sequence[object], name: str) -> tuple[I32, I32]:
    if len(vector) != 2:
        raise ValueError(f"{name} must have length 2")
    return (_i32(vector[0], f"{name}[0]"), _i32(vector[1], f"{name}[1]"))


def _mul(a: I32, b: I32) -> I32:
    product = a * b
    if product < _MIN or product > _MAX:
        raise OverflowError("i32 multiply overflow")
    return product


def _add(a: I32, b: I32) -> I32:
    total = a + b
    if total < _MIN or total > _MAX:
        raise OverflowError("i32 add overflow")
    return total


def _dot(row: tuple[I32, I32], vector: tuple[I32, I32]) -> I32:
    return _add(_mul(row[0], vector[0]), _mul(row[1], vector[1]))


def _mv(matrix: tuple[tuple[I32, I32], tuple[I32, I32]], vector: tuple[I32, I32]) -> tuple[I32, I32]:
    return (_dot(matrix[0], vector), _dot(matrix[1], vector))


def chain_jvp_i32(
    j1: Sequence[Sequence[object]],
    dx: Sequence[object],
    j2: Sequence[Sequence[object]],
) -> tuple[I32, I32]:
    """y = J2 (J1 dx). Discrete JSPT chain rule on i32 2x2 maps."""
    mid = _mv(_mat2(j1, "J1"), _vec2(dx, "dx"))
    return _mv(_mat2(j2, "J2"), mid)


def quadratic_i32(
    matrix: tuple[tuple[I32, I32], tuple[I32, I32]],
    vector: tuple[I32, I32],
) -> I32:
    return _dot(vector, _mv(matrix, vector))


def discrete_lyapunov_decrease_i32(
    a: Sequence[Sequence[object]],
    p: Sequence[Sequence[object]],
    x: Sequence[object],
) -> dict[str, object]:
    """One-sample discrete decrease: x+ = A x, V = x^T P x, claim V+ < V."""
    a_i = _mat2(a, "A")
    p_i = _mat2(p, "P")
    x_i = _vec2(x, "x")
    x_next = _mv(a_i, x_i)
    v = quadratic_i32(p_i, x_i)
    v_next = quadratic_i32(p_i, x_next)
    return {
        "x": list(x_i),
        "x_next": list(x_next),
        "V": v,
        "V_next": v_next,
        "decreases": v_next < v,
    }
