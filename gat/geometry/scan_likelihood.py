"""Calibrated scan-to-clearance likelihood adapter.

Registration answers whether scan points can be associated with the
Gaussian BIM field.  It must not also provide the pose used to claim that
the BIM dimensions are wrong: doing so would feed a model-derived alignment
back as apparently independent evidence about that same model.

This adapter therefore requires an independently calibrated model-from-scan
pose (survey control or a separately calibrated SLAM trajectory).  An
accepted registration is retained only as a fit/association gate.  For the
element and separating direction selected by clearance assurance it:

* extracts responsibility-weighted points near the controlling support face,
* rejects weak, ambiguous, clustered, or non-planar support,
* estimates the support coordinate and decomposes sampling, pose, and
  systematic calibration variance,
* checks pose agreement and the normalized measurement innovation, and
* emits a provenance-bound :class:`~gat.engine.transform.ObserveLinearized`.

The returned transformation still enters the ordinary
condition -> propagate -> verify -> commit/rollback pipeline.  No function
in this module mutates canonical BIM state directly.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import math

import numpy as np

from gat.engine.transform import ObserveLinearized
from gat.errors import LikelihoodCalibrationError
from gat.geometry.assurance import (
    ClearanceEvidencePlan,
    InspectionAction,
)
from gat.geometry.registration import (
    RegistrationResult,
    RigidTransformZ,
    ScanEvidenceReport,
    ScanRegistrar,
)
from gat.geometry.stateio import (
    GeometryScene,
    SceneElement,
    rot_z,
    support_radius,
)


@dataclass(frozen=True)
class IndependentPoseCalibration:
    """Externally sourced model-from-scan pose and covariance.

    ``covariance`` is ordered ``(yaw, tx, ty, tz)``.  ``source_id`` must
    identify the survey control, calibrated SLAM trajectory, or equivalent
    provenance; a registration fit against this BIM is not independent.
    """

    transform: RigidTransformZ
    covariance: np.ndarray
    scan_digest: str
    source_id: str

    def __post_init__(self) -> None:
        values = (self.transform.theta, *self.transform.t)
        if not np.isfinite(values).all():
            raise ValueError("independent pose must be finite")
        covariance = np.asarray(self.covariance, dtype=np.float64)
        if covariance.shape != (4, 4) or not np.isfinite(covariance).all():
            raise ValueError("independent pose covariance must be finite 4x4")
        if not np.allclose(covariance, covariance.T, atol=1e-12, rtol=0.0):
            raise ValueError("independent pose covariance must be symmetric")
        if float(np.linalg.eigvalsh(covariance).min()) <= 0.0:
            raise ValueError("independent pose covariance must be positive definite")
        if not self.scan_digest or not self.source_id.strip():
            raise ValueError("independent pose provenance must be non-empty")
        copied = covariance.copy()
        copied.setflags(write=False)
        object.__setattr__(self, "covariance", copied)


@dataclass(frozen=True)
class ClearanceLikelihoodCalibration:
    """Declared physical noise model and evidence acceptance gates."""

    sensor_sigma: float = 0.010
    calibration_sigma: float = 0.005
    face_band: float = 0.060
    min_face_effective_points: float = 15.0
    min_tangent_rms: float = 0.100
    #: Fraction of the face's tangential extent that must actually carry
    #: returns.  ``min_tangent_rms`` is a *spread*, and spread is maximized
    #: by putting every point at the two extremes: two 4 mm clusters 3.2 m
    #: apart score 1.60 where a uniformly covered face scores 0.91, so that
    #: gate passes the case its own message names.  Coverage is the
    #: participation ratio over cells of the element's own face: on the demo
    #: wall a sweep along its length reads 0.35, one that crosses the
    #: thickness too reads 0.65, and the two clusters read 0.07.  The default
    #: sits in that gap.  It catches returns that span a face without
    #: sampling it; it is not a completeness check, and half a wall measured
    #: well still reads about 0.21.
    min_face_coverage: float = 0.15
    #: The face's scatter about its own plane, as a multiple of
    #: ``sensor_sigma``.  ``sampling_variance = residual_variance /
    #: face_mass`` is the standard error of a mean, which is only the right
    #: formula when the residual is independent noise; a 45 mm bulge over a
    #: third of the face is structure, and dividing it by the point count
    #: makes a deformed wall look *more* certain the harder you scan it.
    #: This gate makes that premise a checked precondition.  It is only as
    #: tight as the declared sensor: a survey that declares 10 mm when its
    #: instrument delivers 3 mm buys itself a 15 mm tolerance for real
    #: deformation, and the declaration is what it will be held to.
    max_residual_sigma_ratio: float = 1.5
    #: How far the support window may re-centre off the model's prediction
    #: before the measurement is refused rather than reported.  The window
    #: has to move -- pinned to the prediction it truncates a deviated face
    #: and reports a shrunken number -- but a window that has walked a long
    #: way is no longer obviously looking at the face it was asked about.
    #: The default equals ``face_band``: a face further off than the window
    #: is wide is a deviation this instrument was not set up to measure, and
    #: saying so is more use than a number.  Raising it is a deliberate
    #: declaration that the model is expected to be that wrong.
    max_face_recentre: float = 0.060
    #: Share of the settled face's returns that a plane one element
    #: thickness further out may carry.  Above it the window has settled on
    #: the element's far face, which is a clean measurement of the wrong
    #: side of the wall and is invisible to every statistic computed on the
    #: retained returns alone.  Conservative by design: clutter parked
    #: exactly one thickness outward refuses too, and that really is
    #: ambiguous evidence.
    #:
    #: Checked only when the element's support radius exceeds ``face_band``,
    #: so that the rival window is a separate window rather than an overlap
    #: of the face being measured.  Thinner than that and the two faces share
    #: one window, which ``max_residual_sigma_ratio`` catches as scatter.
    max_rival_plane_share: float = 0.25
    min_element_effective_points: float = 25.0
    min_support_diversity: float = 0.50
    min_assignment_confidence: float = 0.80
    min_face_alignment: float = 0.98
    max_pose_disagreement_m2: float = 16.0
    max_innovation_sigma: float = 5.0

    def __post_init__(self) -> None:
        positive = (
            "sensor_sigma",
            "calibration_sigma",
            "face_band",
            "min_face_effective_points",
            "min_tangent_rms",
            "max_residual_sigma_ratio",
            "max_face_recentre",
            "max_rival_plane_share",
            "min_element_effective_points",
            "max_pose_disagreement_m2",
            "max_innovation_sigma",
        )
        for name in positive:
            value = getattr(self, name)
            if not math.isfinite(value) or value <= 0.0:
                raise ValueError(f"{name} must be finite and positive")
        for name in (
            "min_support_diversity",
            "min_assignment_confidence",
            "min_face_alignment",
            "min_face_coverage",
        ):
            value = getattr(self, name)
            if not math.isfinite(value) or not 0.0 < value <= 1.0:
                raise ValueError(f"{name} must be finite and in (0, 1]")


@dataclass(frozen=True)
class ScanClearanceLikelihood:
    """Auditable scalar support-plane likelihood ready for conditioning."""

    element_name: str
    direction: tuple[float, float, float]
    predicted_support: float
    observed_support: float
    effective_face_points: float
    face_assignment_confidence: float
    tangent_rms: float
    #: Occupied fraction of the face's tangential extent, and the face's own
    #: scatter about its fitted plane. Reported whether or not they gate, so
    #: an operator sees a face that only just qualified.
    face_coverage: float
    face_residual_rms: float
    sampling_sigma: float
    pose_sigma: float
    calibration_sigma: float
    noise_sigma: float
    innovation_sigma: float
    pose_disagreement_m2: float
    scan_digest: str
    scene_version: str
    pose_source_id: str
    evidence_digest: str
    observation: ObserveLinearized

    def render(self) -> str:
        return (
            f"scan likelihood {self.element_name}: support "
            f"{self.observed_support:.4f} m (predicted "
            f"{self.predicted_support:.4f} m); noise={self.noise_sigma:.4f} m "
            f"[sampling {self.sampling_sigma:.4f}, pose {self.pose_sigma:.4f}, "
            f"calibration {self.calibration_sigma:.4f}]; "
            f"face_mass={self.effective_face_points:.1f}; "
            f"coverage={self.face_coverage:.3f}; "
            f"flatness={self.face_residual_rms*1000:.1f} mm rms; "
            f"assignment={self.face_assignment_confidence:.3f}; "
            f"innovation={self.innovation_sigma:.3f} sigma"
        )


#: Returns per cell the coverage grid is sized for, and the cell count it is
#: clamped between.  A fixed grid would measure point count as much as
#: clustering: 180 returns in 144 cells cannot fill more than a fraction of
#: them however evenly they fall.  Sizing the grid to the data keeps the
#: statistic about *where* the returns are, which is the question.
COVERAGE_POINTS_PER_CELL = 4.0
COVERAGE_CELL_BOUNDS = (4, 256)


def _on_support_face(
    element: SceneElement,
    direction: np.ndarray,
    points: np.ndarray,
) -> np.ndarray:
    """Boolean mask: returns lying on the support face, not a perpendicular one.

    The support window is one-dimensional -- a band on the projection along
    ``direction`` -- and a box has four faces *perpendicular* to that
    direction whose returns fall inside the band near the far edge. On
    ``gat/demo/model.ifc`` that is 21.3% of the weight: the party wall is
    3.0 m tall and 0.2 m thick, so every return on its sides and ends within
    60 mm of the top counted as a top-face return. They are not scatter about
    the support plane; they are a different plane seen edge-on, and their
    spread is what ``max_residual_sigma_ratio`` was reading. Filtering them
    out takes the demo's support face from 15.08 mm rms to 8.84 mm and moves
    ``observed`` from 6.5 mm below the true top to 1.2 mm below it.

    ``min_face_alignment`` already checks that the *direction* names a face
    rather than an edge or corner. This checks that each *return* does.

    A point is assigned to the box face it is nearest, in the box's own
    frame: for half-extents h and local coordinates x, the distance to the
    face pair on axis i is ``| |x_i| - h_i |``, and the smallest wins. It is
    the same rule a scanner's own geometry obeys -- a return sits on one
    surface -- so it needs no tolerance and no new calibration constant.

    The axis carries *two* faces, and only the one ``direction`` points at
    is the support face; the other is the element's far side. Keeping both
    would put a thin element's two faces in one retained set, which is the
    case ``max_rival_plane_share`` exists to refuse and this would have
    hidden from it. So the sign is checked too.
    """
    rotation = rot_z(element.box.angle)
    half = 0.5 * np.asarray(element.box.extents, dtype=np.float64)
    local = (points - element.box.center()) @ rotation
    to_face = np.abs(np.abs(local) - half)
    aligned = direction @ rotation
    support_axis = int(np.argmax(np.abs(aligned)))
    on_axis = np.argmin(to_face, axis=1) == support_axis
    outward = np.sign(aligned[support_axis])
    return on_axis & (local[:, support_axis] * outward > 0.0)


#: Rounds the support window is allowed to chase the returns. The map
#: centre -> weighted mean of what the centre retains is a mean-shift step
#: with a flat kernel; it converges in a handful of rounds on anything
#: plane-like and oscillates between two clusters on anything that is not.
#: The bound is what turns the second case into a refusal instead of a hang.
SUPPORT_WINDOW_ROUNDS = 12

#: Movement below which the window is called settled, in metres. A hundredth
#: of a millimetre is far inside any sensor this runtime accepts, so this
#: stops the iteration rather than deciding anything.
SUPPORT_WINDOW_TOLERANCE = 1e-5


def _settle_support_window(
    projections: np.ndarray,
    gamma: np.ndarray,
    predicted: float,
    band: float,
) -> tuple[float, float]:
    """Move the support window onto the returns. Returns ``(centre, walked)``.

    Starts at the model's prediction and repeatedly re-centres on the
    weighted mean of what the current window retains -- mean shift with a
    flat kernel. ``walked`` is the total distance from ``predicted``, which
    the caller gates on: it is the estimator's own statement of how far the
    as-built face is from the model, and the one number the pinned window
    could not produce.

    An empty window is left where it is. The caller's effective-point gate
    then refuses it, and it refuses with a count rather than with whatever a
    mean over nothing would have been.
    """
    centre = float(predicted)
    for _ in range(SUPPORT_WINDOW_ROUNDS):
        inside = np.abs(projections - centre) <= band
        mass = float(np.sum(gamma * inside))
        if mass <= 0.0:
            break
        moved = float(np.sum(gamma * inside * projections) / mass)
        if abs(moved - centre) < SUPPORT_WINDOW_TOLERANCE:
            centre = moved
            break
        centre = moved
    return centre, abs(centre - float(predicted))


def _face_coverage(
    element: SceneElement,
    direction: np.ndarray,
    points: np.ndarray,
    weights: np.ndarray,
) -> float:
    """Occupied fraction of the element's face, in [0, 1].

    The participation ratio ``(sum w)^2 / sum w^2`` over cells of the face:
    the effective number of cells the returns occupy, over the number the
    *element's* face spans.  Near one for a face sampled evenly, small for
    two tight clusters at its ends whatever the point count — the case
    ``min_tangent_rms`` rewards, since it measures spread and spread is what
    two extremes maximize — and small for one sweep line, which covers its
    own bounding box completely and the wall barely at all.

    The grid is sized to the return count, so coverage is resolution-limited
    when returns are few: a face carrying the minimum 15 returns is graded
    on a coarse grid, and it is ``min_face_effective_points`` that keeps a
    thin measurement out, not this.
    """
    live = weights > 0.0
    if not np.any(live):
        return 0.0
    mass = weights[live]

    # The face, in the element's own frame: each local axis spans its own
    # extent scaled by how much of it survives the projection onto the plane
    # orthogonal to ``direction``.  This is the denominator; the returns'
    # bounding box will not do, because a single sweep line covers its own
    # box completely and the wall barely at all.
    rotation = rot_z(element.box.angle)
    along = np.abs(direction @ rotation)
    spans = np.asarray(element.box.extents) * np.sqrt(
        np.clip(1.0 - np.square(along), 0.0, 1.0)
    )
    order = np.argsort(spans)[::-1][:2]
    spans, axes = spans[order], rotation[:, order].T
    if spans[0] <= 0.0:
        return 0.0

    # Offsets from the box centre, so the grid is anchored to the element
    # rather than to wherever the returns happened to land.
    offsets = points[live] - element.box.center()

    low, high = COVERAGE_CELL_BOUNDS
    total = int(min(high, max(low, len(offsets) / COVERAGE_POINTS_PER_CELL)))
    # One square cell for both axes, sized so the face yields about ``total``
    # of them.  Square cells keep a 0.2 m wall thickness from being resolved
    # as finely as a 3 m length; sizing by area rather than by the long axis
    # keeps a long thin face from being graded on six cells when hundreds of
    # returns could support fifty.
    size = math.sqrt(spans[0] * spans[1] / total) if spans[1] > 0.0 else 0.0
    if not size > 0.0 or size > spans[1]:
        size = spans[0] / total        # the face is one cell thick: all length
    size = min(size, 0.5 * spans[0])   # never fewer than two cells of length

    cells = 1
    index = np.zeros(len(offsets), dtype=np.int64)
    for axis in range(2):
        count = max(1, int(math.ceil(spans[axis] / size)))
        if count == 1:
            continue
        scaled = (offsets @ axes[axis] + 0.5 * spans[axis]) / size
        index += np.clip(scaled.astype(np.int64), 0, count - 1) * cells
        cells *= count

    occupancy = np.bincount(index, weights=mass)
    squared = float(np.square(occupancy).sum())
    if squared <= 0.0:
        return 0.0
    effective = float(occupancy.sum()) ** 2 / squared
    return float(min(1.0, effective / float(cells)))


def adapt_clearance_likelihood(
    scene: GeometryScene,
    registrar: ScanRegistrar,
    scan: np.ndarray,
    registration: RegistrationResult,
    evidence: ScanEvidenceReport,
    plan: ClearanceEvidencePlan,
    pose: IndependentPoseCalibration,
    calibration: ClearanceLikelihoodCalibration = ClearanceLikelihoodCalibration(),
) -> ScanClearanceLikelihood:
    """Extract and calibrate the selected clearance support-plane evidence.

    Every input is provenance-bound.  Failure of any declared gate raises
    :class:`LikelihoodCalibrationError`; it never degrades silently to an
    update with inflated but untraceable uncertainty.
    """
    scene.check_fresh(scene.world)
    selected = plan.selected
    if selected is None or selected.action is not InspectionAction.EXTRACT_SCAN_MEASUREMENT:
        raise LikelihoodCalibrationError(
            "clearance plan does not authorize scan measurement extraction"
        )
    if plan.assessment.scene_version != scene.version:
        raise LikelihoodCalibrationError(
            "clearance plan belongs to a different canonical scene"
        )
    if evidence.scene_version != scene.version or registration.scene_version != scene.version:
        raise LikelihoodCalibrationError(
            "scan evidence, registration, and canonical scene versions differ"
        )
    if not registration.accepted:
        # ``accepted`` is documented as the fit-quality gate for any
        # write-back, and nothing downstream read it. A pose that failed its
        # own gate cannot place a measurement on an element.
        raise LikelihoodCalibrationError(
            "registration was not accepted"
            + (f": {registration.refusal}" if registration.refusal else "")
        )
    if not (
        plan.scan_digest
        == evidence.scan_digest
        == registration.scan_digest
        == pose.scan_digest
    ):
        raise LikelihoodCalibrationError(
            "scan, evidence plan, registration, and independent pose digests differ"
        )

    points = np.asarray(scan, dtype=np.float64)
    if evidence.point_count != points.shape[0]:
        raise LikelihoodCalibrationError(
            "scan evidence point count differs from the supplied scan"
        )
    element = scene.element_by_name(selected.element_name)
    evidence_rows = [
        row
        for row in evidence.elements
        if row.element_name == element.name and row.element_row == element.row
    ]
    if len(evidence_rows) != 1:
        raise LikelihoodCalibrationError(
            f"expected one evidence row for {element.name}, found {len(evidence_rows)}"
        )
    element_evidence = evidence_rows[0]
    if element_evidence.effective_points < calibration.min_element_effective_points:
        raise LikelihoodCalibrationError("element evidence has insufficient effective points")
    if element_evidence.support_diversity < calibration.min_support_diversity:
        raise LikelihoodCalibrationError("element evidence has insufficient support diversity")
    if element_evidence.assignment_confidence < calibration.min_assignment_confidence:
        raise LikelihoodCalibrationError("element evidence assignment is ambiguous")

    direction = np.asarray(selected.direction, dtype=np.float64)
    direction_norm = float(np.linalg.norm(direction))
    if not np.isfinite(direction).all() or direction_norm <= 0.0:
        raise LikelihoodCalibrationError("clearance direction must be finite and nonzero")
    direction = direction / direction_norm
    R_element = rot_z(element.box.angle)
    face_alignment = float(np.max(np.abs(direction @ R_element)))
    if face_alignment < calibration.min_face_alignment:
        raise LikelihoodCalibrationError(
            "clearance support is an edge/corner, not a calibrated element face"
        )

    pose_m2 = _pose_disagreement_m2(registration, pose)
    if pose_m2 > calibration.max_pose_disagreement_m2:
        raise LikelihoodCalibrationError(
            f"independent pose disagrees with registration (m2={pose_m2:.3f})"
        )

    posterior = registrar.posterior_at(scan, registration, pose.transform)
    primitive_mask = registrar.element_index == element.row
    if not np.any(primitive_mask):
        raise LikelihoodCalibrationError("selected element has no registration primitives")
    target_gamma = posterior.responsibilities[:, primitive_mask].sum(axis=1)

    center = element.box.center()
    radius = support_radius(element, direction)
    predicted = float(direction @ center + radius)
    projections = posterior.model_points @ direction

    # The support window used to sit on ``predicted`` -- the BIM's own answer
    # to the question being asked -- and never move. A face at predicted +
    # delta is then one-side truncated by it, so ``observed`` is pulled back
    # toward the model. Measured on the truncated normal at the shipped
    # 60 mm band and 10 mm sensor: a true 70 mm offset reported 54.8 mm, a
    # true 90 mm reported 57.1, and the estimator saturates near 56 mm -- it
    # could not report a deviation larger than about 0.93 of the band, no
    # matter the truth. Worse, ``face_residual_rms`` is taken about that
    # already-pulled mean, so the gate meant to catch "this is a shape, not
    # noise" read 4.45 mm against its 15 mm bound at the 70 mm offset and
    # got *quieter* the worse the deviation.
    #
    # So the window is put on the returns instead, and the two ways that can
    # go wrong are then checked rather than assumed away.
    # Only returns that lie on the support face may speak for it. See
    # ``_on_support_face``: the window is one-dimensional, so a box's four
    # perpendicular faces put returns inside the band near its far edge and
    # they read as scatter about a plane they are not on.
    on_face = _on_support_face(element, direction, posterior.model_points)
    target_gamma = target_gamma * on_face

    centre, walked = _settle_support_window(
        projections, target_gamma, predicted, calibration.face_band
    )
    if walked > calibration.max_face_recentre:
        raise LikelihoodCalibrationError(
            f"the support face sits {walked*1000:.0f} mm from where the model "
            f"puts it, past the {calibration.max_face_recentre*1000:.0f} mm "
            "this calibration declares: either the as-built deviation is "
            "larger than this instrument was set up to measure, or the "
            "window has found a different surface. Widen face_band and "
            "max_face_recentre deliberately, or fix the pose"
        )

    # A box has two parallel faces exactly 2R apart along ``direction``, and
    # ``direction`` points outward, so the support face is the OUTER one. A
    # window that settles with a plane-like cluster one full thickness
    # further out has settled on the far face: a *clean* measurement of the
    # wrong side of the element. Nothing about the retained returns can show
    # that -- they are well centred in their own window and every statistic
    # taken on them is healthy -- so only the element's own geometry can.
    #
    # It applies only when the far face is far enough away to be a separate
    # window: ``radius > face_band``. Below that the two faces sit inside one
    # window, the rival window overlaps the face itself, and the test fires
    # on every honest measurement -- measured at 0.99 on a clean one-sided
    # scan of Door-1, which is 25 mm of support radius against a 60 mm band.
    # That case is not unguarded: two faces inside one window make the
    # retained returns bimodal, and ``max_residual_sigma_ratio`` below reads
    # the half-separation as scatter and refuses. The two gates divide the
    # range between them.
    if radius > calibration.face_band:
        inside = np.abs(projections - centre) <= calibration.face_band
        here = float(np.sum(target_gamma * inside))
        rival_centre = centre + 2.0 * radius
        rival = float(
            np.sum(
                target_gamma
                * (np.abs(projections - rival_centre) <= calibration.face_band)
            )
        )
        if here > 0.0 and rival / here >= calibration.max_rival_plane_share:
            raise LikelihoodCalibrationError(
                f"a second plane carries {rival/here:.2f} of this one's "
                f"returns exactly {2.0*radius*1000:.0f} mm outward -- one "
                "element thickness. The window has settled on the far face, "
                "or something is parked one thickness off it; either way the "
                "outermost plane is not the one being measured"
            )

    face_mask = np.abs(projections - centre) <= calibration.face_band
    weights = target_gamma * face_mask
    face_mass = float(weights.sum())
    if face_mass < calibration.min_face_effective_points:
        raise LikelihoodCalibrationError(
            f"support face has only {face_mass:.3f} effective points"
        )

    point_inlier_mass = posterior.responsibilities.sum(axis=1)
    target_share = np.divide(
        target_gamma,
        point_inlier_mass,
        out=np.zeros_like(target_gamma),
        where=point_inlier_mass > 0.0,
    )
    face_assignment = float(np.sum(weights * target_share) / face_mass)
    if face_assignment < calibration.min_assignment_confidence:
        raise LikelihoodCalibrationError("support-face assignment is ambiguous")

    observed = float(np.sum(weights * projections) / face_mass)
    centered_points = posterior.model_points - np.sum(
        weights[:, None] * posterior.model_points, axis=0
    ) / face_mass
    normal_offset = centered_points @ direction
    tangent = centered_points - normal_offset[:, None] * direction[None, :]
    tangent_rms = float(
        np.sqrt(np.sum(weights * np.square(tangent).sum(axis=1)) / face_mass)
    )
    if tangent_rms < calibration.min_tangent_rms:
        raise LikelihoodCalibrationError("support-face samples are all in one place")

    face_coverage = _face_coverage(element, direction, posterior.model_points, weights)
    if face_coverage < calibration.min_face_coverage:
        raise LikelihoodCalibrationError(
            f"support face is {face_coverage:.2f} covered (need "
            f"{calibration.min_face_coverage:.2f}): the returns span the face "
            "but do not sample it"
        )

    residual_variance = float(
        np.sum(weights * np.square(projections - observed)) / face_mass
    )
    face_residual_rms = math.sqrt(residual_variance)
    residual_bound = calibration.max_residual_sigma_ratio * calibration.sensor_sigma
    if face_residual_rms > residual_bound:
        raise LikelihoodCalibrationError(
            f"support face scatters {face_residual_rms*1000:.1f} mm rms about "
            f"its own plane, beyond {residual_bound*1000:.1f} mm for a "
            f"{calibration.sensor_sigma*1000:.1f} mm sensor: this is a shape, "
            "not noise, and its mean is not a support plane"
        )
    sampling_variance = max(residual_variance, calibration.sensor_sigma**2) / face_mass
    pose_variance = _support_pose_variance(
        points, weights, face_mass, direction, pose
    )
    noise_variance = (
        sampling_variance + pose_variance + calibration.calibration_sigma**2
    )

    proj = np.abs(direction @ R_element)
    row = (
        direction @ scene.center_jacobian_wrt_raw(element)
        + 0.5 * proj @ scene.extent_jacobians[element.row]
    )
    if not np.any(row != 0.0):
        raise LikelihoodCalibrationError(
            "selected support face is not coupled to any uncertain BIM parameter"
        )
    prior_variance = float(row @ scene.world.belief.sigma @ row)
    innovation_std = math.sqrt(max(prior_variance + noise_variance, 0.0))
    innovation_sigma = (
        abs(observed - predicted) / innovation_std
        if innovation_std > 0.0
        else math.inf
    )
    if innovation_sigma > calibration.max_innovation_sigma:
        raise LikelihoodCalibrationError(
            f"support observation failed innovation gate ({innovation_sigma:.3f} sigma)"
        )

    raw_targets = tuple(
        scene.world.binding.raw_index.var(int(index))
        for index in np.flatnonzero(row)
    )
    evidence_digest = _likelihood_digest(
        scene,
        element.name,
        direction,
        observed,
        face_mass,
        face_assignment,
        pose,
        calibration,
    )
    observation = ObserveLinearized(
        row=row,
        predicted=predicted,
        observed=observed,
        noise_sigma=math.sqrt(noise_variance),
        raw_targets=raw_targets,
        expected_raw_order=scene.world.binding.raw_index.vars,
        expected_belief_digest=scene.world.belief.digest(),
        expected_world_digest=scene.world.digest(),
        evidence_digest=evidence_digest,
        label=f"scan support face {element.name}",
    )
    return ScanClearanceLikelihood(
        element_name=element.name,
        direction=tuple(float(value) for value in direction),
        predicted_support=predicted,
        observed_support=observed,
        effective_face_points=face_mass,
        face_assignment_confidence=face_assignment,
        tangent_rms=tangent_rms,
        face_coverage=face_coverage,
        face_residual_rms=face_residual_rms,
        sampling_sigma=math.sqrt(sampling_variance),
        pose_sigma=math.sqrt(max(pose_variance, 0.0)),
        calibration_sigma=calibration.calibration_sigma,
        noise_sigma=math.sqrt(noise_variance),
        innovation_sigma=innovation_sigma,
        pose_disagreement_m2=pose_m2,
        scan_digest=evidence.scan_digest,
        scene_version=scene.version,
        pose_source_id=pose.source_id,
        evidence_digest=evidence_digest,
        observation=observation,
    )


def _pose_disagreement_m2(
    registration: RegistrationResult, pose: IndependentPoseCalibration
) -> float:
    information = np.asarray(registration.info_matrix, dtype=np.float64)
    if information.shape != (4, 4) or not np.isfinite(information).all():
        raise LikelihoodCalibrationError("registration information matrix is invalid")
    try:
        fit_covariance = np.linalg.inv(information)
        combined = 0.5 * (
            fit_covariance + pose.covariance
            + (fit_covariance + pose.covariance).T
        )
        delta = np.array(
            [
                (pose.transform.theta - registration.transform.theta + math.pi)
                % (2.0 * math.pi)
                - math.pi,
                *(np.asarray(pose.transform.t) - np.asarray(registration.transform.t)),
            ],
            dtype=np.float64,
        )
        return float(delta @ np.linalg.solve(combined, delta))
    except np.linalg.LinAlgError as exc:
        raise LikelihoodCalibrationError(
            "pose agreement covariance is singular"
        ) from exc


def _support_pose_variance(
    scan_points: np.ndarray,
    weights: np.ndarray,
    face_mass: float,
    direction: np.ndarray,
    pose: IndependentPoseCalibration,
) -> float:
    theta = pose.transform.theta
    dR = np.array(
        [
            [-math.sin(theta), -math.cos(theta), 0.0],
            [math.cos(theta), -math.sin(theta), 0.0],
            [0.0, 0.0, 0.0],
        ]
    )
    dpoints_dtheta = scan_points @ dR.T
    dtheta = float(np.sum(weights * (dpoints_dtheta @ direction)) / face_mass)
    jacobian = np.array([dtheta, *direction], dtype=np.float64)
    return max(float(jacobian @ pose.covariance @ jacobian), 0.0)


def _likelihood_digest(
    scene: GeometryScene,
    element_name: str,
    direction: np.ndarray,
    observed: float,
    face_mass: float,
    face_assignment: float,
    pose: IndependentPoseCalibration,
    calibration: ClearanceLikelihoodCalibration,
) -> str:
    digest = hashlib.sha256()
    payload = {
        "scene": scene.version,
        "scan": pose.scan_digest,
        "pose_source": pose.source_id,
        "element": element_name,
        "observed": observed,
        "face_mass": face_mass,
        "face_assignment": face_assignment,
        "calibration": asdict(calibration),
    }
    digest.update(json.dumps(payload, sort_keys=True).encode("utf-8"))
    digest.update(np.asarray(direction, dtype="<f8").tobytes())
    digest.update(
        np.asarray(
            [pose.transform.theta, *pose.transform.t], dtype="<f8"
        ).tobytes()
    )
    digest.update(np.asarray(pose.covariance, dtype="<f8").tobytes())
    return digest.hexdigest()
