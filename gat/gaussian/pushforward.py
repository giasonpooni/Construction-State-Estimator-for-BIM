"""Full-view pushforward. Covariance is JSPT first_order_covariance."""

from __future__ import annotations

import numpy as np
from numpy.typing import ArrayLike

from gat.adapters.jspt import derived_covariance
from gat.gaussian.linalg import symmetrize


def push_sigma(J: ArrayLike, sigma_raw: ArrayLike) -> np.ndarray:
    return symmetrize(derived_covariance(J, sigma_raw))
