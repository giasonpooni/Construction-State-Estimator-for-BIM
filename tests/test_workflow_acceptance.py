"""Case-level scan, fabrication, and opening acceptance policy tests."""

from __future__ import annotations

from dataclasses import replace
import hashlib
import os
import unittest

import gat.demo
from gat.engine.decision import DecisionVerdict
from gat.errors import DecisionError
from gat.session import GatSession
from gat.workflows import (
    AcceptanceCase,
    AcceptanceCheck,
    AcceptanceCheckKind,
    AcceptanceDisposition,
    AcceptancePolicy,
    DifferenceDecision,
    EvidenceReceipt,
    WorkflowKind,
    assess_difference,
    difference_check,
    evaluate_acceptance_case,
)


MODEL = os.path.join(os.path.dirname(gat.demo.__file__), "model.ifc")


class WorkflowAcceptanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.session = GatSession.load_ifc(MODEL)
        cls.width = assess_difference(
            cls.session.world,
            DifferenceDecision(
                cls.session.var("Opening-1", "Width"),
                cls.session.var("Door-1", "Width"),
                minimum_margin=0.05,
                confidence=0.95,
                label="door-to-opening width fit",
            ),
        )
        cls.height = assess_difference(
            cls.session.world,
            DifferenceDecision(
                cls.session.var("Opening-1", "Height"),
                cls.session.var("Door-1", "Height"),
                minimum_margin=0.05,
                confidence=0.95,
                label="door-to-opening height fit",
            ),
        )
        cls.case = AcceptanceCase(
            "opening-fit-1",
            WorkflowKind.OPENING_VERIFICATION,
            "Door-1 into Opening-1",
            (
                difference_check("width", cls.width),
                difference_check("height", cls.height),
            ),
        )

    def receipt(self, *check_ids: str, world_digest: str | None = None) -> EvidenceReceipt:
        digest = self.session.world.digest()
        return EvidenceReceipt(
            receipt_id="survey-receipt-1",
            evidence_kind="calibrated-scan-clearance-likelihood",
            evidence_digest=hashlib.sha256(b"survey-evidence").hexdigest(),
            prior_world_digest=hashlib.sha256(b"prior-world").hexdigest(),
            result_world_digest=world_digest or digest,
            calibration_id="survey-control-A",
            check_ids=tuple(check_ids),
            ledger_event_hash=hashlib.sha256(b"ledger-event").hexdigest(),
            verification_passed=True,
        )

    def test_opening_width_and_height_are_joint_belief_checks(self) -> None:
        self.assertEqual(self.width.verdict, DecisionVerdict.SATISFIED)
        self.assertEqual(self.height.verdict, DecisionVerdict.SATISFIED)
        self.assertGreater(self.width.margin_mean, 0.05)
        self.assertGreater(self.height.margin_mean, 0.05)
        self.assertGreater(self.width.margin_sigma, 0.0)

    def test_satisfied_as_built_case_requests_evidence_by_default(self) -> None:
        outcome = evaluate_acceptance_case(self.case)
        self.assertEqual(outcome.disposition, AcceptanceDisposition.REQUEST_EVIDENCE)
        self.assertEqual(outcome.uncovered_check_ids, ("width", "height"))
        self.assertFalse(outcome.may_authorize)
        self.assertEqual(len(outcome.evidence_requests), 2)

    def test_one_verified_receipt_can_cover_a_multi_check_opening_case(self) -> None:
        outcome = evaluate_acceptance_case(
            self.case, (self.receipt("width", "height"),)
        )
        self.assertEqual(outcome.disposition, AcceptanceDisposition.ACCEPT)
        self.assertTrue(outcome.may_authorize)
        self.assertEqual(outcome.evidence_receipt_ids, ("survey-receipt-1",))
        self.assertEqual(outcome.evidence_requests, ())

    def test_acceptance_is_still_not_an_approval(self) -> None:
        outcome = evaluate_acceptance_case(
            self.case, (self.receipt("width", "height"),)
        )
        rendered = outcome.to_dict()
        self.assertTrue(rendered["may_authorize"])
        self.assertNotIn("approved", rendered)
        self.assertNotIn("authority", rendered)

    def test_a_violated_check_rejects_the_whole_case(self) -> None:
        violated = assess_difference(
            self.session.world,
            DifferenceDecision(
                self.session.var("Opening-1", "Width"),
                self.session.var("Door-1", "Width"),
                minimum_margin=0.20,
                confidence=0.95,
                label="fabrication width tolerance",
            ),
        )
        self.assertEqual(violated.verdict, DecisionVerdict.VIOLATED)
        case = AcceptanceCase(
            "prefab-fit-1",
            WorkflowKind.PREFABRICATION_FIT,
            "prefabricated door assembly",
            (
                difference_check("width", violated),
                difference_check("height", self.height),
            ),
        )
        outcome = evaluate_acceptance_case(
            case, (self.receipt("width", "height"),)
        )
        self.assertEqual(outcome.disposition, AcceptanceDisposition.REJECT)
        self.assertEqual(outcome.rejected_check_ids, ("width",))
        self.assertFalse(outcome.may_authorize)

    def test_stale_receipt_fails_closed(self) -> None:
        stale = self.receipt(
            "width", "height", world_digest=hashlib.sha256(b"stale").hexdigest()
        )
        with self.assertRaisesRegex(DecisionError, "stale"):
            evaluate_acceptance_case(self.case, (stale,))

    def test_policy_can_explicitly_assess_design_only_without_as_built_evidence(self) -> None:
        design_policy = AcceptancePolicy(
            "design-review-v1",
            require_verified_evidence_for_accept=False,
        )
        outcome = evaluate_acceptance_case(self.case, policy=design_policy)
        self.assertEqual(outcome.disposition, AcceptanceDisposition.ACCEPT)

    def test_case_digest_is_deterministic_and_state_bound(self) -> None:
        same = AcceptanceCase(
            self.case.case_id,
            self.case.workflow,
            self.case.subject,
            self.case.checks,
        )
        self.assertEqual(self.case.scope_digest, same.scope_digest)
        changed_check = replace(
            self.case.checks[0],
            p_satisfies_lower=self.case.checks[0].p_satisfies_lower - 1e-6,
        )
        changed = AcceptanceCase(
            self.case.case_id,
            self.case.workflow,
            self.case.subject,
            (changed_check, self.case.checks[1]),
        )
        self.assertNotEqual(self.case.scope_digest, changed.scope_digest)


