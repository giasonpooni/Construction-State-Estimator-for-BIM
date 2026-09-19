"""Which coordinates the evidence actually reaches, and which stay at prior.

CSE conditions on ObserveQuantity / ObserveLinearized and then reports
UNRESOLVED or REQUEST_EVIDENCE. What it has never published is the rank story
behind that: *which* coordinates of the world carry information from evidence,
which are still only their declared prior, and therefore which checks cannot
close no matter how the policy is written.

This is identifiability of a static linear-Gaussian state, not observability of
a time-evolving one -- there is no ``A``, the world does not march forward. The
question is what the available channels determine. Every raw coordinate has a
strictly positive prior, so the posterior is always proper and nothing is
"unobservable" in the improper sense. The honest question is narrower and more
useful:

    information gained   Lambda = Sigma_post^-1 - Sigma_prior^-1

``Lambda`` is the evidence's information matrix on the raw coordinates. It is
PSD when conditioning only adds information, and for a PSD matrix
``Lambda[i, i] == 0`` implies row ``i`` is identically zero -- so a zero diagonal
entry is an exact statement that coordinate ``i`` received nothing. ``rank`` is
the number of independent directions the evidence constrains, which is the
number this repo could not previously state.

A satellite. It reads a world and reports; it computes no disposition, writes no
belief, and changes no digest. Its purpose is to make REQUEST_EVIDENCE say which
coordinates it is requesting evidence *for*, and to give
``gat.engine.active_inference`` a target that is a gap rather than an interest.
"""

from __future__ import annotations

from dataclasses import dataclass
import numpy as np

from gat.errors import GatError
from gat.gaussian.linalg import symmetrize
from gat.ids import VarId
from gat.ir.core import Role

OBSERVABILITY_SCHEMA = "cse-observability-v1"

#: Relative floor for calling an information-matrix diagonal entry nonzero.
#: Scaled by the prior precision of the same coordinate, so the test is "did
#: this coordinate's precision move against its own prior", not an absolute.
DEFAULT_RTOL = 1e-9


class ObservabilityError(GatError):
    """The world cannot be read for an information report."""


@dataclass(frozen=True)
class CoordinateInformation:
    """What the evidence did to one raw coordinate."""

    var: VarId
    prior_variance: float
    posterior_variance: float
    information: float          # Lambda[i, i], added precision
    informed: bool

    @property
    def variance_reduction(self) -> float:
        """Fraction of prior variance removed; 0.0 when no channel reached it."""
        if self.prior_variance <= 0.0:
            return 0.0
        return max(0.0, 1.0 - self.posterior_variance / self.prior_variance)

    def as_dict(self) -> dict[str, object]:
        return {
            "var": str(self.var),
            "qualified": self.var.qualified,
            "prior_variance": self.prior_variance,
            "posterior_variance": self.posterior_variance,
            "information": self.information,
            "variance_reduction": self.variance_reduction,
            "informed": self.informed,
        }


@dataclass(frozen=True)
class ObservabilityReport:
    coordinates: tuple[CoordinateInformation, ...]
    informed_rank: int
    world_digest: str

    @property
    def informed(self) -> tuple[VarId, ...]:
        return tuple(c.var for c in self.coordinates if c.informed)

    @property
    def uninformed(self) -> tuple[VarId, ...]:
        return tuple(c.var for c in self.coordinates if not c.informed)

    def as_dict(self) -> dict[str, object]:
        return {
            "schema": OBSERVABILITY_SCHEMA,
            "claim_scope": "record-integrity-only",
            "world_digest": self.world_digest,
            "raw_coordinates": len(self.coordinates),
            "informed_rank": self.informed_rank,
            "informed": [str(v) for v in self.informed],
            "uninformed": [str(v) for v in self.uninformed],
            "coordinates": [c.as_dict() for c in self.coordinates],
            "rule": (
                "informed_rank is the number of independent directions the "
                "evidence constrains. A coordinate with no information has no "
                "observation channel, so a check that depends on it cannot close "
                "on evidence and must stay UNRESOLVED or REQUEST_EVIDENCE."
            ),
        }


