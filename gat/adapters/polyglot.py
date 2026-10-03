"""Export a bounded local quantity response; do not condition or commit a World.

The plain-data output is consumed by CIW's existing Rust-supervised C++/Julia
operation. CIW is deliberately not a dependency of this scientific package.
"""
from __future__ import annotations

import math
from numbers import Real
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from gat.engine.executor import World
    from gat.ids import VarId


def _number(value):
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError("Require a real number, not a coerced value")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("Require a finite value")
    return result


def _axis(world, var, scale):
    scale = _number(scale)
    if not 1e-100 <= scale <= 1e100:
        raise ValueError("Normalization scale outside positive bounds")
    return {"id": f"{var.entity.ifc_class}/{var.entity.global_id}/{var.quantity}",
            "unit": world.module.slot(var).unit.value, "scale": scale}


def linear_response_case(world: World, inputs: list[VarId], outputs: list[VarId],
                         deltas: list[float], *, input_scales: list[float],
                         output_scales: list[float]) -> dict:
    """Export y0 + J_selected delta from the current World's actual Jacobian.

Inputs must be raw variables; outputs may be raw or derived. Scales express one
unit-labelled coordinate in the native dimensionless basis, not a conversion.
The mean tangent is not a nonlinear prediction or a new architectural belief.
Covariance remains in the unchanged World and is not propagated by this seam.
"""
    inputs, outputs = list(inputs), list(outputs)
    deltas, input_scales, output_scales = list(deltas), list(input_scales), list(output_scales)
    if not 1 <= len(inputs) <= 8 or not 1 <= len(outputs) <= 8:
        raise ValueError("Select one to eight inputs and outputs")
    if len(set(inputs)) != len(inputs) or len(set(outputs)) != len(outputs):
        raise ValueError("Duplicate variable selection")
    if len(deltas) != len(inputs) or len(input_scales) != len(inputs) or len(output_scales) != len(outputs):
        raise ValueError("Selection, delta and scale dimensions differ")
    if world.jacobian is None:
        raise ValueError("World has no retained full-to-raw Jacobian")
    raw, full = list(world.belief.index.vars), list(world.full.index.vars)
    try:
        columns, rows = [raw.index(v) for v in inputs], [full.index(v) for v in outputs]
    except ValueError as exc:
        raise ValueError("Inputs must be known raw variables; outputs must be known full variables") from exc
    identity = world.digest()
    if type(identity) is not str or not re.fullmatch(r"[0-9a-f]{64}", identity):
        raise ValueError("Malformed World digest")
    return {
        "schema": "notation.linear-map.v1",
        "model": {"owner": "State-Estimator-for-BIM", "kind": "bim-local-jacobian.v1", "digest": "sha256:" + identity},
        "frame": "bim-quantity-coordinates",
        "inputs": [_axis(world, v, s) for v, s in zip(inputs, input_scales)],
        "outputs": [_axis(world, v, s) for v, s in zip(outputs, output_scales)],
        "baseline": [_number(world.full.mu[i]) for i in rows],
        "jacobian_row_major": [_number(world.jacobian[i, j]) for i in rows for j in columns],
        "delta": [_number(v) for v in deltas],
        "claim_scope": "first-order-mean-response-only", "covariance": "not_propagated", "may_authorize": False,
    }
