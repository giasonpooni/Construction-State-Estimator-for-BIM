"""GAT call site for JSPT. Do not form T @ P @ T.T in domain code."""

from __future__ import annotations

import numpy as np
from numpy.typing import ArrayLike


def chart_covariance(T: ArrayLike, P: ArrayLike, *, inverse: bool = False):
    from sensitivity.coordinates import push_covariance

    return np.asarray(push_covariance(T, P, inverse=inverse), dtype=np.float64)


def derived_covariance(J: ArrayLike, P_raw: ArrayLike):
    from sensitivity.covariance import first_order_covariance

    return np.asarray(first_order_covariance(J, P_raw), dtype=np.float64)
