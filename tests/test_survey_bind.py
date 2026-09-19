"""Survey tick binding refuses anything it cannot constitute.

The JSPT-backed chart push is exercised only when the companion
``sensitivity`` clone is importable; the refusal contract is local and
always runs.  stdlib unittest only.
"""

from __future__ import annotations

import importlib.util
import unittest

import numpy as np

from gat.errors import BindingError
from gat.geometry.survey_bind import SurveyTick, bind_tick, require_constitution, staff_indication


def sensitivity_available() -> bool:
    """True when the companion JSPT clone is importable."""
    try:
        return importlib.util.find_spec("sensitivity") is not None
    except (ImportError, ValueError):
        return False


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


class SurveyBindRefusalTests(unittest.TestCase):
    def test_refuses_missing_chart(self) -> None:
        with self.assertRaisesRegex(BindingError, "chart"):
            require_constitution(_tick(chart_id=""))

    def test_refuses_dropped_tick(self) -> None:
        with self.assertRaisesRegex(BindingError, "pack"):
            require_constitution(_tick(acquisition="dropped"))

    def test_refuses_empty_raw(self) -> None:
        with self.assertRaisesRegex(BindingError, "raw"):
            require_constitution(_tick(raw=()))

    def test_staff_is_affine_indication(self) -> None:
        self.assertEqual(staff_indication(1.234, offset=0.0, gain=1.0), 1.234)


@unittest.skipUnless(sensitivity_available(), "companion JSPT clone is not importable")
class SurveyBindChartTests(unittest.TestCase):
    def test_bind_uses_jspt_grams(self) -> None:
        t = np.diag([1000.0, 1000.0])
        p = np.array([[1.0, 0.2], [0.2, 1.5]])
        out = bind_tick(_tick(), t, p)
        self.assertIs(out["conditions_belief"], False)
        self.assertEqual(out["installation_id"], "hi-1.500")
        np.testing.assert_allclose(
            out["P_chart"], [[1e6, 2e5], [2e5, 1.5e6]], atol=1e-11
        )


if __name__ == "__main__":
    unittest.main()
