"""Invariant, variant, and the measurement that tells them apart.

Verification used to answer a binary question at a hardcoded two sigma, and
nothing consumed the answer: `VerificationReport.passed` ignored WARN, the
acceptance policy never read it, and `active_inference` had no reference to
verification at all. So a world whose opening-width bound held at the mean
but in only 60% of realizations verified clean and could reach ACCEPT.

Now a probabilistic constraint reports `p_holds`, the policy declares the
confidence it wants, a variant constraint blocks authorization the way
insufficient geometry does, and the planner can rank the measurement that
would settle it. These tests pin that chain end to end.
"""

from __future__ import annotations

from dataclasses import replace
import math
import unittest

from gat.engine.active_inference import (
    MarginPreference,
    ObservationCandidate,
    plan_variant_evidence,
    preference_for_variant,
)
from gat.engine.transform import SetParameter
from gat.engine.verify import (
    ALL_INVARIANTS,
    _z_for,
    DEFAULT_INVARIANT_CONFIDENCE,
    InvariantResult,
    Status,
    VerificationReport,
    run_invariants,
)
from gat.ledger import LEDGER_SCHEMA_VERSION, verification_payload
from gat.session import GatSession
from gat.workflows import (
    AcceptanceCase,
    AcceptanceDisposition,
    AcceptancePolicy,
    DifferenceDecision,
    WorkflowKind,
    assess_difference,
    difference_check,
    evaluate_acceptance_case,
)


MODEL = "gat/demo/model.ifc"


def _variant_session() -> GatSession:
    """A world whose door-into-opening bound holds at the mean, but barely.

    Door width 0.99 against an opening of 1.00, with a 0.04 m design sigma:
    a 0.01 m margin against a 0.04 m spread.
    """
    session = GatSession.load_ifc(MODEL)
    session.run(SetParameter(session.var("Door-1", "Width"), 0.99, design_sigma=0.04))
    return session


class DefaultIsTheOldBehaviourTests(unittest.TestCase):
    def test_the_default_confidence_is_exactly_phi_of_two(self) -> None:
        """The layer used a 2-sigma band; the default must change no verdict."""
        self.assertAlmostEqual(
            DEFAULT_INVARIANT_CONFIDENCE,
            0.5 * (1.0 + math.erf(2.0 / math.sqrt(2.0))),
            places=15,
        )

    def test_a_clean_world_still_verifies_clean(self) -> None:
        report = run_invariants(GatSession.load_ifc(MODEL).world)
        self.assertTrue(report.passed)
        self.assertEqual(report.warnings, ())

    def test_confidence_must_be_a_probability(self) -> None:
        world = GatSession.load_ifc(MODEL).world
        for bad in (0.0, 1.0, -0.5, 1.5, float("nan")):
            with self.subTest(confidence=bad):
                with self.assertRaises(ValueError):
                    run_invariants(world, bad)


class EmptyReportTests(unittest.TestCase):
    """A check that checked nothing is not a pass."""

    def test_a_report_with_no_results_does_not_pass(self) -> None:
        self.assertFalse(VerificationReport(()).passed)

    def test_every_invariant_speaks_for_any_compilable_world(self) -> None:
        """Which is why run_invariants cannot produce an empty report."""
        session = GatSession.load_ifc(MODEL)
        for invariant in ALL_INVARIANTS:
            with self.subTest(invariant=invariant.id):
                results = list(
                    invariant.check(session.world, DEFAULT_INVARIANT_CONFIDENCE)
                )
                self.assertGreater(len(results), 0)

    def test_a_warning_still_passes(self) -> None:
        warned = InvariantResult("X-01", Status.WARN, "s", 0.0, "advisory")
        self.assertTrue(VerificationReport((warned,)).passed)


class ProbabilityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.session = _variant_session()
        self.report = run_invariants(self.session.world)

    def test_a_barely_held_bound_is_variant(self) -> None:
        warnings = [r for r in self.report.warnings if r.invariant_id == "CONS-02"]
        self.assertEqual(len(warnings), 1)
        variant = warnings[0]
        self.assertIsNotNone(variant.p_holds)
        self.assertLess(variant.p_holds, DEFAULT_INVARIANT_CONFIDENCE)
        self.assertGreater(variant.p_holds, 0.5, "it does still hold at the mean")
        self.assertIn("variant", variant.detail)

    def test_a_variant_result_names_its_variables(self) -> None:
        variant = next(r for r in self.report.warnings if r.invariant_id == "CONS-02")
        names = {str(v) for v in variant.variables}
        self.assertEqual(len(names), 2, "a LessEqual margin spans two variables")
        self.assertTrue(any("Width" in n for n in names))

    def test_p_holds_matches_the_margin_normal(self) -> None:
        """Recompute it independently from the belief."""
        variant = next(r for r in self.report.warnings if r.invariant_id == "CONS-02")
        lhs, rhs = variant.variables
        full = self.session.world.full
        margin = full.mean(rhs) - full.mean(lhs)
        var = full.var_of(lhs) + full.var_of(rhs) - 2.0 * full.cov(lhs, rhs)
        expected = 0.5 * (1.0 + math.erf(margin / math.sqrt(var) / math.sqrt(2.0)))
        self.assertAlmostEqual(variant.p_holds, expected, places=12)

    def test_a_variant_world_still_passes_because_warn_is_not_fail(self) -> None:
        """The signal exists; `passed` deliberately does not consume it."""
        self.assertTrue(self.report.passed)
        self.assertTrue(self.report.warnings)

    def test_raising_the_confidence_can_only_add_variants(self) -> None:
        counts = [
            len(run_invariants(self.session.world, c).warnings)
            for c in (0.5, 0.9, 0.99, 0.999)
        ]
        self.assertEqual(counts, sorted(counts))
        # The bound holds with P = 0.598, so it is invariant against a
        # confidence of 0.5 and variant against anything above it.
        self.assertEqual(counts[0], 0)
        self.assertGreater(counts[-1], 0)

    def test_a_clean_pass_records_the_tightest_constraint(self) -> None:
        report = run_invariants(GatSession.load_ifc(MODEL).world)
        for invariant_id in ("CONS-01", "CONS-02"):
            with self.subTest(invariant=invariant_id):
                result = next(
                    r for r in report.results if r.invariant_id == invariant_id
                )
                self.assertIs(result.status, Status.PASS)
                self.assertIsNotNone(result.p_holds)
                self.assertIn("tightest", result.detail)


class LedgerRecordTests(unittest.TestCase):
    def test_the_schema_version_moved_for_the_new_field(self) -> None:
        self.assertEqual(LEDGER_SCHEMA_VERSION, 2)

    def test_probabilistic_results_carry_p_holds_and_structural_ones_do_not(
        self,
    ) -> None:
        payload = verification_payload(
            run_invariants(GatSession.load_ifc(MODEL).world)
        )
        by_id = {r["invariant_id"]: r for r in payload["results"]}
        self.assertIsNotNone(by_id["CONS-01"]["p_holds"])
        self.assertIsNotNone(by_id["CONS-02"]["p_holds"])
        self.assertIsNone(
            by_id["STRUCT-01"]["p_holds"],
            "a structural invariant is true or false, not probable",
        )

    def test_every_recorded_probability_is_a_probability(self) -> None:
        payload = verification_payload(run_invariants(_variant_session().world))
        for result in payload["results"]:
            if result["p_holds"] is not None:
                with self.subTest(invariant=result["invariant_id"]):
                    self.assertGreaterEqual(result["p_holds"], 0.0)
                    self.assertLessEqual(result["p_holds"], 1.0)


