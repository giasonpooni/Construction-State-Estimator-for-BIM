"""The rank story behind UNRESOLVED and REQUEST_EVIDENCE.

CSE conditions on observations and reports a disposition, but never published
which coordinates the evidence reaches. These tests pin that: the information
matrix of the evidence, its rank, and the per-coordinate consequence -- a check
resting on a coordinate nothing measured cannot close, whatever its margin looks
like.

The flagship case is asserted directly: the opening-fit world has informed_rank
zero, which is the mechanical reason both of its SATISFIED checks still produce
REQUEST_EVIDENCE.

stdlib unittest only.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

import numpy as np

from gat.engine.active_inference import ObservationCandidate, plan_observations
from gat.engine.transform import ObserveQuantity
from gat.harness.observability import (
    OBSERVABILITY_SCHEMA,
    ObservabilityError,
    blocking_coordinates,
    evidence_ticket,
    information_matrix,
    observability_report,
    plan_coverage,
    prior_variances,
    rank_gain,
    raw_dependencies,
)
from gat.ids import VarId
from gat.session import GatSession

_ROOT = Path(__file__).resolve().parents[1]
MODEL = _ROOT / "gat" / "demo" / "model.ifc"


def _session() -> GatSession:
    return GatSession.load_ifc(str(MODEL))


class PriorWorldTests(unittest.TestCase):
    """A compiled world carries priors and no evidence."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.session = _session()
        cls.report = observability_report(cls.session.world)

    def test_nothing_is_informed_before_an_observation(self) -> None:
        self.assertEqual(self.report.informed_rank, 0)
        self.assertEqual(self.report.informed, ())
        self.assertEqual(len(self.report.uninformed), self.session.world.binding.n_raw)

    def test_the_information_matrix_is_zero(self) -> None:
        lam = information_matrix(self.session.world)
        self.assertTrue(np.allclose(lam, 0.0, atol=1e-9 / np.min(prior_variances(self.session.world))))

    def test_prior_variances_are_the_declared_sigmas_squared(self) -> None:
        variances = prior_variances(self.session.world)
        for index, var in enumerate(self.session.world.binding.raw_index.vars):
            slot = self.session.world.module.slot(var)
            self.assertAlmostEqual(variances[index], slot.prior_sigma**2, places=15)

    def test_every_coordinate_reports_no_variance_reduction(self) -> None:
        for coordinate in self.report.coordinates:
            self.assertAlmostEqual(coordinate.variance_reduction, 0.0, places=12)
            self.assertFalse(coordinate.informed)


class ObservedWorldTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.session = _session()
        cls.opening = cls.session.var("Opening-1", "Width")
        cls.door = cls.session.var("Door-1", "Width")
        cls.session.run(ObserveQuantity.single(cls.opening, 1.002, 0.0016))
        cls.report = observability_report(cls.session.world)

    def test_one_observation_gives_rank_one(self) -> None:
        self.assertEqual(self.report.informed_rank, 1)
        self.assertEqual(self.report.informed, (self.opening,))

    def test_the_measured_coordinate_lost_variance(self) -> None:
        row = next(c for c in self.report.coordinates if c.var == self.opening)
        self.assertGreater(row.variance_reduction, 0.5)
        self.assertLess(row.posterior_variance, row.prior_variance)
        self.assertGreater(row.information, 0.0)

    def test_the_information_matrix_is_psd_and_symmetric(self) -> None:
        lam = information_matrix(self.session.world)
        self.assertTrue(np.allclose(lam, lam.T, rtol=0, atol=0))
        eigenvalues = np.linalg.eigvalsh(lam)
        scale = max(float(np.max(np.abs(eigenvalues))), 1.0)
        self.assertGreater(float(np.min(eigenvalues)), -1e-9 * scale)

    def test_a_zero_diagonal_entry_means_a_zero_row(self) -> None:
        # The PSD property this module's per-coordinate test relies on.
        lam = information_matrix(self.session.world)
        scale = max(float(np.max(np.abs(np.diag(lam)))), 1.0)
        for index in range(lam.shape[0]):
            if abs(lam[index, index]) <= 1e-12 * scale:
                self.assertTrue(
                    np.allclose(lam[index], 0.0, atol=1e-6 * scale),
                    f"row {index} is not zero despite a zero diagonal",
                )


class DependencyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.session = _session()

    def test_a_raw_coordinate_depends_on_itself(self) -> None:
        var = self.session.var("Opening-1", "Width")
        self.assertEqual(raw_dependencies(self.session.world, var), (var,))

    def test_a_derived_quantity_reports_its_jacobian_support(self) -> None:
        total = self.session.var("Level 1", "TotalWallCost")
        deps = raw_dependencies(self.session.world, total)
        self.assertGreater(len(deps), 10)
        # Every dependency is raw, and the storey height is among them.
        raw = set(self.session.world.binding.raw_index.vars)
        self.assertTrue(set(deps) <= raw)
        self.assertIn(self.session.var("Level 1", "ClearHeight"), deps)
        # A door has nothing to do with wall cost.
        self.assertNotIn(self.session.var("Door-1", "Width"), deps)

    def test_an_unknown_coordinate_is_refused(self) -> None:
        bogus = VarId(next(iter(self.session.world.module.entities)), "NotAQuantity")
        with self.assertRaises(ObservabilityError):
            raw_dependencies(self.session.world, bogus)


