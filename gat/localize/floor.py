"""Two-room corridor floor plate used as the MCL demonstrator.

Rooms A and B are geometrically similar. Global localization can remain
multimodal until the robot travels far enough for the doorway sequence
to break the symmetry. That is the observability point of the demo.
"""

from __future__ import annotations

from gat.localize.occupancy import OccupancyGrid, WallSegment, rasterize


def two_room_walls() -> tuple[WallSegment, ...]:
    t = 0.20
    # Outer envelope 12m x 6m.
    outer = (
        WallSegment(0.0, 0.0, 12.0, 0.0, t),
        WallSegment(0.0, 6.0, 12.0, 6.0, t),
        WallSegment(0.0, 0.0, 0.0, 6.0, t),
        WallSegment(12.0, 0.0, 12.0, 6.0, t),
    )
    # Mid wall with a 1.2m doorway centered at y=3.
    mid = (
        WallSegment(6.0, 0.0, 6.0, 2.4, t),
        WallSegment(6.0, 3.6, 6.0, 6.0, t),
    )
    return outer + mid


def two_room_grid(resolution: float = 0.05) -> OccupancyGrid:
    return rasterize(two_room_walls(), origin=(-0.3, -0.3), size=(12.6, 6.6), resolution=resolution)


def room_a_pose() -> tuple[float, float, float]:
    return (3.0, 3.0, 0.0)


def room_b_pose() -> tuple[float, float, float]:
    return (9.0, 3.0, 0.0)


def corridor_path() -> tuple[tuple[float, float, float], ...]:
    """Ground-truth poses walking from room A through the door into B."""
    return (
        (3.0, 3.0, 0.0),
        (4.0, 3.0, 0.0),
        (5.0, 3.0, 0.0),
        (5.7, 3.0, 0.0),
        (6.4, 3.0, 0.0),
        (7.5, 3.0, 0.0),
        (9.0, 3.0, 0.0),
    )