class InvariantGateTests(unittest.TestCase):
    """A variant constraint must not authorize."""

    def setUp(self) -> None:
        self.session = _variant_session()
        self.report = run_invariants(self.session.world)
        assessment = assess_difference(
            self.session.world,
            DifferenceDecision(
                self.session.var("Opening-1", "Height"),
                self.session.var("Door-1", "Height"),
                minimum_margin=0.05,
                confidence=0.95,
                label="Door-1 height fit",
            ),
        )
        self.case = AcceptanceCase(
            "variant-case",
            WorkflowKind.OPENING_VERIFICATION,
            "Door-1 into Opening-1",
            (difference_check("height", assessment),),
        )
        # Waives field evidence but not support, so ACCEPT is reachable and
        # the invariant gate is the thing being tested.
        self.review = AcceptancePolicy(
            "design-review-v1", require_verified_evidence_for_accept=False
        )

    def test_without_a_report_the_gate_does_not_run(self) -> None:
        outcome = evaluate_acceptance_case(self.case, policy=self.review)
        self.assertIs(outcome.disposition, AcceptanceDisposition.ACCEPT)
        self.assertEqual(outcome.variant_constraints, ())

    def test_a_variant_constraint_blocks_authorization(self) -> None:
        outcome = evaluate_acceptance_case(
            self.case, policy=self.review, verification=self.report
        )
        self.assertIs(outcome.disposition, AcceptanceDisposition.REQUEST_EVIDENCE)
        self.assertFalse(outcome.may_authorize)
        self.assertEqual(len(outcome.variant_constraints), 1)
        subject, p_holds = outcome.variant_constraints[0]
        self.assertLess(p_holds, DEFAULT_INVARIANT_CONFIDENCE)
        self.assertIn("<=", subject)

    def test_it_raises_a_ranked_evidence_request(self) -> None:
        outcome = evaluate_acceptance_case(
            self.case, policy=self.review, verification=self.report
        )
        requests = [
            r for r in outcome.evidence_requests
            if r.action == "MEASURE_VARIANT_CONSTRAINT"
        ]
        self.assertEqual(len(requests), 1)
        # Priority is the shortfall, so a weaker constraint is asked first.
        self.assertAlmostEqual(
            requests[0].priority, 1.0 - outcome.variant_constraints[0][1], places=12
        )

    def test_a_policy_may_declare_that_it_tolerates_variance(self) -> None:
        tolerant = AcceptancePolicy(
            "design-review-v1",
            require_verified_evidence_for_accept=False,
            require_invariant_constraints_for_accept=False,
        )
        outcome = evaluate_acceptance_case(
            self.case, policy=tolerant, verification=self.report
        )
        self.assertIs(outcome.disposition, AcceptanceDisposition.ACCEPT)
        self.assertEqual(
            len(outcome.variant_constraints),
            1,
            "tolerating variance must still report it",
        )

    def test_a_clean_world_is_unaffected_by_the_gate(self) -> None:
        session = GatSession.load_ifc(MODEL)
        assessment = assess_difference(
            session.world,
            DifferenceDecision(
                session.var("Opening-1", "Height"),
                session.var("Door-1", "Height"),
                minimum_margin=0.05,
                confidence=0.95,
                label="Door-1 height fit",
            ),
        )
        case = AcceptanceCase(
            "clean-case",
            WorkflowKind.OPENING_VERIFICATION,
            "Door-1 into Opening-1",
            (difference_check("height", assessment),),
        )
        outcome = evaluate_acceptance_case(
            case, policy=self.review, verification=run_invariants(session.world)
        )
        self.assertIs(outcome.disposition, AcceptanceDisposition.ACCEPT)
        self.assertEqual(outcome.variant_constraints, ())


