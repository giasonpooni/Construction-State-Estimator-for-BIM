"""Binary occupancy grid used as a known floor-plate prior.

This is a BIM *slice*: axis-aligned wall segments rasterized at a declared
resolution. It is not a solid IFC adapter and does not upgrade geometry
authority. Occupied cells block rays. Free cells are valid particle support.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class WallSegment:
    x0: float
    y0: float
    x1: float
    y1: float
    thickness: float = 0.15


@dataclass(frozen=True)
class OccupancyGrid:
    origin: tuple[float, float]
    resolution: float
    occupied: np.ndarray  # (H, W) uint8, 1 = occupied

    @property
    def height(self) -> int:
        return int(self.occupied.shape[0])

    @property
    def width(self) -> int:
        return int(self.occupied.shape[1])

    def world_to_cell(self, x: float, y: float) -> tuple[int, int]:
        col = int(np.floor((x - self.origin[0]) / self.resolution))
        row = int(np.floor((y - self.origin[1]) / self.resolution))
        return row, col

    def in_bounds(self, row: int, col: int) -> bool:
        return 0 <= row < self.height and 0 <= col < self.width

    def is_occupied(self, x: float, y: float) -> bool:
        row, col = self.world_to_cell(x, y)
        if not self.in_bounds(row, col):
            return True
        return bool(self.occupied[row, col])

    def is_free(self, x: float, y: float) -> bool:
        row, col = self.world_to_cell(x, y)
        if not self.in_bounds(row, col):
            return False
        return self.occupied[row, col] == 0

    def raycast(self, x: float, y: float, heading: float, max_range: float) -> float:
        """Step along the ray until an occupied or out-of-bounds cell."""
        step = 0.5 * self.resolution
        n = int(np.ceil(max_range / step))
        c, s = float(np.cos(heading)), float(np.sin(heading))
        for i in range(1, n + 1):
            t = i * step
            if self.is_occupied(x + t * c, y + t * s):
                return min(t, max_range)
        return max_range


def rasterize(walls: tuple[WallSegment, ...], origin: tuple[float, float],
              size: tuple[float, float], resolution: float) -> OccupancyGrid:
    width = int(np.ceil(size[0] / resolution))
    height = int(np.ceil(size[1] / resolution))
    occ = np.zeros((height, width), dtype=np.uint8)
    for wall in walls:
        _stamp_segment(occ, origin, resolution, wall)
    occ.setflags(write=False)
    return OccupancyGrid(origin=origin, resolution=resolution, occupied=occ)


def _stamp_segment(occ: np.ndarray, origin: tuple[float, float],
                   resolution: float, wall: WallSegment) -> None:
    length = math_hypot(wall.x1 - wall.x0, wall.y1 - wall.y0)
    if length <= 0.0:
        return
    n = max(2, int(np.ceil(length / (0.5 * resolution))))
    half = 0.5 * wall.thickness
    ux = (wall.x1 - wall.x0) / length
    uy = (wall.y1 - wall.y0) / length
    nx, ny = -uy, ux
    height, width = occ.shape
    for i in range(n + 1):
        t = i / n
        cx = wall.x0 + t * (wall.x1 - wall.x0)
        cy = wall.y0 + t * (wall.y1 - wall.y0)
        for s in (-half, 0.0, half):
            x, y = cx + s * nx, cy + s * ny
            col = int(np.floor((x - origin[0]) / resolution))
            row = int(np.floor((y - origin[1]) / resolution))
            if 0 <= row < height and 0 <= col < width:
                occ[row, col] = 1


def math_hypot(a: float, b: float) -> float:
    return float(np.hypot(a, b))


def free_cells(grid: OccupancyGrid) -> np.ndarray:
    rows, cols = np.nonzero(grid.occupied == 0)
    xs = grid.origin[0] + (cols + 0.5) * grid.resolution
    ys = grid.origin[1] + (rows + 0.5) * grid.resolution
    return np.stack([xs, ys], axis=1)