def prior_variances(world) -> np.ndarray:
    """Declared prior variances of the raw coordinates, in index order."""
    variances = []
    for var in world.binding.raw_index.vars:
        slot = world.module.slot(var)
        if slot.role is not Role.RAW:
            raise ObservabilityError(f"{var} is indexed raw but its slot is {slot.role}")
        variances.append(float(slot.prior_sigma) ** 2)
    array = np.asarray(variances, dtype=np.float64)
    if not np.all(array > 0.0):
        raise ObservabilityError("every raw prior must have strictly positive sigma")
    return array


def information_matrix(world) -> np.ndarray:
    """``Sigma_post^-1 - Sigma_prior^-1`` on the raw coordinates.

    The prior is diagonal by construction, so its precision is exact. The
    posterior precision comes from a solve, never an explicit inverse.
    """
    posterior = symmetrize(np.asarray(world.belief.sigma, dtype=np.float64))
    n = posterior.shape[0]
    if n != world.binding.n_raw:
        raise ObservabilityError("belief covariance is not on the raw index")
    try:
        posterior_precision = np.linalg.solve(posterior, np.eye(n))
    except np.linalg.LinAlgError as error:  # pragma: no cover - full rank by design
        raise ObservabilityError(f"posterior covariance is singular: {error}") from error
    prior_precision = np.diag(1.0 / prior_variances(world))
    return symmetrize(posterior_precision - prior_precision)


def observability_report(world, *, rtol: float = DEFAULT_RTOL) -> ObservabilityReport:
    """Per-coordinate information plus the rank of the evidence."""
    lam = information_matrix(world)
    prior = prior_variances(world)
    posterior = np.diag(np.asarray(world.belief.sigma, dtype=np.float64))
    diagonal = np.diag(lam)
    # Scale the floor by each coordinate's own prior precision: a millimetre
    # prior and a metre prior are not comparable in absolute precision.
    floors = rtol / prior
    rows = tuple(
        CoordinateInformation(
            var=var,
            prior_variance=float(prior[i]),
            posterior_variance=float(posterior[i]),
            information=float(diagonal[i]),
            informed=bool(diagonal[i] > floors[i]),
        )
        for i, var in enumerate(world.binding.raw_index.vars)
    )
    return ObservabilityReport(
        coordinates=rows,
        informed_rank=_numerical_rank(lam),
        world_digest=world.digest(),
    )


def _numerical_rank(matrix: np.ndarray) -> int:
    """Rank by eigenvalue threshold; the matrix is symmetric by construction."""
    if matrix.size == 0:
        return 0
    eigenvalues = np.linalg.eigvalsh(matrix)
    largest = float(np.max(np.abs(eigenvalues)))
    if largest <= 0.0:
        return 0
    return int(np.count_nonzero(np.abs(eigenvalues) > largest * 1e-10))


def raw_dependencies(world, var: VarId) -> tuple[VarId, ...]:
    """Raw coordinates ``var`` actually depends on, in index order.

    A raw variable depends on itself. A derived one is read off the total
    Jacobian, so the answer is the one the propagation uses rather than a
    re-walk of the expression tree.
    """
    raw_vars = world.binding.raw_index.vars
    if var in raw_vars:
        return (var,)
    deps = world.binding.deps
    if var not in deps.derived_vars:
        raise ObservabilityError(f"{var} is neither a raw nor a derived coordinate")
    jacobian = deps.total_jacobian(raw_vars, world.belief.env())
    row = list(deps.derived_vars).index(var)
    return tuple(
        raw_vars[column]
        for column in range(len(raw_vars))
        if jacobian[row, column] != 0.0
    )


def blocking_coordinates(
    world, var: VarId, *, rtol: float = DEFAULT_RTOL
) -> tuple[VarId, ...]:
    """The raw coordinates ``var`` depends on that no evidence has reached.

    Non-empty means a check on ``var`` cannot be closed by the evidence in this
    world: it is resting on a declared prior, whatever the margin looks like.
    """
    report = observability_report(world, rtol=rtol)
    uninformed = set(report.uninformed)
    return tuple(v for v in raw_dependencies(world, var) if v in uninformed)


