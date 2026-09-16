"""GAT consumes JSPT. Skip if the kernel is not on PYTHONPATH."""

from __future__ import annotations

import numpy as np
import pytest

sensitivity = pytest.importorskip("sensitivity")
from sensitivity.coordinates import push_covariance


def test_gat_does_not_own_grams_push():
    t = np.diag([1000.0, 1000.0])
    p = np.array([[1.0, 0.2], [0.2, 1.5]])
    got = push_covariance(t, p)
    np.testing.assert_allclose(got, [[1e6, 2e5], [2e5, 1.5e6]], atol=1e-11)