class VariantToMeasurementTests(unittest.TestCase):
    """The loop the README advertises: verify, then select what to measure."""

    def setUp(self) -> None:
        self.session = _variant_session()
        self.report = run_invariants(self.session.world)
        self.door = self.session.var("Door-1", "Width")
        self.opening = self.session.var("Opening-1", "Width")
        self.height = self.session.var("Level 1", "ClearHeight")
        self.candidates = [
            ObservationCandidate(self.door, 0.002, "laser on door leaf", 0.1),
            ObservationCandidate(self.opening, 0.002, "laser on opening", 0.1),
            ObservationCandidate(self.height, 0.002, "laser on storey", 0.1),
        ]

    def test_a_bound_becomes_a_margin_preference(self) -> None:
        variant = next(r for r in self.report.warnings if r.invariant_id == "CONS-02")
        preference = preference_for_variant(variant)
        self.assertIsInstance(preference, MarginPreference)
        coefficients = sorted(c for c, _ in preference.terms)
        self.assertEqual(coefficients, [-1.0, 1.0], "margin is rhs - lhs")
        self.assertEqual(preference.minimum, 0.0)

    def test_a_structural_invariant_has_no_margin_to_measure(self) -> None:
        structural = next(
            r for r in self.report.results if r.invariant_id == "STRUCT-01"
        )
        self.assertIsNone(preference_for_variant(structural))

    def test_the_planner_reproduces_the_invariant_probability(self) -> None:
        """Two layers, two code paths, one number."""
        plans = plan_variant_evidence(
            self.session.world, self.report, self.candidates
        )
        self.assertEqual(len(plans), 1)
        plan = plans[0]
        self.assertAlmostEqual(
            plan.best.p_satisfies_preference, plan.p_holds, places=12
        )

    def test_the_dominant_uncertainty_is_ranked_first(self) -> None:
        plan = plan_variant_evidence(
            self.session.world, self.report, self.candidates
        )[0]
        self.assertEqual(plan.best.candidate.var, self.door)
        self.assertLess(
            plan.best.posterior_target_sigma,
            plan.best.target_sigma / 5.0,
            "measuring the dominant term should collapse the margin spread",
        )

    def test_an_irrelevant_variable_carries_no_information(self) -> None:
        plan = plan_variant_evidence(
            self.session.world, self.report, self.candidates
        )[0]
        storey = next(p for p in plan.plans if p.candidate.var == self.height)
        self.assertAlmostEqual(storey.epistemic_value, 0.0, places=12)
        self.assertAlmostEqual(
            storey.posterior_target_sigma, storey.target_sigma, places=12
        )

    def test_weaker_constraints_are_answered_first(self) -> None:
        plans = plan_variant_evidence(
            self.session.world, run_invariants(self.session.world, 0.999), self.candidates
        )
        self.assertEqual(
            [p.p_holds for p in plans], sorted(p.p_holds for p in plans)
        )

    def test_planning_refuses_to_invent_an_instrument(self) -> None:
        with self.assertRaises(ValueError):
            plan_variant_evidence(self.session.world, self.report, [])


