"""Measurement constitution on a layout point. Not an IFC class for HI."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import ArrayLike

from gat.errors import BindingError


@dataclass(frozen=True)
class SurveyTick:
    session_id: str
    sequence: int
    raw: tuple[float, ...]
    project_space_id: str
    chart_id: str
    installation_id: str
    ifc_guid: str
    acquisition: str = "received"
    quantity: str = "layout_point"
    units: str = "m"


def require_constitution(tick: SurveyTick) -> None:
    if not tick.project_space_id or not tick.chart_id or not tick.installation_id:
        raise BindingError("survey bind needs project_space_id, chart_id, installation_id")
    if not tick.ifc_guid or " " in tick.ifc_guid:
        raise BindingError("survey bind needs an Ifc GlobalId, not a display name")
    if tick.acquisition != "received":
        raise BindingError("dropped or unavailable ticks stay in the pack; they do not bind")
    if not tick.raw:
        raise BindingError("received tick must carry a raw tuple; no last-value fill")


def bind_tick(tick: SurveyTick, T: ArrayLike, P: ArrayLike) -> dict:
    require_constitution(tick)
    from gat.adapters.jspt import chart_covariance

    p_prime = chart_covariance(T, P)
    return {
        "ok": True,
        "kind": "survey_bind",
        "ifc_guid": tick.ifc_guid,
        "project_space_id": tick.project_space_id,
        "chart_id": tick.chart_id,
        "installation_id": tick.installation_id,
        "session_id": tick.session_id,
        "sequence": tick.sequence,
        "raw": list(tick.raw),
        "quantity": tick.quantity,
        "units": tick.units,
        "indication_is_not_process": True,
        "P_chart": np.asarray(p_prime, dtype=float).tolist(),
        "conditions_belief": False,
    }


def staff_indication(reading_m: float, offset: float = 0.0, gain: float = 1.0) -> float:
    """Digital level: same affine g(r;theta) as the bench. Not a clash."""
    return float(offset + gain * reading_m)
