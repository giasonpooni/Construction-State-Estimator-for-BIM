from __future__ import annotations

import numpy as np
import pytest

from gat.errors import BindingError
from gat.geometry.survey_bind import SurveyTick, bind_tick, require_constitution, staff_indication


def _tick(**kwargs) -> SurveyTick:
    base = dict(
        session_id="sess-a",
        sequence=1,
        raw=(0.0, 1.5707963267948966, 10.0),
        project_space_id="bldg-1",
        chart_id="enu-a",
        installation_id="hi-1.500",
        ifc_guid="2O2Fr$t4X7Zf8NOew3FLOH",
    )
    base.update(kwargs)
    return SurveyTick(**base)


def test_refuses_missing_chart():
    with pytest.raises(BindingError, match="chart"):
        require_constitution(_tick(chart_id=""))


def test_refuses_dropped_tick():
    with pytest.raises(BindingError, match="pack"):
        require_constitution(_tick(acquisition="dropped"))


def test_refuses_empty_raw():
    with pytest.raises(BindingError, match="raw"):
        require_constitution(_tick(raw=()))


def test_staff_is_affine_indication():
    assert staff_indication(1.234, offset=0.0, gain=1.0) == 1.234


def test_bind_uses_jspt_grams():
    pytest.importorskip("sensitivity")
    t = np.diag([1000.0, 1000.0])
    p = np.array([[1.0, 0.2], [0.2, 1.5]])
    out = bind_tick(_tick(), t, p)
    assert out["conditions_belief"] is False
    assert out["installation_id"] == "hi-1.500"
    np.testing.assert_allclose(out["P_chart"], [[1e6, 2e5], [2e5, 1.5e6]], atol=1e-11)
