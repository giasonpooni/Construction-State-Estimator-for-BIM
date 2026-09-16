"""Scan residual given a pose and a known occupancy slice.

This is the measurement morphism. The particle filter consumes the
likelihood of the residual; a later i32 guest may consume the residual
itself. A low residual at a pose is not field evidence that the BIM
dimensions are correct — see gat.geometry.scan_likelihood.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from gat.localize.occupancy import OccupancyGrid


@dataclass(frozen=True)
class Scan:
    angles: np.ndarray  # body-frame bearings
    ranges: np.ndarray
    max_range: float

    def __post_init__(self) -> None:
        angles = np.asarray(self.angles, dtype=np.float64)
        ranges = np.asarray(self.ranges, dtype=np.float64)
        if angles.shape != ranges.shape:
            raise ValueError("scan angles and ranges must match")
        if not np.isfinite(angles).all() or not np.isfinite(ranges).all():
            raise ValueError("scan must be finite")
        if not np.isfinite(self.max_range) or self.max_range <= 0.0:
            raise ValueError("max_range must be positive")
        object.__setattr__(self, "angles", angles)
        object.__setattr__(self, "ranges", ranges)


def predicted_ranges(pose: np.ndarray, angles: np.ndarray, grid: OccupancyGrid,
                     max_range: float) -> np.ndarray:
    x, y, th = float(pose[0]), float(pose[1]), float(pose[2])
    out = np.empty(angles.shape, dtype=np.float64)
    for i, a in enumerate(angles):
        out[i] = grid.raycast(x, y, th + float(a), max_range)
    return out


def residual(pose: np.ndarray, scan: Scan, grid: OccupancyGrid) -> np.ndarray:
    zhat = predicted_ranges(pose, scan.angles, grid, scan.max_range)
    r = scan.ranges - zhat
    both_max = (scan.ranges >= scan.max_range - 1e-9) & (zhat >= scan.max_range - 1e-9)
    r = np.where(both_max, 0.0, r)
    return r


def log_likelihood(res: np.ndarray, sigma: float) -> float:
    if not np.isfinite(sigma) or sigma <= 0.0:
        raise ValueError("sigma must be positive")
    return float(-0.5 * np.dot(res, res) / (sigma * sigma))


def synthesize_scan(pose: np.ndarray, grid: OccupancyGrid, angles: np.ndarray,
                    max_range: float, sigma: float, rng: np.random.Generator) -> Scan:
    zhat = predicted_ranges(pose, angles, grid, max_range)
    noise = rng.normal(0.0, sigma, size=zhat.shape)
    ranges = np.clip(zhat + noise, 0.0, max_range)
    return Scan(angles=np.asarray(angles, dtype=np.float64), ranges=ranges, max_range=max_range)
