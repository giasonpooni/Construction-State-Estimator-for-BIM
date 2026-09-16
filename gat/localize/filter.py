"""SE(2) particle filter / Monte Carlo localization.

Bootstrap proposal uses the motion model. An optional tangent is pushed
by the adjoint of each increment (a discrete Jacobi field on SE(2)).
Diagnostics are first-class: N_eff, unique support, max weight.

The filter does not write BIM state and does not mint survey provenance.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from gat.localize import se2
from gat.localize.occupancy import OccupancyGrid, free_cells
from gat.localize.residual import Scan, log_likelihood, residual


@dataclass(frozen=True)
class MotionNoise:
    """Diagonal se(2) process covariance for one step, body coordinates."""

    sigma_x: float
    sigma_y: float
    sigma_theta: float

    def sample(self, rng: np.random.Generator, n: int) -> np.ndarray:
        return rng.normal(
            0.0,
            [self.sigma_x, self.sigma_y, self.sigma_theta],
            size=(n, 3),
        )


@dataclass(frozen=True)
class FilterDiagnostics:
    n_eff: float
    unique_count: int
    max_weight: float
    entropy: float
    mean_pose: np.ndarray
    tangent_cov: np.ndarray
    collapsed: bool
    log_likelihood_mean: float


@dataclass
class ParticleFilter:
    poses: np.ndarray
    weights: np.ndarray
    tangents: np.ndarray | None
    rng: np.random.Generator

    @classmethod
    def uniform_free(
        cls,
        grid: OccupancyGrid,
        n: int,
        rng: np.random.Generator,
        with_tangents: bool = False,
    ) -> "ParticleFilter":
        cells = free_cells(grid)
        if cells.shape[0] == 0:
            raise ValueError("occupancy grid has no free cells")
        idx = rng.integers(0, cells.shape[0], size=n)
        xy = cells[idx]
        th = rng.uniform(-np.pi, np.pi, size=n)
        poses = np.column_stack([xy, th])
        weights = np.full(n, 1.0 / n, dtype=np.float64)
        tangents = np.zeros((n, 3), dtype=np.float64) if with_tangents else None
        return cls(poses=poses, weights=weights, tangents=tangents, rng=rng)

    @classmethod
    def around(
        cls,
        pose: np.ndarray,
        n: int,
        rng: np.random.Generator,
        noise: MotionNoise,
        with_tangents: bool = False,
    ) -> "ParticleFilter":
        xi = noise.sample(rng, n)
        poses = np.stack([se2.compose(pose, se2.exp_se2(x)) for x in xi])
        weights = np.full(n, 1.0 / n, dtype=np.float64)
        tangents = xi.copy() if with_tangents else None
        return cls(poses=poses, weights=weights, tangents=tangents, rng=rng)

    @property
    def n(self) -> int:
        return int(self.poses.shape[0])

    def predict(self, v: float, omega: float, dt: float, noise: MotionNoise) -> None:
        increment = se2.unicycle_increment(v, omega, dt)
        xi = noise.sample(self.rng, self.n)
        new_poses = np.empty_like(self.poses)
        new_tangents = None if self.tangents is None else np.empty_like(self.tangents)
        for i in range(self.n):
            moved = se2.compose(self.poses[i], increment)
            noisy = se2.exp_se2(xi[i])
            new_poses[i] = se2.compose(moved, noisy)
            if new_tangents is not None:
                pushed = se2.transport_tangent(increment, self.tangents[i])
                new_tangents[i] = pushed + xi[i]
        self.poses = new_poses
        self.tangents = new_tangents

    def update(self, scan: Scan, grid: OccupancyGrid, sigma: float) -> np.ndarray:
        logs = np.empty(self.n, dtype=np.float64)
        for i in range(self.n):
            res = residual(self.poses[i], scan, grid)
            logs[i] = log_likelihood(res, sigma)
        logs -= float(np.max(logs))
        w = self.weights * np.exp(logs)
        total = float(np.sum(w))
        if not np.isfinite(total) or total <= 0.0:
            self.weights = np.full(self.n, 1.0 / self.n, dtype=np.float64)
        else:
            self.weights = w / total
        return logs

    def step(
        self,
        v: float,
        omega: float,
        dt: float,
        noise: MotionNoise,
        scan: Scan,
        grid: OccupancyGrid,
        sigma: float,
        resample_frac: float = 0.5,
    ) -> FilterDiagnostics:
        """Predict, update, diagnose, then resample. Diagnostics are pre-resample."""
        self.predict(v, omega, dt, noise)
        self.update(scan, grid, sigma)
        diag = self.diagnostics()
        self.resample_if_needed(resample_frac)
        return diag

    def n_eff(self) -> float:
        return float(1.0 / np.sum(self.weights * self.weights))

    def resample_if_needed(self, threshold_frac: float = 0.5) -> bool:
        if self.n_eff() >= threshold_frac * self.n:
            return False
        self._systematic_resample()
        return True

    def _systematic_resample(self) -> None:
        n = self.n
        positions = (self.rng.uniform() + np.arange(n)) / n
        cdf = np.cumsum(self.weights)
        cdf[-1] = 1.0
        idx = np.searchsorted(cdf, positions)
        self.poses = self.poses[idx].copy()
        if self.tangents is not None:
            self.tangents = self.tangents[idx].copy()
        self.weights = np.full(n, 1.0 / n, dtype=np.float64)

    def unique_count(self, position_bin: float, angle_bin: float) -> int:
        bx = np.round(self.poses[:, 0] / position_bin)
        by = np.round(self.poses[:, 1] / position_bin)
        bt = np.round(se2.wrap_angle(self.poses[:, 2]) / angle_bin)
        return int(np.unique(np.stack([bx, by, bt], axis=1), axis=0).shape[0])

    def diagnostics(self, position_bin: float = 0.05, angle_bin: float = 0.05) -> FilterDiagnostics:
        mean = se2.weighted_mean_pose(self.poses, self.weights)
        cov = se2.tangent_covariance(self.poses, self.weights, mean)
        n_eff = self.n_eff()
        max_w = float(np.max(self.weights))
        w = np.clip(self.weights, 1e-300, 1.0)
        entropy = float(-np.sum(w * np.log(w)))
        return FilterDiagnostics(
            n_eff=n_eff,
            unique_count=self.unique_count(position_bin, angle_bin),
            max_weight=max_w,
            entropy=entropy,
            mean_pose=mean,
            tangent_cov=cov,
            collapsed=n_eff < 0.1 * self.n or max_w > 0.5,
            log_likelihood_mean=0.0,
        )