class GateReadsTheWholeReportTests(unittest.TestCase):
    """What the gate consults, and on whose threshold.

    The gate originally read only ``verification.warnings``. That left three
    holes, each of which an audit reproduced: an outright FAILED constraint
    never blocked ACCEPT, only the first variant constraint became a request,
    and the policy's own declared confidence was never applied.
    """

    def setUp(self) -> None:
        session = _variant_session()
        assessment = assess_difference(
            session.world,
            DifferenceDecision(
                session.var("Opening-1", "Height"),
                session.var("Door-1", "Height"),
                minimum_margin=0.05,
                confidence=0.95,
                label="Door-1 height fit",
            ),
        )
        self.session = session
        self.case = AcceptanceCase(
            "gate-case",
            WorkflowKind.OPENING_VERIFICATION,
            "Door-1 into Opening-1",
            (difference_check("height", assessment),),
        )
        self.review = AcceptancePolicy(
            "design-review-v1", require_verified_evidence_for_accept=False
        )

    @staticmethod
    def _result(status: Status, subject: str, p_holds: float | None) -> InvariantResult:
        return InvariantResult(
            "CONS-02", status, subject, 0.0, "detail", p_holds=p_holds, variables=()
        )

    def _evaluate(self, *results: InvariantResult, policy=None):
        return evaluate_acceptance_case(
            self.case,
            policy=policy or self.review,
            verification=VerificationReport(results),
        )

    def test_a_violated_constraint_cannot_be_accepted(self) -> None:
        """It reached ACCEPT while a merely variant one did not -- the gate was
        strictly stronger on the weaker evidence."""
        outcome = self._evaluate(self._result(Status.FAIL, "violated", 0.0))
        self.assertIs(outcome.disposition, AcceptanceDisposition.REJECT)
        self.assertFalse(outcome.may_authorize)
        self.assertEqual(outcome.failed_invariants, (("CONS-02", "violated"),))

    def test_a_violation_outranks_a_variant_constraint(self) -> None:
        outcome = self._evaluate(
            self._result(Status.WARN, "variant", 0.60),
            self._result(Status.FAIL, "violated", 0.0),
        )
        self.assertIs(outcome.disposition, AcceptanceDisposition.REJECT)

    def test_every_variant_constraint_is_asked_about(self) -> None:
        outcome = self._evaluate(
            self._result(Status.WARN, "strongest", 0.95),
            self._result(Status.WARN, "middle", 0.90),
            self._result(Status.WARN, "weakest", 0.60),
        )
        requests = [
            request
            for request in outcome.evidence_requests
            if request.action == "MEASURE_VARIANT_CONSTRAINT"
        ]
        self.assertEqual(len(requests), 3)
        self.assertEqual(
            [request.target for request in requests],
            ["weakest", "middle", "strongest"],
            "the weakest constraint is the one worth measuring first",
        )
        self.assertEqual(len({request.check_id for request in requests}), 3)

    def test_a_report_can_be_narrowed_but_not_tightened(self) -> None:
        """Reclassifying against the policy is only sound one way.

        Below its own threshold a passing probabilistic invariant is a single
        aggregate row carrying the tightest p_holds under the label "bounds",
        so the constraints between the report's confidence and a stricter
        policy's are not in the report at all. Reading them out of it gave one
        phantom constraint named after the aggregate.
        """
        lax = run_invariants(self.session.world, confidence=0.50)
        self.assertEqual(lax.confidence, 0.50)
        self.assertEqual(lax.warnings, (), "nothing is a warning at 0.50")

        tolerant = evaluate_acceptance_case(
            self.case,
            policy=replace(self.review, invariant_confidence=0.50),
            verification=lax,
        )
        self.assertIs(tolerant.disposition, AcceptanceDisposition.ACCEPT)

        strict = evaluate_acceptance_case(
            self.case,
            policy=replace(self.review, invariant_confidence=0.999),
            verification=lax,
        )
        self.assertIs(strict.disposition, AcceptanceDisposition.REQUEST_EVIDENCE)
        self.assertEqual(
            strict.variant_constraints, (), "no constraint is invented from a label"
        )
        self.assertTrue(
            any("cannot be tightened" in reason for reason in strict.reasons)
        )

    def test_narrowing_drops_a_constraint_the_report_flagged(self) -> None:
        report = run_invariants(self.session.world)
        self.assertTrue(report.warnings)
        narrowed = evaluate_acceptance_case(
            self.case,
            policy=replace(self.review, invariant_confidence=0.50),
            verification=report,
        )
        self.assertIs(narrowed.disposition, AcceptanceDisposition.ACCEPT)

    def test_a_variant_request_names_a_measurable_constraint(self) -> None:
        """Not the aggregate label the invariant reports a pass under."""
        outcome = evaluate_acceptance_case(
            self.case, policy=self.review, verification=run_invariants(self.session.world)
        )
        targets = [
            request.target
            for request in outcome.evidence_requests
            if request.action == "MEASURE_VARIANT_CONSTRAINT"
        ]
        self.assertEqual(len(targets), 1)
        self.assertNotIn(targets[0], {"bounds", "nonneg"})
        self.assertIn("<=", targets[0])

    def test_the_warn_residual_follows_the_confidence_that_fired(self) -> None:
        """It was pinned at two sigma, so a run at 0.999 recorded a number that
        contradicted the status beside it."""
        self.assertEqual(_z_for(DEFAULT_INVARIANT_CONFIDENCE), 2.0)
        world = self.session.world
        loose = next(
            r for r in run_invariants(world).warnings if r.p_holds is not None
        )
        tight = next(
            r
            for r in run_invariants(world, confidence=0.999).warnings
            if r.subject == loose.subject
        )
        self.assertGreater(_z_for(0.999), 2.0)
        self.assertNotEqual(loose.residual, tight.residual)

if __name__ == "__main__":
    unittest.main()