class VerdictExhaustivenessTests(unittest.TestCase):
    """A verdict the policy cannot dispose of must not be read as satisfied.

    ``evaluate_acceptance_case`` sorts checks into violated, unresolved and
    satisfied and then tests those three in order, so a verdict in none of
    them reaches no refusal branch and falls through to ACCEPT. Today
    ``DecisionVerdict`` has exactly those three members and the partition is
    exact -- which is why nothing caught it -- but the failure direction of a
    fourth is acceptance, silently, with every existing test still green.
    The same shape once let a MARGINAL compliance row pass as a clean one.
    """

    DIGEST = "a" * 64

    def _check(self, check_id: str, verdict) -> AcceptanceCheck:
        return AcceptanceCheck(
            check_id=check_id,
            kind=AcceptanceCheckKind.MINIMUM,
            subject="subject",
            verdict=verdict,
            confidence=0.95,
            p_satisfies_lower=0.99,
            p_satisfies_upper=0.99,
            world_digest=self.DIGEST,
        )

    def _case(self, *checks) -> AcceptanceCase:
        return AcceptanceCase(
            "case-1", WorkflowKind.AS_BUILT_CLEARANCE, "subject", checks
        )

    def test_the_three_known_verdicts_still_dispose_normally(self) -> None:
        policy = AcceptancePolicy(require_verified_evidence_for_accept=False)
        for verdict, expected in (
            (DecisionVerdict.SATISFIED, AcceptanceDisposition.ACCEPT),
            (DecisionVerdict.VIOLATED, AcceptanceDisposition.REJECT),
            (DecisionVerdict.UNRESOLVED, AcceptanceDisposition.REQUEST_EVIDENCE),
        ):
            with self.subTest(verdict=verdict):
                case = self._case(self._check("C1", verdict))
                self.assertIs(
                    evaluate_acceptance_case(case, policy=policy).disposition,
                    expected,
                )

    def test_a_verdict_the_policy_cannot_dispose_of_is_refused(self) -> None:
        """Written past the dataclass guard on purpose: the point is what the
        evaluator does with a verdict it was never taught, not whether the
        constructor would have built one."""
        good = self._check("C1", DecisionVerdict.SATISFIED)
        stranded = self._check("C2", DecisionVerdict.SATISFIED)
        case = self._case(good, stranded)
        object.__setattr__(stranded, "verdict", "MARGINAL")

        with self.assertRaises(DecisionError) as caught:
            evaluate_acceptance_case(
                case, policy=AcceptancePolicy(require_verified_evidence_for_accept=False)
            )
        message = str(caught.exception)
        self.assertIn("MARGINAL", message)
        self.assertIn("C2", message)
        self.assertNotIn("C1", message)


if __name__ == "__main__":
    unittest.main()
