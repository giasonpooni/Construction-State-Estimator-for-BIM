"""Scan-to-BIM registration: aligning point clouds to the Gaussian field.

The Gaussianized building is a mixture model; registering a scan is
maximum-likelihood estimation of the rigid transform that carries scan
points into the model frame:

    NLL(T) = -mean_n log [ (1-pi_out) sum_k w_k N(T x_n; mu_k, S_k) + pi_out / V ]

with a uniform outlier component over the scene bounding box.  v0
estimates the 4-DOF gravity-aligned transform (yaw + translation) —
buildings and scanners agree about *up* — via:

* EM outer loop: responsibilities from the current transform,
* M-step: closed-form generalized-least-squares translation, then a
  Gauss-Newton yaw step, Armijo-guarded on the true NLL so the outer
  iteration is monotone,
* 8 deterministic yaw starts (k * pi/4), each with centroid-matched
  initial translation; best final NLL wins, ties broken by start index.

Those starts are also the only evidence this module has that the winner is
*unique*.  A symmetric room answers the likelihood equally well at yaw 0 and
yaw 180: on the shipped demo wall two starts land 10.2 m apart in
translation and 180 deg apart in yaw, separated by 6.5e-05 nats per point.
Picking the lower one is a coin toss deciding which end of the building was
measured, so the starts are clustered into basins and the margin to the best
*distinct* basin gates acceptance alongside the fit itself.

The reported information matrix is the *complete-data* (responsibility-
weighted) Gauss-Newton Hessian at the optimum.  For a mixture likelihood
this overstates the observed information (the missing-data correction of
Louis' identity is not subtracted), so ``pose_sigma`` is a lower bound on
the pose uncertainty — useful for gating and relative comparisons, and
labeled as the approximation it is.  This module reports it and gates on fit
quality.  Dimensional conditioning is handled separately
by :mod:`gat.geometry.scan_likelihood`, which requires an independent pose
and measures a decision-controlling support face; the naive surface-centroid
observation of a partially visible element remains deliberately unsupported.

Everything is deterministic: scan synthesis takes an explicit seed, and
the optimizer has no stochastic steps.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass

import numpy as np

from gat.errors import RegistrationError
from gat.geometry.stateio import GeometryScene, rot_z


@dataclass(frozen=True)
class RigidTransformZ:
    """x -> R_z(theta) x + t."""

    theta: float
    t: tuple[float, float, float]

    def apply(self, points: np.ndarray) -> np.ndarray:
        return points @ rot_z(self.theta).T + np.asarray(self.t)

    def compose_error(self, other: "RigidTransformZ") -> tuple[float, float]:
        """(yaw error, translation error) between this and another transform."""
        dtheta = abs(
            (self.theta - other.theta + math.pi) % (2.0 * math.pi) - math.pi
        )
        dt = float(np.linalg.norm(np.asarray(self.t) - np.asarray(other.t)))
        return dtheta, dt


@dataclass(frozen=True)
class RegistrationResult:
    transform: RigidTransformZ
    nll: float
    nll_trace: tuple[float, ...]        # fine-stage trace (monotone)
    coarse_trace: tuple[float, ...]     # coarse-stage trace (monotone)
    #: Converged NLL of each pose in :attr:`converged_poses`, same order.
    converged_nlls: tuple[float, ...]
    info_matrix: np.ndarray        # (4, 4) over (theta, tx, ty, tz)
    accepted: bool                 # fit quality AND basin separation
    scan_digest: str               # binds downstream evidence to exact input bytes
    scene_version: str             # canonical-world digest used to derive the field
    #: The distinct poses the contenders converged to, best fit first -- not
    #: one entry per start. Contenders that arrive at the same pose are one
    #: answer found twice, and are merged as they meet rather than carried to
    #: the end as apparent rivals. Kept so the basin structure is auditable
    #: rather than only summarized.
    converged_poses: tuple[RigidTransformZ, ...] = ()
    #: Distinct converged poses found among the contenders, and the NLL margin
    #: from the winner to the best of the others. ``inf`` when every contender
    #: agreed, which is the unambiguous case and not a missing measurement.
    #:
    #: The count is over the contenders as converged on a ``BASIN_SAMPLE_POINTS``
    #: probe, so it resolves the structure at that density and can split a
    #: shallow optimum the full capture merges -- measured on the demo it reads
    #: 2 or 3 for the same scene. The *margin* is what the gate decides on, and
    #: it is stable: 0.47 to 0.61 nats/point across 700 to 4000 points on the
    #: demo building against 1.8e-05 for a genuinely ambiguous single wall.
    basin_count: int = 1
    basin_margin: float = math.inf
    #: Why ``accepted`` is False, or the empty string. A refusal that does
    #: not say which gate refused sends the surveyor back out blind.
    refusal: str = ""

    def pose_sigma(self) -> np.ndarray:
        """Marginal standard deviations of the pose estimate.

        Derived from the complete-data Gauss-Newton information matrix, so
        these are LOWER bounds on the true pose uncertainty (see module
        docstring).

        An information matrix that does not determine a component reports
        ``inf`` for it, not zero.  Clipping a negative variance to zero --
        which is what an inverse of a singular Hessian can produce -- reads
        an ill-conditioned fit as a pose known exactly, and every threshold
        downstream would then pass on the strength of the failure.
        """
        return _marginal_sigma(self.info_matrix)


#: Two starts are the same basin when their poses agree this closely. Far
#: looser than convergence jitter (which is arcseconds and micrometres) and
#: far tighter than a real ambiguity (which is metres and quadrants), so the
#: classification is not sensitive to either bound.
BASIN_YAW_TOL = math.radians(5.0)
BASIN_TRANSLATION_TOL = 0.25

#: How far above the best coarse NLL a start is still worth refining. A start
#: outside this window lost the coarse stage by more than any refinement is
#: going to recover, so it is not a candidate optimum and costs nothing to
#: drop. Inside it, two starts may still be one basin or two, and only
#: convergence can say which.
#:
#: Dropping a start is only free if it could never have been the *rival* the
#: margin is measured to, so that is checked rather than assumed: converging
#: all eight starts instead of the contenders alone leaves the winning pose
#: and ``basin_margin`` bit-identical on every case measured, because the
#: dropped starts settle 2.2 to 4.6 nats/point above the winner against a
#: 0.10 gate -- they become extra basins, never the nearest one.
#: :func:`tests.test_geometry_registration` holds that property.
CONTENDER_WINDOW = 1.0

#: One ``register_from`` call stops when the NLL *step* falls below ``tol``,
#: which a slow plateau satisfies while the pose is still moving: on the demo
#: building the "refined" contenders shifted another 2.8 to 13.7 degrees on the
#: next call, and two pairs of them turned out to be one basin each. A pose has
#: converged when the pose stops moving, not when the objective flattens for
#: one step.
#: Settled to a tenth of the basin tolerance it feeds -- enough to decide
#: whether two contenders are the same optimum, and no tighter. Converging to
#: arcseconds instead cost 31 s for one registration and answered the same
#: question.
#: Which optimum a start falls into is a coarse, global property: it does not
#: depend on the last few thousand returns. Deciding it on a deterministic
#: stride subsample keeps the count honest and keeps its cost off the full
#: capture -- the same reasoning :mod:`gat.geometry.scan_filter` applies to
#: registration itself, where pose wants coverage and not density. The final
#: pose is still refined on every point.
#:
#: The coarse stage runs on the probe too, for the same reason and with the
#: same check: across the demo capture at 700/1500/4000 points, three other
#: seeds and the ambiguous single wall, the probe and the full scan select the
#: identical contender set, and their coarse NLLs agree to 0.09 nats/point
#: against the 1.0-nat window that uses them.
BASIN_SAMPLE_POINTS = 600

#: How uncertain the pose may be and still be an answer. ``pose_sigma`` is a
#: LOWER bound on the pose uncertainty, so a reading above these is a floor
#: already too high, not an estimate that might be better than it looks.
#:
#: The basin margin and the fit NLL do not cover this. Both are per point:
#: a handful of returns can separate two basins by 2.2 nats/point and still
#: not say where the scanner stood. Measured on the demo building, a 10-point
#: capture was accepted with the pose 10.9 deg and 865 mm wrong, and a
#: 20-point capture with it 279 mm wrong; both read a yaw sigma above 0.50
#: deg while every correct acceptance from 20 to 4000 points read 0.43 deg or
#: below. The information matrix knew, and nothing asked it.
#:
#: Half a degree of yaw is about 90 mm at the far corner of this building, the
#: order of the tolerances the decisions downstream turn on. Like ``accept_nll``
#: and ``min_basin_margin`` these are declared defaults calibrated on the demo,
#: overridable per call, and not a claim about every building.
#:
#: They complement the basin margin rather than replace it: the information
#: matrix is local curvature at one optimum and cannot see a rival basin --
#: the ambiguous single wall reads a comfortable 0.20 deg -- while the margin
#: cannot see how few points it was measured over.
MAX_YAW_SIGMA = math.radians(0.5)
MAX_TRANSLATION_SIGMA = 0.100

CONVERGENCE_ROUNDS = 8
CONVERGENCE_YAW = BASIN_YAW_TOL / 10.0
CONVERGENCE_TRANSLATION = BASIN_TRANSLATION_TOL / 10.0


def _marginal_sigma(information: np.ndarray) -> np.ndarray:
    """Marginal standard deviations from an information matrix, fail-closed.

    A component the matrix does not determine reports ``inf``, never zero: an
    inverse of a singular Hessian can yield a negative variance, and clipping
    that to zero reads the failure as a pose known exactly.
    """
    information = np.asarray(information, dtype=np.float64)
    if not np.isfinite(information).all():
        return np.full(information.shape[0], math.inf)
    try:
        variance = np.diag(np.linalg.inv(information))
    except np.linalg.LinAlgError:
        return np.full(information.shape[0], math.inf)
    return np.where(
        np.isfinite(variance) & (variance > 0.0),
        np.sqrt(np.abs(variance)),
        math.inf,
    )


def _basin_separation(
    nlls: list[float],
    poses: list["RigidTransformZ"],
    winner: int,
) -> tuple[int, float]:
    """How many distinct poses explain this scan, and by how much the best wins.

    Starts that converge to the same pose are one basin and their near-equal
    NLLs are agreement, not ambiguity — so the margin is measured to the best
    start in a *different* basin.  With one basin there is no competitor and
    the margin is infinite: an unopposed answer, not an unmeasured one.
    """
    # Union-find, not first-match: "within tolerance of the basin's first
    # member" is not transitive, so a greedy pass can split one basin in two
    # (A~B, B~C, A!~C) and report a phantom rival separated by ~0 nats.
    parent = list(range(len(poses)))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    for i in range(len(poses)):
        for j in range(i + 1, len(poses)):
            yaw, translation = poses[i].compose_error(poses[j])
            if yaw <= BASIN_YAW_TOL and translation <= BASIN_TRANSLATION_TOL:
                parent[find(i)] = find(j)
    grouped: dict[int, list[int]] = {}
    for index in range(len(poses)):
        grouped.setdefault(find(index), []).append(index)
    basins: list[list[int]] = list(grouped.values())

    home = next(b for b in basins if winner in b)
    rivals = [min(nlls[i] for i in b) for b in basins if b is not home]
    if not rivals:
        return len(basins), math.inf
    return len(basins), float(min(rivals) - nlls[winner])


@dataclass(frozen=True)
class ElementScanEvidence:
    """Responsibility-based evidence for one canonical BIM element.

    ``support_diversity`` is the normalized effective number of supported
    primitives (1/K..1), not a claim of physical surface coverage.
    ``assignment_confidence`` is one for evidence assigned exclusively to
    this element and falls when nearby elements share responsibility.
    """

    element_row: int
    element_name: str
    primitive_count: int
    effective_points: float
    responsibility_fraction: float
    mean_mahalanobis2: float
    support_diversity: float
    assignment_confidence: float


@dataclass(frozen=True)
class ScanEvidenceReport:
    """Auditable scan evidence produced only after an accepted fit gate."""

    scan_digest: str
    scene_version: str
    point_count: int
    inlier_effective_points: float
    outlier_fraction: float
    elements: tuple[ElementScanEvidence, ...]

    def render(self) -> str:
        lines = [
            "SCAN EVIDENCE REPORT",
            f"points={self.point_count} "
            f"inlier_mass={self.inlier_effective_points:.3f} "
            f"outlier_fraction={self.outlier_fraction:.3f}",
        ]
        for evidence in self.elements:
            lines.append(
                f"{evidence.element_name}: mass={evidence.effective_points:.3f} "
                f"share={evidence.responsibility_fraction:.3f} "
                f"fit_m2={evidence.mean_mahalanobis2:.3f} "
                f"diversity={evidence.support_diversity:.3f} "
                f"confidence={evidence.assignment_confidence:.3f}"
            )
        return "\n".join(lines)


@dataclass(frozen=True)
class RegisteredScanPosterior:
    """Fine-scale scan/primitive posterior at a declared external pose.

    This is an inspectable likelihood product, not canonical state.  The
    registration result remains the fit and association gate; callers may
    supply an independently calibrated pose so model-derived registration
    error is not recycled as evidence about the model itself.
    """

    model_points: np.ndarray
    responsibilities: np.ndarray
    mahalanobis2: np.ndarray
    scan_digest: str
    scene_version: str

    def __post_init__(self) -> None:
        points = np.asarray(self.model_points, dtype=np.float64)
        gamma = np.asarray(self.responsibilities, dtype=np.float64)
        m2 = np.asarray(self.mahalanobis2, dtype=np.float64)
        if points.ndim != 2 or points.shape[1] != 3:
            raise ValueError("model_points must have shape (n, 3)")
        if gamma.ndim != 2 or gamma.shape != m2.shape:
            raise ValueError("responsibilities and mahalanobis2 must have equal 2D shapes")
        if gamma.shape[0] != points.shape[0]:
            raise ValueError("posterior point and responsibility counts differ")
        if not np.isfinite(points).all() or not np.isfinite(gamma).all() or not np.isfinite(m2).all():
            raise ValueError("registered posterior contains non-finite values")
        for name, value in (("model_points", points), ("responsibilities", gamma), ("mahalanobis2", m2)):
            copied = value.copy()
            copied.setflags(write=False)
            object.__setattr__(self, name, copied)


def _validated_scan(scan: np.ndarray) -> np.ndarray:
    points = np.asarray(scan, dtype=np.float64)
    if points.ndim != 2 or points.shape[1] != 3:
        raise RegistrationError("scan must have shape (n, 3)")
    if not np.isfinite(points).all():
        raise RegistrationError("scan contains non-finite coordinates")
    return np.ascontiguousarray(points)


def _scan_digest(scan: np.ndarray) -> str:
    points = _validated_scan(scan)
    digest = hashlib.sha256()
    digest.update(np.asarray(points.shape, dtype="<i8").tobytes())
    digest.update(np.asarray(points, dtype="<f8").tobytes())
    return digest.hexdigest()


def synthesize_scan(
    scene: GeometryScene,
    n_points: int = 1500,
    noise_sigma: float = 0.01,
    outlier_frac: float = 0.02,
    transform: RigidTransformZ | None = None,
    seed: int = 0,
) -> np.ndarray:
    """Deterministic synthetic laser scan of the scene's solid elements.

    Points sample element box *surfaces* (area-weighted faces) with
    Gaussian sensor noise, plus a uniform outlier fraction.  If
    ``transform`` is given, points are emitted in the scan frame, i.e. the
    INVERSE transform is applied — registration should recover
    ``transform``.
    """
    rng = np.random.default_rng(seed)
    solids = [e for e in scene.elements if e.is_solid]
    areas = []
    for e in solids:
        ex, ey, ez = e.box.extents
        areas.append(2.0 * (ex * ey + ex * ez + ey * ez))
    areas = np.asarray(areas)
    probs = areas / areas.sum()

    n_out = int(round(outlier_frac * n_points))
    n_surf = n_points - n_out
    choices = rng.choice(len(solids), size=n_surf, p=probs)

    points = np.zeros((n_surf, 3), dtype=np.float64)
    for i, idx in enumerate(choices):
        e = solids[idx]
        ex, ey, ez = e.box.extents
        face_areas = np.array([ey * ez, ey * ez, ex * ez, ex * ez, ex * ey, ex * ey])
        face = rng.choice(6, p=face_areas / face_areas.sum())
        u, v = rng.random(), rng.random()
        local = {
            0: (0.0, u * ey, v * ez),
            1: (ex, u * ey, v * ez),
            2: (u * ex, 0.0, v * ez),
            3: (u * ex, ey, v * ez),
            4: (u * ex, v * ey, 0.0),
            5: (u * ex, v * ey, ez),
        }[int(face)]
        R = rot_z(e.box.angle)
        points[i] = np.asarray(e.box.origin) + R @ np.asarray(local)
    points += rng.normal(0.0, noise_sigma, size=points.shape)

    los = np.array([e.aabb()[0] for e in solids]).min(axis=0)
    his = np.array([e.aabb()[1] for e in solids]).max(axis=0)
    outliers = los + rng.random((n_out, 3)) * (his - los)
    scan = np.concatenate([points, outliers])

    if transform is not None:
        # Emit in scan frame: apply the inverse of the model-from-scan map.
        R = rot_z(transform.theta)
        scan = (scan - np.asarray(transform.t)) @ R
    return scan


class ScanRegistrar:
    def __init__(
        self,
        scene: GeometryScene,
        reg_sigma: float = 0.08,
        fine_sigma: float = 0.03,
        outlier_pi: float = 0.05,
        max_iter: int = 30,
        tol: float = 1e-9,
    ):
        scene.check_fresh(scene.world)
        solid_mask = np.isin(
            scene.cloud.element_index,
            [e.row for e in scene.elements if e.is_solid],
        )
        prims = scene.cloud.select(solid_mask)
        self.means = prims.means
        self.base_covs = prims.covs
        self.weights = prims.weights
        self.element_index = prims.element_index
        self.scene_version = scene.version
        self._elements_by_row = {
            element.row: element for element in scene.elements if element.is_solid
        }
        self.outlier_pi = outlier_pi
        self.reg_sigma = reg_sigma
        self.fine_sigma = fine_sigma
        self.max_iter = max_iter
        self.tol = tol
        self._set_sigma(reg_sigma)

    def _set_sigma(self, reg_sigma: float) -> None:
        """(Re)build the smoothed mixture at the given regularization scale."""
        covs = self.base_covs + (reg_sigma**2) * np.eye(3)
        self.inv_covs = np.linalg.inv(covs)
        sign, logdet = np.linalg.slogdet(covs)
        self.log_norm = -0.5 * (3.0 * math.log(2.0 * math.pi) + logdet)
        self.log_w = np.log(self.weights / self.weights.sum())
        los = self.means.min(axis=0) - 1.0
        his = self.means.max(axis=0) + 1.0
        self.log_outlier = math.log(self.outlier_pi) - math.log(
            float(np.prod(his - los))
        )

    # -- likelihood --------------------------------------------------------

    def _log_components(self, model_points: np.ndarray) -> np.ndarray:
        """(M, K) log[(1-pi) w_k N_k(x_m)] — the inlier component logs."""
        d = model_points[:, None, :] - self.means[None, :, :]     # (M, K, 3)
        m2 = np.einsum("mki,kij,mkj->mk", d, self.inv_covs, d)
        return (
            math.log(1.0 - self.outlier_pi)
            + self.log_w[None, :]
            + self.log_norm[None, :]
            - 0.5 * m2
        )

    def nll(self, scan: np.ndarray, T: RigidTransformZ) -> float:
        logs = self._log_components(T.apply(scan))
        top = np.maximum(logs.max(axis=1), self.log_outlier)
        lse = top + np.log(
            np.exp(logs - top[:, None]).sum(axis=1) + np.exp(self.log_outlier - top)
        )
        return float(-lse.mean())

    # -- EM ----------------------------------------------------------------

    def _responsibilities(self, model_points: np.ndarray) -> np.ndarray:
        logs = self._log_components(model_points)
        top = np.maximum(logs.max(axis=1), self.log_outlier)
        denom = np.exp(logs - top[:, None]).sum(axis=1) + np.exp(self.log_outlier - top)
        return np.exp(logs - top[:, None]) / denom[:, None]      # (M, K), inlier only

    def _m_step(
        self, scan: np.ndarray, T: RigidTransformZ, gamma: np.ndarray
    ) -> RigidTransformZ:
        """Closed-form t (GLS) then one Armijo-guarded Gauss-Newton yaw step."""
        # Effective per-point precision and precision-weighted target.
        A = np.einsum("mk,kij->mij", gamma, self.inv_covs)           # (M, 3, 3)
        b = np.einsum("mk,kij,kj->mi", gamma, self.inv_covs, self.means)

        def solve_t(theta: float) -> np.ndarray:
            R = rot_z(theta)
            rx = scan @ R.T                                          # (M, 3)
            lhs = A.sum(axis=0)
            rhs = (b - np.einsum("mij,mj->mi", A, rx)).sum(axis=0)
            return np.linalg.solve(lhs, rhs)

        theta = T.theta
        t = solve_t(theta)

        # Gauss-Newton on theta for the responsibility-weighted quadratic.
        R = rot_z(theta)
        dR = np.array(
            [[-math.sin(theta), -math.cos(theta), 0.0],
             [math.cos(theta), -math.sin(theta), 0.0],
             [0.0, 0.0, 0.0]]
        )
        rx = scan @ R.T + t
        drx = scan @ dR.T                                            # (M, 3)
        resid = np.einsum("mij,mj->mi", A, rx) - b                   # precision-weighted
        grad = float(np.einsum("mi,mi->", drx, resid))
        hess = float(np.einsum("mi,mij,mj->", drx, A, drx))
        if hess <= 0:
            return RigidTransformZ(theta, tuple(t))
        step = -grad / hess

        # Armijo guard on the TRUE NLL (monotone outer iteration).
        base = self.nll(scan, RigidTransformZ(theta, tuple(t)))
        alpha = 1.0
        for _ in range(20):
            cand_theta = theta + alpha * step
            cand_t = solve_t(cand_theta)
            if self.nll(scan, RigidTransformZ(cand_theta, tuple(cand_t))) <= base + 1e-15:
                return RigidTransformZ(cand_theta, tuple(cand_t))
            alpha *= 0.5
        return RigidTransformZ(theta, tuple(t))

    def register_from(
        self, scan: np.ndarray, start: RigidTransformZ, max_iter: int | None = None
    ) -> tuple[RigidTransformZ, float, list[float]]:
        T = start
        trace = [self.nll(scan, T)]
        for _ in range(max_iter if max_iter is not None else self.max_iter):
            gamma = self._responsibilities(T.apply(scan))
            T = self._m_step(scan, T, gamma)
            trace.append(self.nll(scan, T))
            if abs(trace[-2] - trace[-1]) < self.tol:
                break
        return T, trace[-1], trace

    def _converge_together(
        self, scan: np.ndarray, starts: list[RigidTransformZ]
    ) -> list[tuple[float, RigidTransformZ]]:
        """Refine the contenders in lockstep, dropping them as they merge.

        Converging each contender separately re-derives the same optimum once
        per start that leads to it.  Two contenders that agree to the
        *convergence* tolerance -- arcminutes and millimetres, a tenth of the
        tolerance that groups basins -- are at the same pose, and EM from the
        same pose on the same points follows the same path, so one of them
        carries it from there and the other is not a second answer.

        That is the only merge performed here, and it is an identity, not an
        extrapolation: a contender still moving stays live and is converged on
        its own until it settles or the rounds run out.  Merging contenders
        that are merely *heading* the same way would be a guess, and the
        direction it errs in is acceptance -- one rival fewer raises
        ``basin_margin``, which is the quantity that gates.
        """
        def _same(a: RigidTransformZ, b: RigidTransformZ) -> bool:
            yaw, translation = a.compose_error(b)
            return yaw <= CONVERGENCE_YAW and translation <= CONVERGENCE_TRANSLATION

        live = [(self.nll(scan, pose), pose) for pose in starts]
        done: list[tuple[float, RigidTransformZ]] = []
        for _ in range(CONVERGENCE_ROUNDS):
            if not live:
                break
            moved: list[tuple[float, RigidTransformZ, bool]] = []
            for nll, pose in live:
                nxt, nxt_nll, _ = self.register_from(scan, pose)
                yaw, translation = nxt.compose_error(pose)
                at_rest = yaw <= CONVERGENCE_YAW and translation <= CONVERGENCE_TRANSLATION
                moved.append((nxt_nll, nxt, at_rest))

            live = []
            for nll, pose, at_rest in sorted(moved, key=lambda i: i[0]):
                pool = done if at_rest else live
                if any(_same(pose, other) for _, other in done + live):
                    continue
                pool.append((nll, pose))
        return sorted(done + live, key=lambda item: item[0])

    def register(
        self,
        scan: np.ndarray,
        n_starts: int = 8,
        accept_nll: float = 6.0,
        min_basin_margin: float = 0.10,
        max_yaw_sigma: float = MAX_YAW_SIGMA,
        max_translation_sigma: float = MAX_TRANSLATION_SIGMA,
    ) -> RegistrationResult:
        """Coarse-to-fine multi-start registration.

        Stage A runs a few EM iterations from every yaw start at the coarse
        smoothing scale; stage B refines every *contender* -- each start whose
        coarse NLL is within ``CONTENDER_WINDOW`` of the best -- to
        convergence, clusters those into basins, and anneals the winner to the
        fine scale for the final polish and the information matrix.  Fully
        deterministic; ties break by start index.

        Converging the contenders rather than clustering the six-iteration
        coarse results costs roughly twice the EM work of the single-refinement
        path it replaced.  That is the price of an honest count: on the demo
        building the coarse poses sit within 2 degrees of the eight starts they
        began at, so clustering them reported eight optima that do not exist
        and a margin to a rival that is not there.

        ``min_basin_margin`` is how much better, in nats per point, the
        winning basin must be than the best *distinct* basin.  Without it a
        pose is accepted on a tie-break: on a symmetric wall the yaw-0 and
        yaw-180 solutions differ by 10.2 m of translation and 6.5e-05 nats,
        and the registrar returns whichever came first.  A margin of 0.10
        over hundreds of points is decisive evidence; below it the scan does
        not determine where it was taken from, and saying so is the answer.

        ``max_yaw_sigma`` and ``max_translation_sigma`` bound the pose
        uncertainty the fit is willing to call an answer.  That is a separate
        question from either gate above: both of those are per point, and a
        scan of a dozen returns can clear both while leaving the pose a
        degree and a metre out.  See :data:`MAX_YAW_SIGMA`.

        ``n_starts`` must be at least two.  The starts are the only evidence
        this module has that the winner is unique, so a single start leaves
        the margin unmeasured -- and an unmeasured margin reads as ``inf``,
        which passes every threshold.
        """
        scan = _validated_scan(scan)
        if scan.shape[0] < 10:
            raise RegistrationError("scan has too few points")
        if n_starts < 2:
            raise RegistrationError(
                f"n_starts={n_starts} cannot establish that a pose is unique: "
                "one start has nothing to be compared against and no starts "
                "have nothing to compare"
            )
        model_centroid = self.means.mean(axis=0)
        scan_centroid = scan.mean(axis=0)

        self._set_sigma(self.reg_sigma)
        # Which basin a start falls into is a coarse, global property. The
        # whole pose *search* -- every yaw start, every contender, the basin
        # clustering -- therefore runs on a deterministic stride probe, and
        # only the final refinement sees every point. Ceiling division so the
        # probe is at most BASIN_SAMPLE_POINTS rather than at most one stride
        # above it; floor division left a 700-point scan at stride 1.
        stride = max(1, -(-scan.shape[0] // BASIN_SAMPLE_POINTS))
        probe = scan[::stride]

        best: tuple[int, float, RigidTransformZ] | None = None
        coarse_nlls: list[float] = []
        coarse_poses: list[RigidTransformZ] = []
        for k in range(n_starts):
            theta0 = 2.0 * math.pi * k / n_starts
            R0 = rot_z(theta0)
            t0 = model_centroid - R0 @ scan_centroid
            T0 = RigidTransformZ(theta0, tuple(t0))
            T, final_nll, _ = self.register_from(probe, T0, max_iter=6)
            coarse_nlls.append(final_nll)
            coarse_poses.append(T)

        # Six EM iterations from a 45-degree start is not a converged pose: on
        # the demo building the eight coarse results sit within 2 degrees of
        # the eight starts they began at, so clustering *those* measures the
        # starts and reports eight basins that do not exist. Refine every
        # contender to convergence first, and cluster what converged.
        floor = min(coarse_nlls)
        contenders = [
            k for k, nll in enumerate(coarse_nlls)
            if nll <= floor + CONTENDER_WINDOW
        ]
        converged = self._converge_together(
            probe, [coarse_poses[k] for k in contenders]
        )
        converged_nlls = [nll for nll, _ in converged]
        converged_poses = [pose for _, pose in converged]
        for index, (refined_nll, refined) in enumerate(converged):
            if best is None or refined_nll < best[1] - 1e-12:
                best = (index, refined_nll, refined)
        assert best is not None
        basin_count, basin_margin = _basin_separation(
            converged_nlls, converged_poses, best[0]
        )

        T, _, trace_coarse = self.register_from(scan, best[2])

        self._set_sigma(self.fine_sigma)
        T, nll, trace_fine = self.register_from(scan, T)
        info = self._information_matrix(scan, T)
        self._set_sigma(self.reg_sigma)  # restore for reproducible reuse

        refusals = []
        if not nll < accept_nll:
            refusals.append(f"fit nll {nll:.4f} is not below {accept_nll:.4f}")
        if not basin_margin >= min_basin_margin:
            refusals.append(
                f"{basin_count} converged poses fit this scan and the best two "
                f"are within {basin_margin:.3g} nats/point (need "
                f"{min_basin_margin:g}); the scan does not determine where it "
                "was taken from"
            )
        yaw_sigma, *translation_sigma = _marginal_sigma(info)
        worst_translation = max(translation_sigma)
        if not yaw_sigma <= max_yaw_sigma:
            refusals.append(
                f"pose yaw is uncertain to at least {math.degrees(yaw_sigma):.3g} "
                f"deg (allowed {math.degrees(max_yaw_sigma):g}); the fit is not "
                "determined well enough to place the scan"
            )
        if not worst_translation <= max_translation_sigma:
            refusals.append(
                f"pose translation is uncertain to at least "
                f"{worst_translation * 1000.0:.3g} mm (allowed "
                f"{max_translation_sigma * 1000.0:g}); the fit is not determined "
                "well enough to place the scan"
            )
        return RegistrationResult(
            transform=T,
            nll=nll,
            nll_trace=tuple(trace_fine),
            coarse_trace=tuple(trace_coarse),
            converged_nlls=tuple(converged_nlls),
            info_matrix=info,
            accepted=not refusals,
            scan_digest=_scan_digest(scan),
            scene_version=self.scene_version,
            converged_poses=tuple(converged_poses),
            basin_count=basin_count,
            basin_margin=basin_margin,
            refusal="; ".join(refusals),
        )

    def register_ply(
        self,
        path: str,
        n_starts: int = 8,
        accept_nll: float = 6.0,
        min_basin_margin: float = 0.10,
        max_yaw_sigma: float = MAX_YAW_SIGMA,
        max_translation_sigma: float = MAX_TRANSLATION_SIGMA,
    ) -> RegistrationResult:
        """Register vertices from a standard external PLY artifact.

        This is an adapter boundary, not a dependency on a reconstruction
        engine.  For example, Geometry-Grounded-Gaussian-Splatting exports
        its post-processed extracted mesh as ``recon_post.ply``; the mesh
        vertices are treated as scan points and enter the same deterministic
        GMM likelihood and fit-quality gate as native point clouds.
        """
        from gat.geometry.scan_io import load_ply_points

        return self.register(
            load_ply_points(path),
            n_starts,
            accept_nll,
            min_basin_margin,
            max_yaw_sigma,
            max_translation_sigma,
        )

    def evidence(
        self, scan: np.ndarray, result: RegistrationResult
    ) -> ScanEvidenceReport:
        """Aggregate accepted primitive responsibilities by BIM element.

        The report is descriptive evidence, not a state update.  It is
        bound to the exact registered scan and canonical scene version so a
        transform cannot accidentally be reused for different observations
        or a changed model.  Rejected registrations never produce evidence.
        """
        posterior = self.posterior_at(scan, result)
        points = posterior.model_points
        gamma = posterior.responsibilities
        mahalanobis2 = posterior.mahalanobis2

        rows = tuple(sorted(self._elements_by_row))
        element_gamma = np.stack(
            [gamma[:, self.element_index == row].sum(axis=1) for row in rows],
            axis=1,
        )
        point_inlier_mass = element_gamma.sum(axis=1)
        total_inlier_mass = float(point_inlier_mass.sum())

        evidence_rows: list[ElementScanEvidence] = []
        for column, row in enumerate(rows):
            primitive_mask = self.element_index == row
            primitive_mass = gamma[:, primitive_mask].sum(axis=0)
            effective_points = float(primitive_mass.sum())
            primitive_count = int(primitive_mask.sum())

            if effective_points > 0.0:
                normalized_primitive_mass = primitive_mass / effective_points
                support_diversity = float(
                    1.0
                    / (
                        primitive_count
                        * np.square(normalized_primitive_mass).sum()
                    )
                )
                mean_mahalanobis2 = float(
                    np.sum(gamma[:, primitive_mask] * mahalanobis2[:, primitive_mask])
                    / effective_points
                )
                point_share = np.divide(
                    element_gamma[:, column],
                    point_inlier_mass,
                    out=np.zeros_like(point_inlier_mass),
                    where=point_inlier_mass > 0.0,
                )
                assignment_confidence = float(
                    np.sum(element_gamma[:, column] * point_share)
                    / effective_points
                )
            else:
                support_diversity = 0.0
                mean_mahalanobis2 = 0.0
                assignment_confidence = 0.0

            element = self._elements_by_row[row]
            evidence_rows.append(
                ElementScanEvidence(
                    element_row=row,
                    element_name=element.name,
                    primitive_count=primitive_count,
                    effective_points=effective_points,
                    responsibility_fraction=(
                        effective_points / total_inlier_mass
                        if total_inlier_mass > 0.0
                        else 0.0
                    ),
                    mean_mahalanobis2=mean_mahalanobis2,
                    support_diversity=support_diversity,
                    assignment_confidence=assignment_confidence,
                )
            )

        return ScanEvidenceReport(
            scan_digest=result.scan_digest,
            scene_version=result.scene_version,
            point_count=points.shape[0],
            inlier_effective_points=total_inlier_mass,
            outlier_fraction=1.0 - total_inlier_mass / points.shape[0],
            elements=tuple(evidence_rows),
        )

    def posterior_at(
        self,
        scan: np.ndarray,
        result: RegistrationResult,
        transform: RigidTransformZ | None = None,
    ) -> RegisteredScanPosterior:
        """Return fine responsibilities at ``transform`` after all fit gates.

        Omitting ``transform`` reproduces the fitted registration posterior.
        Supplying a survey/SLAM pose lets downstream adapters use registration
        only for association while keeping pose provenance independent.
        """
        points = _validated_scan(scan)
        if not result.accepted:
            raise RegistrationError(
                "cannot report scan evidence: registration failed the fit gate"
            )
        if result.scene_version != self.scene_version:
            raise RegistrationError(
                "cannot report scan evidence: registration belongs to a different scene"
            )
        if result.scan_digest != _scan_digest(points):
            raise RegistrationError(
                "cannot report scan evidence: scan differs from the registered input"
            )

        pose = result.transform if transform is None else transform
        self._set_sigma(self.fine_sigma)
        try:
            model_points = pose.apply(points)
            gamma = self._responsibilities(model_points)
            delta = model_points[:, None, :] - self.means[None, :, :]
            mahalanobis2 = np.einsum(
                "mki,kij,mkj->mk", delta, self.inv_covs, delta
            )
        finally:
            self._set_sigma(self.reg_sigma)
        return RegisteredScanPosterior(
            model_points=model_points,
            responsibilities=gamma,
            mahalanobis2=mahalanobis2,
            scan_digest=result.scan_digest,
            scene_version=result.scene_version,
        )

    def _information_matrix(self, scan: np.ndarray, T: RigidTransformZ) -> np.ndarray:
        """Gauss-Newton Hessian of the total NLL at the optimum, over
        (theta, tx, ty, tz).  Total (not mean) — information adds over
        points, so more scan coverage means a tighter pose."""
        gamma = self._responsibilities(T.apply(scan))
        A = np.einsum("mk,kij->mij", gamma, self.inv_covs)
        dR = np.array(
            [[-math.sin(T.theta), -math.cos(T.theta), 0.0],
             [math.cos(T.theta), -math.sin(T.theta), 0.0],
             [0.0, 0.0, 0.0]]
        )
        drx = scan @ dR.T                                            # d model-point / d theta
        H = np.zeros((4, 4), dtype=np.float64)
        H[0, 0] = np.einsum("mi,mij,mj->", drx, A, drx)
        Ht_block = A.sum(axis=0)
        H[1:, 1:] = Ht_block
        cross = np.einsum("mij,mj->i", A, drx)
        H[0, 1:] = cross
        H[1:, 0] = cross
        return H