def evidence_ticket(
    world, subjects: tuple[VarId, ...], *, rtol: float = DEFAULT_RTOL
) -> dict[str, object]:
    """An observability ticket for the coordinates a decision rests on.

    One entry per subject: what it depends on, what of that is uninformed, and
    whether it could close on evidence at all in this world. This is what turns
    REQUEST_EVIDENCE from a verdict into an address.
    """
    report = observability_report(world, rtol=rtol)
    uninformed = set(report.uninformed)
    entries = []
    for subject in subjects:
        dependencies = raw_dependencies(world, subject)
        blocked = tuple(v for v in dependencies if v in uninformed)
        entries.append(
            {
                "subject": str(subject),
                "depends_on": [str(v) for v in dependencies],
                "uninformed": [str(v) for v in blocked],
                "can_close_on_evidence": not blocked,
            }
        )
    return {
        "schema": OBSERVABILITY_SCHEMA,
        "claim_scope": "record-integrity-only",
        "world_digest": report.world_digest,
        "informed_rank": report.informed_rank,
        "raw_coordinates": len(report.coordinates),
        "subjects": entries,
        "rule": (
            "a subject with uninformed dependencies rests on a declared prior; "
            "no acceptance policy can turn that into evidence"
        ),
    }


def rank_gain(world, var: VarId, variance: float) -> int:
    """Independent directions a direct observation of ``var`` would add.

    Answers the question active inference should be asking -- does this
    measurement reach somewhere the evidence has not -- by forming the updated
    information matrix rather than asserting a rule about it.
    """
    if variance <= 0.0:
        raise ObservabilityError("an observation variance must be positive")
    raw_vars = world.binding.raw_index.vars
    if var not in raw_vars:
        raise ObservabilityError(f"{var} is not a raw coordinate")
    lam = information_matrix(world)
    before = _numerical_rank(lam)
    index = raw_vars.index(var)
    bump = np.zeros_like(lam)
    bump[index, index] = 1.0 / float(variance)
    return _numerical_rank(symmetrize(lam + bump)) - before


def plan_coverage(
    world, plans, subjects: tuple[VarId, ...], *, rtol: float = DEFAULT_RTOL
) -> dict[str, object]:
    """Does a set of planned observations reach the coordinates a decision needs?

    ``plans`` are :class:`~gat.engine.active_inference.ObservationPlan` objects,
    or anything exposing ``candidate.var`` and ``candidate.noise_sigma``. Active
    inference scores a candidate by expected information about the state; this
    asks the complementary question the acceptance policy actually depends on --
    of the coordinates these subjects rest on and nothing has measured, which
    would any of these plans reach, and which would remain untouched.

    A plan set that scores well and covers nothing is a plan to learn about
    coordinates the decision does not need.
    """
    report = observability_report(world, rtol=rtol)
    uninformed = set(report.uninformed)
    needed: list[VarId] = []
    for subject in subjects:
        for var in raw_dependencies(world, subject):
            if var in uninformed and var not in needed:
                needed.append(var)

    reached: dict[VarId, int] = {}
    for plan in plans:
        candidate = getattr(plan, "candidate", plan)
        var = candidate.var
        if var not in needed:
            continue
        gain = rank_gain(world, var, float(candidate.noise_sigma) ** 2)
        if gain > 0:
            reached[var] = max(reached.get(var, 0), gain)

    uncovered = [v for v in needed if v not in reached]
    return {
        "schema": OBSERVABILITY_SCHEMA,
        "claim_scope": "record-integrity-only",
        "world_digest": report.world_digest,
        "informed_rank": report.informed_rank,
        "needed": [str(v) for v in needed],
        "reached": [str(v) for v in reached],
        "uncovered": [str(v) for v in uncovered],
        "covers_every_gap": not uncovered,
        "rule": (
            "a plan that scores well on expected information but reaches no "
            "needed coordinate is planning to learn something the decision does "
            "not rest on"
        ),
    }
