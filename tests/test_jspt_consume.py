"""GAT consumes JSPT through gat.adapters.jspt.

``gat.adapters.jspt`` imports the companion ``sensitivity`` clone lazily, so
the module imports here unconditionally and only the calls are guarded.
stdlib unittest only.
"""

from __future__ import annotations

import importlib.util
import unittest

import numpy as np

from gat.adapters.jspt import chart_covariance, derived_covariance
from gat.gaussian.pushforward import push_sigma


def sensitivity_available() -> bool:
    """True when the companion JSPT clone is importable."""
    try:
        return importlib.util.find_spec("sensitivity") is not None
    except (ImportError, ValueError):
        return False


@unittest.skipUnless(sensitivity_available(), "companion JSPT clone is not importable")
class JsptConsumeTests(unittest.TestCase):
    def test_gat_chart_uses_jspt_grams(self) -> None:
        t = np.diag([1000.0, 1000.0])
        p = np.array([[1.0, 0.2], [0.2, 1.5]])
        got = chart_covariance(t, p)
        np.testing.assert_allclose(
            got, [[1e6, 2e5], [2e5, 1.5e6]], atol=1e-11
        )

    def test_derived_view_uses_jspt(self) -> None:
        j = np.array([[1.0, 0.0], [0.0, 1.0], [1.0, 1.0]])
        p = np.eye(2)
        sigma = push_sigma(j, p)
        self.assertEqual(sigma.shape, (3, 3))
        np.testing.assert_allclose(sigma, derived_covariance(j, p))


if __name__ == "__main__":
    unittest.main()