class TicketTests(unittest.TestCase):
    def test_a_subject_cannot_close_until_its_coordinate_is_measured(self) -> None:
        session = _session()
        opening = session.var("Opening-1", "Width")
        door = session.var("Door-1", "Width")
        subjects = (opening, door)

        before = evidence_ticket(session.world, subjects)
        self.assertEqual(before["informed_rank"], 0)
        self.assertFalse(any(e["can_close_on_evidence"] for e in before["subjects"]))

        session.run(ObserveQuantity.single(opening, 1.002, 0.0016))
        after = evidence_ticket(session.world, subjects)
        entries = {e["subject"]: e for e in after["subjects"]}
        self.assertTrue(entries[str(opening)]["can_close_on_evidence"])
        self.assertFalse(entries[str(door)]["can_close_on_evidence"])
        self.assertEqual(entries[str(door)]["uninformed"], [str(door)])

    def test_blocking_coordinates_shrink_as_evidence_arrives(self) -> None:
        session = _session()
        opening = session.var("Opening-1", "Width")
        area = session.var("Opening-1", "Area")
        before = blocking_coordinates(session.world, area)
        session.run(ObserveQuantity.single(opening, 1.002, 0.0016))
        after = blocking_coordinates(session.world, area)
        self.assertIn(opening, before)
        self.assertNotIn(opening, after)
        self.assertLess(len(after), len(before))

    def test_the_ticket_is_serializable_and_scoped(self) -> None:
        session = _session()
        ticket = evidence_ticket(session.world, (session.var("Opening-1", "Width"),))
        self.assertEqual(ticket["schema"], OBSERVABILITY_SCHEMA)
        self.assertEqual(ticket["claim_scope"], "record-integrity-only")
        self.assertEqual(ticket["world_digest"], session.world.digest())
        json.dumps(ticket)


class RankGainTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.session = _session()
        cls.opening = cls.session.var("Opening-1", "Width")
        cls.session.run(ObserveQuantity.single(cls.opening, 1.002, 0.0016))

    def test_remeasuring_the_same_coordinate_adds_no_direction(self) -> None:
        self.assertEqual(rank_gain(self.session.world, self.opening, 0.0016**2), 0)

    def test_measuring_an_untouched_coordinate_adds_one(self) -> None:
        door = self.session.var("Door-1", "Width")
        self.assertEqual(rank_gain(self.session.world, door, 0.003**2), 1)

    def test_a_non_raw_coordinate_is_refused(self) -> None:
        with self.assertRaises(ObservabilityError):
            rank_gain(self.session.world, self.session.var("Opening-1", "Area"), 1e-6)

    def test_a_non_positive_variance_is_refused(self) -> None:
        with self.assertRaises(ObservabilityError):
            rank_gain(self.session.world, self.opening, 0.0)


class PlanCoverageTests(unittest.TestCase):
    """Expected information and decision relevance are different questions."""

    def test_a_well_scored_plan_can_cover_nothing_the_decision_needs(self) -> None:
        session = _session()
        subjects = (session.var("Opening-1", "Width"), session.var("Door-1", "Width"))
        candidate = ObservationCandidate(
            session.var("Wall-Party", "Length"), 0.004, "tape on party wall"
        )
        plans = plan_observations(session.world, [candidate])
        # It scores real information about the state ...
        self.assertGreater(plans[0].epistemic_value, 0.0)
        # ... and reaches none of the coordinates these subjects rest on.
        coverage = plan_coverage(session.world, plans, subjects)
        self.assertEqual(coverage["reached"], [])
        self.assertFalse(coverage["covers_every_gap"])
        self.assertEqual(len(coverage["uncovered"]), 2)

    def test_a_plan_aimed_at_the_gaps_covers_them(self) -> None:
        session = _session()
        opening = session.var("Opening-1", "Width")
        door = session.var("Door-1", "Width")
        plans = plan_observations(
            session.world,
            [
                ObservationCandidate(opening, 0.0016, "scan opening"),
                ObservationCandidate(door, 0.003, "measure door leaf"),
            ],
        )
        coverage = plan_coverage(session.world, plans, (opening, door))
        self.assertTrue(coverage["covers_every_gap"])
        self.assertEqual(coverage["uncovered"], [])
        self.assertEqual(sorted(coverage["reached"]), sorted([str(opening), str(door)]))

    def test_coverage_accepts_bare_candidates_too(self) -> None:
        session = _session()
        opening = session.var("Opening-1", "Width")
        coverage = plan_coverage(
            session.world, [ObservationCandidate(opening, 0.0016, "scan")], (opening,)
        )
        self.assertTrue(coverage["covers_every_gap"])


class FlagshipDispositionTests(unittest.TestCase):
    """Why the pinned opening-fit case is REQUEST_EVIDENCE."""

    def test_both_checks_are_satisfied_on_a_world_with_no_evidence(self) -> None:
        pin = json.loads(
            (_ROOT / "validation" / "opening-fit-disposition-v1.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(pin["disposition"], "REQUEST_EVIDENCE")
        self.assertTrue(all(c["verdict"] == "SATISFIED" for c in pin["checks"]))
        self.assertEqual(sorted(pin["uncovered_check_ids"]), ["height", "width"])

        session = _session()
        report = observability_report(session.world)
        # The mechanical reason, which the pin states only in prose:
        # "satisfied checks lack verified evidence for this exact world".
        self.assertEqual(report.informed_rank, 0)
        for quantity in ("Width", "Height"):
            for name in ("Opening-1", "Door-1"):
                subject = session.var(name, quantity)
                self.assertEqual(
                    blocking_coordinates(session.world, subject), (subject,)
                )


if __name__ == "__main__":
    unittest.main()
