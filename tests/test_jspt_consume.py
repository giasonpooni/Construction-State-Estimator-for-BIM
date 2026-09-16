"""GAT consumes JSPT through gat.adapters.jspt. Skip if kernel missing."""

from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("sensitivity")
from gat.adapters.jspt import chart_covariance, derived_covariance
from gat.gaussian.pushforward import push_sigma


def test_gat_chart_uses_jspt_grams():
    t = np.diag([1000.0, 1000.0])
    p = np.array([[1.0, 0.2], [0.2, 1.5]])
    got = chart_covariance(t, p)
    np.testing.assert_allclose(got, [[1e6, 2e5], [2e5, 1.5e6]], atol=1e-11)


def test_derived_view_uses_jspt():
    j = np.array([[1.0, 0.0], [0.0, 1.0], [1.0, 1.0]])
    p = np.eye(2)
    sigma = push_sigma(j, p)
    assert sigma.shape == (3, 3)
    np.testing.assert_allclose(sigma, derived_covariance(j, p))
