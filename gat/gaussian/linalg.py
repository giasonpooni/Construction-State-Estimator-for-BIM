"""Numerical hygiene primitives for the Gaussian layer.

Design rules (fixed by the v0 architecture review):

* No matrix is ever explicitly inverted — gains come from Cholesky solves.
* The Joseph stabilized form is used for every conditioning update.
* PSD certification runs only on full-rank belief covariances, via
  Cholesky over a deterministic, trace-scaled jitter ladder; the jitter
  actually used is always reported to the caller (auditable, never silent).
* No eigendecompositions appear in the execution path — ``eigvalsh`` is
  reserved for error messages and tests.
"""

from __future__ import annotations

import numpy as np

from gat.errors import NumericalError

#: Relative jitter ladder; each entry is scaled by ``max(trace(S)/n, 1)``
#: so certification is unit-invariant.
JITTER_LADDER: tuple[float, ...] = (0.0, 1e-12, 1e-10)


def symmetrize(matrix: np.ndarray) -> np.ndarray:
    """Exact symmetric part ``0.5 * (A + A^T)``."""
    return 0.5 * (matrix + matrix.T)


def chol_psd(matrix: np.ndarray) -> tuple[np.ndarray, float]:
    """Cholesky factor of a (near-)PSD matrix with a deterministic jitter ladder.

    Returns ``(L, jitter_used)`` where ``jitter_used`` is the absolute
    diagonal jitter that was added (0.0 in the healthy case).  Raises
    :class:`NumericalError` when the ladder is exhausted — never repairs
    silently beyond the ladder.

    Non-finite input is refused before the ladder rather than run through it.
    ``numpy.linalg.cholesky`` does not raise on a matrix containing NaN: it
    returns a factor full of NaN, so the first rung "succeeded" and this
    returned that factor with ``jitter_used`` of 0.0 — reporting a covariance
    of NaN as healthy and needing no repair, which is the opposite of what
    this function is for.

    Every caller today checks finiteness first (``GaussianState`` refuses a
    non-finite Sigma at construction, and ``dynamics`` checks its process
    matrices), so this closes a gap rather than a live hole. That is the
    reason to close it: the guarantee should be this function's, not an
    obligation spread across five call sites that the next one may not know.
    """
    if not np.isfinite(matrix).all():
        raise NumericalError("matrix contains non-finite entries")
    n = matrix.shape[0]
    scale = max(float(np.trace(matrix)) / max(n, 1), 1.0)
    for rung in JITTER_LADDER:
        jitter = rung * scale
        try:
            L = np.linalg.cholesky(matrix + jitter * np.eye(n))
            return L, jitter
        except np.linalg.LinAlgError:
            continue
    min_eig = float(np.linalg.eigvalsh(symmetrize(matrix)).min())
    raise NumericalError(
        f"matrix is not PSD within the jitter ladder (min eigenvalue {min_eig:.3e})"
    )


def chol_solve(L: np.ndarray, rhs: np.ndarray) -> np.ndarray:
    """Solve ``S x = rhs`` given the Cholesky factor ``L`` of ``S``.

    Uses two triangular solves; never forms an inverse.
    """
    y = np.linalg.solve(L, rhs)
    return np.linalg.solve(L.T, y)


def assert_finite(array: np.ndarray, what: str) -> None:
    if not np.isfinite(array).all():
        raise NumericalError(f"{what} contains non-finite entries")


def max_asymmetry(matrix: np.ndarray) -> float:
    return float(np.abs(matrix - matrix.T).max()) if matrix.size else 0.0
