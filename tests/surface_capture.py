"""A terrestrial laser scan of the shipped model, for tests that need one.

Every scan in this repository until now came from
:func:`gat.geometry.registration.synthesize_scan`, which draws points *from
the model's own Gaussian mixture* -- that is, from the volume the elements
fill.  It is the right instrument for testing the estimator against its own
likelihood, and it is not what a scanner produces.  A scanner produces
returns from the surfaces it can see, from where it stood, and the two
differ in a way that shows up in the pose: see
:mod:`tests.test_surface_capture_chain`.

What this simulates, and why each part is here:

* **Occlusion.** Rays are cast from a station and stop at the first surface,
  so a face behind a wall contributes nothing. Density therefore varies with
  what each station could see, not with element size.
* **Range-dependent noise.** Ranging error grows with distance; a far wall is
  measured worse than a near one, and the returns on one face are not
  identically distributed.
* **Mixed pixels.** A beam straddling a depth discontinuity reports a range
  between the two surfaces, placing a return in empty space along the edge.
* **Clutter.** Furniture and a person are in the capture and not in the BIM.
* **Stray returns.** A few ghosts from atmospheric and retro-reflective
  effects, unrelated to any surface.

Deterministic: every station takes an explicit seed and there are no
unstable sorts.
"""

from __future__ import annotations

import math

import numpy as np

from gat.geometry.stateio import rot_z

#: A station is blind past this; returns beyond it are dropped.
MAX_RANGE_M = 40.0


def slab(
    origin: tuple[float, float, float],
    angle: float,
    extents: tuple[float, float, float],
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """An oriented box as (centre, rotation, half-extents) for ray casting."""
    rotation = rot_z(angle)
    half = 0.5 * np.asarray(extents, dtype=np.float64)
    centre = np.asarray(origin, dtype=np.float64) + rotation @ half
    return centre, rotation, half


def scene_slabs(scene) -> list[tuple[np.ndarray, np.ndarray, np.ndarray]]:
    """Every element of a :class:`GeometryScene` as a castable slab."""
    return [
        slab(element.box.origin, element.box.angle, element.box.extents)
        for element in scene.elements
    ]


def _ray_slab(
    origin: np.ndarray,
    directions: np.ndarray,
    box: tuple[np.ndarray, np.ndarray, np.ndarray],
) -> np.ndarray:
    """Distance to the first surface of one box along each ray, else ``inf``.

    A station inside a box -- which is the normal case here, since the model
    represents rooms as solid elements and the scanner stands in one -- sees
    that box's *exit* face, which is the inside surface of the room. A box
    ahead of the station is seen at its entry face. Taking the minimum over
    boxes then gives the nearest visible surface, which is the occlusion.
    """
    centre, rotation, half = box
    station = rotation.T @ (origin - centre)
    local = directions @ rotation
    with np.errstate(divide="ignore", invalid="ignore"):
        inverse = 1.0 / local
        near = (-half - station) * inverse
        far = (half - station) * inverse
    entry = np.maximum.reduce(np.minimum(near, far), axis=1)
    exit_ = np.minimum.reduce(np.maximum(near, far), axis=1)
    hit = (exit_ >= np.maximum(entry, 0.0)) & np.isfinite(entry)
    distance = np.where(hit, np.where(entry > 0.0, entry, exit_), np.inf)
    return np.where(distance > 0.0, distance, np.inf)


def capture_station(
    boxes,
    station: tuple[float, float, float],
    *,
    seed: int,
    n_azimuth: int = 300,
    n_elevation: int = 56,
    sigma_0_m: float = 0.004,
    sigma_per_m: float = 0.0009,
    mixed_pixel_fraction: float = 0.004,
    stray_fraction: float = 0.0015,
) -> np.ndarray:
    """One station's returns, in the model frame."""
    rng = np.random.default_rng(seed)
    azimuth = np.linspace(0.0, 2.0 * math.pi, n_azimuth, endpoint=False)
    elevation = np.linspace(math.radians(-38.0), math.radians(42.0), n_elevation)
    grid_a, grid_e = np.meshgrid(azimuth, elevation, indexing="ij")
    grid_a, grid_e = grid_a.ravel(), grid_e.ravel()
    directions = np.column_stack(
        [
            np.cos(grid_e) * np.cos(grid_a),
            np.cos(grid_e) * np.sin(grid_a),
            np.sin(grid_e),
        ]
    )

    origin = np.asarray(station, dtype=np.float64)
    distance = np.full(directions.shape[0], np.inf)
    for box in boxes:
        distance = np.minimum(distance, _ray_slab(origin, directions, box))

    visible = np.isfinite(distance) & (distance < MAX_RANGE_M)
    distance, directions = distance[visible].copy(), directions[visible]
    if distance.size == 0:
        raise ValueError("station sees nothing")

    # Mixed pixels sit at depth discontinuities, so pick the rays whose range
    # jumps hardest against their neighbour and pull them short.
    count = max(1, int(mixed_pixel_fraction * distance.size))
    jump = np.abs(np.diff(distance, prepend=distance[0]))
    edges = np.argsort(jump, kind="stable")[-4 * count:]
    chosen = rng.choice(edges, size=min(count, edges.size), replace=False)
    distance[chosen] *= rng.uniform(0.35, 0.9, chosen.size)

    distance = distance + rng.normal(0.0, sigma_0_m + sigma_per_m * distance)
    points = origin + directions * distance[:, None]

    ghosts = int(stray_fraction * points.shape[0])
    stray = origin + rng.normal(0.0, 1.0, (ghosts, 3)) * rng.uniform(
        1.0, 25.0, (ghosts, 1)
    )
    return np.vstack([points, stray])


def write_ply(path, points: np.ndarray) -> None:
    """Binary little-endian float32 PLY -- what a scanner actually exports."""
    points = np.asarray(points)
    header = (
        "ply\nformat binary_little_endian 1.0\n"
        f"element vertex {points.shape[0]}\n"
        "property float x\nproperty float y\nproperty float z\n"
        "end_header\n"
    ).encode("ascii")
    with open(path, "wb") as handle:
        handle.write(header)
        handle.write(np.asarray(points, dtype="<f4").tobytes())
