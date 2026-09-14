"""Declared reductions of a point cloud, with provenance.

A real terrestrial scan is millions of returns covering a whole site, most of
them irrelevant to one clearance case and some of them noise. It has to be
reduced before it can be registered. The question is not whether to filter but
whether the filtering is *stated*.

GAT's position: a transformation that changes what the evidence says is part
of the evidence. Every operation here records its method, its parameters, and
how many points it dropped, and the resulting :class:`FilteredScan` carries
the digest of the cloud it came from as well as its own. A receipt built on
filtered points can therefore name exactly what was discarded and under what
rule -- which is the difference between reducing a scan and quietly improving
it.

Two properties are held deliberately:

*Retained points are measured points.* Voxel reduction keeps one real return
per voxel rather than a centroid of several. A centroid is not a laser return;
it would average sensor noise down by roughly sqrt(n) while the declared
``sensor_sigma`` in the likelihood stayed unchanged, silently overstating
confidence. Keeping a representative return leaves the noise model true.
:func:`voxel_centroid_downsample` offers the averaging variant for callers who
want it, and says in one line why it is not the default.

*Everything is deterministic.* Voxel keys come from integer floor division and
ties break on original index, so the same cloud and parameters always produce
the same points in the same order -- which is what lets the filtered digest
mean anything.

Order matters, and not in the obvious direction
-----------------------------------------------

Downsampling *concentrates* outliers. A dense surface is decimated at roughly
the ratio of its point spacing to the voxel edge, while an isolated return
survives as its own voxel, so the noise fraction rises by the same ratio.
MEASURED on a 460k-point capture with 0.48% clutter after cropping:

    crop -> downsample(0.30 m)          6,443 points, 20.3% clutter
    crop -> clean -> downsample(0.30 m) 4,282 points,  5.7% clutter

and cleaning *after* the downsample removed nothing at all, because at 0.30 m
spacing every point is already its own voxel. On that cloud the wrong order
registered 79 arcmin from truth and the right order 2 arcmin.

So: crop, then remove outliers, then downsample.
:func:`prepare_for_pose` and :func:`prepare_for_measurement` encode that order
and are the intended entry points. :func:`density_outlier_removal` records an
advisory on its own step when it detects that it ran too late to help.

Pose and measurement want different clouds
------------------------------------------

Registration needs sparse coverage over the whole extent; the clearance
measurement needs local density on the face under assessment. Both chains
start from the same source digest, so a receipt can name the one capture that
produced both.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib

import numpy as np

from gat.errors import ScanArtifactError


FILTER_FORMAT = "gat-scan-filter-v1"


def _validated(points: np.ndarray, label: str = "points") -> np.ndarray:
    array = np.asarray(points, dtype=np.float64)
    if array.ndim != 2 or array.shape[1] != 3:
        raise ScanArtifactError(f"{label} must have shape (n, 3)")
    if not np.isfinite(array).all():
        raise ScanArtifactError(f"{label} contain non-finite coordinates")
    return np.ascontiguousarray(array)


def scan_digest(points: np.ndarray) -> str:
    """The same digest the registrar binds evidence to."""
    array = _validated(points)
    digest = hashlib.sha256()
    digest.update(np.asarray(array.shape, dtype="<i8").tobytes())
    digest.update(np.asarray(array, dtype="<f8").tobytes())
    return digest.hexdigest()


@dataclass(frozen=True)
class FilterStep:
    """One declared reduction: what was done, with what, and what it cost.

    ``parameters`` is a dict, so the generated ``__hash__`` raises; hashing by
    the ordered record keeps a step usable as a set member or dict key without
    changing what equality means.
    """

    method: str
    parameters: dict[str, float]
    points_in: int
    points_out: int
    #: Set when a step ran but could not do its job, so the provenance shows
    #: an ineffective filter rather than an apparently clean one.
    advisory: str = ""

    def __post_init__(self) -> None:
        if not self.method.strip():
            raise ValueError("filter step needs a method name")
        if self.points_in < 0 or self.points_out < 0:
            raise ValueError("filter step point counts must be non-negative")
        if self.points_out > self.points_in:
            raise ValueError("a filter step cannot create points")

    @property
    def dropped(self) -> int:
        return self.points_in - self.points_out

    @property
    def retained_fraction(self) -> float:
        return self.points_out / self.points_in if self.points_in else 0.0

    def __hash__(self) -> int:
        return hash(
            (
                self.method,
                tuple(sorted(self.parameters.items())),
                self.points_in,
                self.points_out,
                self.advisory,
            )
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "method": self.method,
            "parameters": dict(sorted(self.parameters.items())),
            "points_in": self.points_in,
            "points_out": self.points_out,
            "dropped": self.dropped,
            "retained_fraction": self.retained_fraction,
            "advisory": self.advisory,
        }


@dataclass(frozen=True, eq=False)
class FilteredScan:
    """Reduced points, bound to the cloud they were reduced from.

    ``eq=False``: the generated ``__eq__`` compares the point arrays with
    ``==``, which raises on anything but a one-element cloud. Identity is what
    this type has a digest for, so equality is digest equality and a scan is
    hashable by it.
    """

    points: np.ndarray
    source_digest: str
    steps: tuple[FilterStep, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        # Copy before freezing. ``_validated`` returns the caller's own array
        # unchanged when it is already float64 and contiguous, so freezing in
        # place made *their* cloud permanently read-only -- filtering a
        # capture must not confiscate it.
        array = np.array(_validated(self.points, "filtered points"), copy=True)
        array.setflags(write=False)
        object.__setattr__(self, "points", array)
        if not self.source_digest:
            raise ValueError("a filtered scan must name its source digest")

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, FilteredScan):
            return NotImplemented
        return (
            self.digest == other.digest
            and self.source_digest == other.source_digest
            and self.steps == other.steps
        )

    def __hash__(self) -> int:
        return hash((self.digest, self.source_digest, self.steps))

    @property
    def digest(self) -> str:
        """Digest of the filtered cloud -- what the registrar will bind to."""
        return scan_digest(self.points)

    @property
    def point_count(self) -> int:
        return int(self.points.shape[0])

    @property
    def source_point_count(self) -> int:
        return self.steps[0].points_in if self.steps else self.point_count

    @property
    def retained_fraction(self) -> float:
        source = self.source_point_count
        return self.point_count / source if source else 0.0

    def then(self, step: FilterStep, points: np.ndarray) -> "FilteredScan":
        return FilteredScan(points, self.source_digest, self.steps + (step,))

    def to_dict(self) -> dict[str, object]:
        """The provenance record: what this cloud is, and what it used to be."""
        return {
            "format": FILTER_FORMAT,
            "source_digest": self.source_digest,
            "filtered_digest": self.digest,
            "source_point_count": self.source_point_count,
            "point_count": self.point_count,
            "retained_fraction": self.retained_fraction,
            "steps": [step.to_dict() for step in self.steps],
        }

    def render(self) -> str:
        lines = [
            f"SCAN FILTER  {self.source_point_count} -> {self.point_count} points "
            f"({self.retained_fraction:.4%} retained)",
            f"  source   {self.source_digest[:16]}...",
            f"  filtered {self.digest[:16]}...",
        ]
        for step in self.steps:
            params = ", ".join(f"{k}={v:g}" for k, v in sorted(step.parameters.items()))
            lines.append(
                f"  {step.method}({params}): {step.points_in} -> {step.points_out}"
                f", dropped {step.dropped}"
            )
        return "\n".join(lines)


def begin(points: np.ndarray) -> FilteredScan:
    """Start a filter chain from an unreduced cloud."""
    array = _validated(points)
    return FilteredScan(array, scan_digest(array))


# -- voxel keys -------------------------------------------------------------


def _voxel_keys(points: np.ndarray, voxel_m: float) -> tuple[np.ndarray, np.ndarray]:
    """Integer voxel index per point, and the grid origin used.

    The origin is the cloud's own minimum corner, so keys do not depend on
    where the building sits in world coordinates.
    """
    origin = points.min(axis=0)
    keys = np.floor((points - origin) / voxel_m).astype(np.int64)
    return keys, origin


def _require_positive(value: float, name: str) -> float:
    value = float(value)
    if not np.isfinite(value) or value <= 0.0:
        raise ScanArtifactError(f"{name} must be finite and positive")
    return value


# -- operations -------------------------------------------------------------


def voxel_downsample(scan: FilteredScan, voxel_m: float) -> FilteredScan:
    """Keep one real return per occupied voxel.

    The kept point is the one closest to its voxel's centre, ties broken by
    original index, so the result is deterministic and every retained point is
    a measurement rather than an average of several.
    """
    voxel_m = _require_positive(voxel_m, "voxel_m")
    points = scan.points
    if points.shape[0] == 0:
        return scan.then(
            FilterStep("voxel_downsample", {"voxel_m": voxel_m}, 0, 0), points
        )

    keys, origin = _voxel_keys(points, voxel_m)
    centres = origin + (keys.astype(np.float64) + 0.5) * voxel_m
    offset = np.einsum("ij,ij->i", points - centres, points - centres)

    # Sort by voxel, then by distance to centre, then by original index; the
    # first row of each voxel group is the representative.
    order = np.lexsort((np.arange(points.shape[0]), offset, keys[:, 2], keys[:, 1], keys[:, 0]))
    sorted_keys = keys[order]
    first = np.ones(sorted_keys.shape[0], dtype=bool)
    if sorted_keys.shape[0] > 1:
        first[1:] = np.any(sorted_keys[1:] != sorted_keys[:-1], axis=1)
    kept = np.sort(order[first])  # restore original acquisition order
    out = np.ascontiguousarray(points[kept])
    return scan.then(
        FilterStep(
            "voxel_downsample", {"voxel_m": voxel_m}, points.shape[0], out.shape[0]
        ),
        out,
    )


def voxel_centroid_downsample(scan: FilteredScan, voxel_m: float) -> FilteredScan:
    """Replace each occupied voxel with the centroid of its points.

    Averaging reduces sensor noise by roughly sqrt(n) per voxel, but the
    likelihood's declared ``sensor_sigma`` does not know that, so the
    resulting confidence is overstated unless the caller lowers it to match.
    :func:`voxel_downsample` is the default for that reason.
    """
    voxel_m = _require_positive(voxel_m, "voxel_m")
    points = scan.points
    if points.shape[0] == 0:
        return scan.then(
            FilterStep("voxel_centroid_downsample", {"voxel_m": voxel_m}, 0, 0), points
        )

    keys, _ = _voxel_keys(points, voxel_m)
    _, inverse, counts = np.unique(keys, axis=0, return_inverse=True, return_counts=True)
    inverse = inverse.reshape(-1)
    sums = np.zeros((counts.shape[0], 3), dtype=np.float64)
    np.add.at(sums, inverse, points)
    out = np.ascontiguousarray(sums / counts[:, None])
    return scan.then(
        FilterStep(
            "voxel_centroid_downsample",
            {"voxel_m": voxel_m},
            points.shape[0],
            out.shape[0],
        ),
        out,
    )


def crop_to_bounds(
    scan: FilteredScan,
    lower: tuple[float, float, float],
    upper: tuple[float, float, float],
    margin_m: float = 0.0,
) -> FilteredScan:
    """Keep returns inside a declared box.

    A site scan covers far more than the element under assessment. Cropping to
    the model's extent plus a margin is usually the largest single reduction,
    and unlike the statistical filters it cannot discard a genuine defect that
    lies inside the region of interest.
    """
    lo = np.asarray(lower, dtype=np.float64) - margin_m
    hi = np.asarray(upper, dtype=np.float64) + margin_m
    if lo.shape != (3,) or hi.shape != (3,):
        raise ScanArtifactError("crop bounds must be 3-vectors")
    if not np.isfinite(lo).all() or not np.isfinite(hi).all():
        raise ScanArtifactError("crop bounds must be finite")
    if np.any(hi < lo):
        raise ScanArtifactError("crop upper bound is below its lower bound")

    points = scan.points
    inside = np.all((points >= lo) & (points <= hi), axis=1)
    out = np.ascontiguousarray(points[inside])
    return scan.then(
        FilterStep(
            "crop_to_bounds",
            {
                "margin_m": float(margin_m),
                "lower_x": float(lo[0]), "lower_y": float(lo[1]), "lower_z": float(lo[2]),
                "upper_x": float(hi[0]), "upper_y": float(hi[1]), "upper_z": float(hi[2]),
            },
            points.shape[0],
            out.shape[0],
        ),
        out,
    )


def range_gate(
    scan: FilteredScan,
    origin: tuple[float, float, float],
    max_range_m: float,
    min_range_m: float = 0.0,
) -> FilteredScan:
    """Drop returns outside a declared standoff band from the scanner.

    Terrestrial LiDAR noise grows with range and near returns can be
    saturated, so an instrument's usable band is part of its calibration
    rather than a property of the building.
    """
    max_range_m = _require_positive(max_range_m, "max_range_m")
    min_range_m = float(min_range_m)
    if not np.isfinite(min_range_m) or min_range_m < 0.0:
        raise ScanArtifactError("min_range_m must be finite and non-negative")
    if min_range_m >= max_range_m:
        raise ScanArtifactError("min_range_m must be below max_range_m")

    station = np.asarray(origin, dtype=np.float64)
    if station.shape != (3,) or not np.isfinite(station).all():
        raise ScanArtifactError("range gate origin must be a finite 3-vector")

    points = scan.points
    distance = np.linalg.norm(points - station, axis=1)
    inside = (distance >= min_range_m) & (distance <= max_range_m)
    out = np.ascontiguousarray(points[inside])
    return scan.then(
        FilterStep(
            "range_gate",
            {
                "min_range_m": min_range_m,
                "max_range_m": max_range_m,
                "origin_x": float(station[0]),
                "origin_y": float(station[1]),
                "origin_z": float(station[2]),
            },
            points.shape[0],
            out.shape[0],
        ),
        out,
    )


def density_outlier_removal(
    scan: FilteredScan,
    radius_m: float,
    min_neighbours: int,
) -> FilteredScan:
    """Drop returns with too few companions within a radius.

    Isolated returns are the signature of mixed pixels, birds, dust and
    retro-reflection artifacts. Implemented over the voxel grid rather than a
    kd-tree: a point is scored by the population of its own voxel and the 26
    around it, with the voxel edge set to ``radius_m``, so the counted
    neighbourhood contains the true radius ball and cost stays linear.

    That makes the filter *conservative*: it over-counts neighbours slightly
    and therefore keeps some points a strict radius search would drop. For a
    filter that discards evidence, erring toward keeping is the right
    direction.
    """
    radius_m = _require_positive(radius_m, "radius_m")
    if min_neighbours < 0:
        raise ScanArtifactError("min_neighbours must be non-negative")

    points = scan.points
    parameters = {"radius_m": radius_m, "min_neighbours": float(min_neighbours)}
    if points.shape[0] == 0:
        return scan.then(
            FilterStep("density_outlier_removal", parameters, 0, 0), points
        )

    keys, _ = _voxel_keys(points, radius_m)
    # Encode the 3-D voxel index as one int64 so the 27-cell block sum is a
    # sorted-array lookup rather than a per-voxel dictionary probe. Keys are
    # non-negative by construction (the grid origin is the cloud minimum) and
    # padded by one so a -1 shift cannot wrap.
    keys = keys + 1
    dims = keys.max(axis=0) + 2
    if int(np.prod(dims.astype(object))) > np.iinfo(np.int64).max:
        raise ScanArtifactError(
            "radius_m is too small for this cloud's extent to index"
        )
    strides = np.array([dims[1] * dims[2], dims[2], 1], dtype=np.int64)
    encoded = keys @ strides

    unique, inverse, counts = np.unique(
        encoded, return_inverse=True, return_counts=True
    )
    inverse = inverse.reshape(-1)

    block = np.zeros(unique.shape[0], dtype=np.int64)
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            for dz in (-1, 0, 1):
                shift = dx * strides[0] + dy * strides[1] + dz * strides[2]
                neighbour = unique + shift
                position = np.searchsorted(unique, neighbour)
                position = np.clip(position, 0, unique.shape[0] - 1)
                hit = unique[position] == neighbour
                block += np.where(hit, counts[position], 0)

    # Exclude the point itself from its own neighbour count.
    neighbours = block[inverse] - 1
    keep = neighbours >= min_neighbours
    out = np.ascontiguousarray(points[keep])

    # If the typical point has no neighbours at all, the cloud is already
    # sparser than the radius and this filter cannot tell an isolated return
    # from a surface one. That happens when it runs AFTER an aggressive
    # downsample -- see the ordering note in this module's docstring.
    median_neighbours = float(np.median(neighbours)) if neighbours.size else 0.0
    advisory = ""
    if median_neighbours < min_neighbours:
        advisory = (
            f"cloud is sparser than radius_m={radius_m:g} (median neighbours "
            f"{median_neighbours:g} < min_neighbours {min_neighbours}); this "
            "filter cannot discriminate here. Run it before downsampling."
        )
    parameters["median_neighbours"] = median_neighbours
    return scan.then(
        FilterStep(
            "density_outlier_removal",
            parameters,
            points.shape[0],
            out.shape[0],
            advisory,
        ),
        out,
    )


def _crop_requested(
    lower: tuple[float, float, float] | None,
    upper: tuple[float, float, float] | None,
) -> bool:
    """Whether to crop, refusing a half-declared box.

    Requiring both and silently skipping on one meant an ``upper`` that came
    back ``None`` from an optional scene lookup produced a full-extent capture
    whose provenance record showed no crop at all -- a reduction that did not
    happen, recorded as though none was asked for. In a module whose contract
    is that a transformation which changes what the evidence says is part of
    the evidence, a silent no-op is the one outcome not allowed.
    """
    if (lower is None) != (upper is None):
        missing = "upper" if upper is None else "lower"
        raise ScanArtifactError(
            f"a crop needs both bounds; {missing} is missing. Pass both to "
            "crop, or neither to declare that the capture was not cropped"
        )
    return lower is not None


def prepare_for_pose(
    points: np.ndarray,
    lower: tuple[float, float, float] | None = None,
    upper: tuple[float, float, float] | None = None,
    *,
    margin_m: float = 1.0,
    clean_radius_m: float = 0.15,
    min_neighbours: int = 6,
    voxel_m: float = 0.30,
) -> FilteredScan:
    """Reduce a capture to what registration needs: coverage, not density.

    Crop, then clean, then downsample -- the order the module docstring
    measures. The defaults suit a terrestrial scan of a storey; a coarser
    ``voxel_m`` trades registration cost against pose precision.
    """
    chain = begin(points)
    if _crop_requested(lower, upper):
        chain = crop_to_bounds(chain, lower, upper, margin_m)
    chain = density_outlier_removal(chain, clean_radius_m, min_neighbours)
    return voxel_downsample(chain, voxel_m)


def prepare_for_measurement(
    points: np.ndarray,
    lower: tuple[float, float, float] | None = None,
    upper: tuple[float, float, float] | None = None,
    *,
    margin_m: float = 0.5,
    clean_radius_m: float = 0.15,
    min_neighbours: int = 6,
    voxel_m: float = 0.05,
) -> FilteredScan:
    """Reduce a capture to what the clearance measurement needs.

    The same order and the same source digest as :func:`prepare_for_pose`,
    but a fine voxel: a face measurement wants the returns on that face, and
    a local as-built defect is exactly what coarse downsampling would erase.
    """
    chain = begin(points)
    if _crop_requested(lower, upper):
        chain = crop_to_bounds(chain, lower, upper, margin_m)
    chain = density_outlier_removal(chain, clean_radius_m, min_neighbours)
    return voxel_downsample(chain, voxel_m)


__all__ = [
    "FILTER_FORMAT",
    "FilterStep",
    "FilteredScan",
    "begin",
    "crop_to_bounds",
    "density_outlier_removal",
    "prepare_for_measurement",
    "prepare_for_pose",
    "range_gate",
    "scan_digest",
    "voxel_centroid_downsample",
    "voxel_downsample",
]
