"""Geometry authority is part of the decision contract, not a footnote."""

from __future__ import annotations

import importlib
import unittest

import os

import gat.demo
from gat.engine.decision import DecisionVerdict, MinimumDecision, assess_decision
from gat.engineering.beam import DECLARATION_BACKED_QUANTITIES
from gat.session import GatSession
from gat.workflows.acceptance import (
    AcceptanceCase,
    AcceptanceCheck,
    AcceptanceCheckKind,
    AcceptanceDisposition,
    AcceptancePolicy,
    WorkflowKind,
    minimum_check,
)
from gat.workflows.geometry_gate import (
    check_geometry_authority,
    evaluate_acceptance_case,
    evaluate_acceptance_case as gated_evaluator,
    evaluate_acceptance_case_ungated as ungated_evaluator,
)
from gat.workflows.geometry_authority import (
    GeometryAuthority,
    authority_from_beam_status,
    geometry_sufficient,
)


BEAM_MODEL = os.path.join(os.path.dirname(gat.demo.__file__), "beam_model.ifc")


class GeometryAuthorityTests(unittest.TestCase):
    def test_quantity_fit_is_sufficient_without_solids(self) -> None:
        self.assertTrue(
            geometry_sufficient("DIFFERENCE", GeometryAuthority.QUANTITY_ONLY)
        )

    def test_gaussian_proxy_cannot_close_clearance(self) -> None:
        self.assertFalse(
            geometry_sufficient("CLEARANCE", GeometryAuthority.GAUSSIAN_PROXY)
        )

    def test_scan_receipt_upgrades_clearance(self) -> None:
        self.assertTrue(
            geometry_sufficient(
                "CLEARANCE",
                GeometryAuthority.GAUSSIAN_PROXY,
                scan_covered=True,
            )
        )

    def test_length_only_beam_is_not_section_authority(self) -> None:
        self.assertEqual(
            authority_from_beam_status("LENGTH_ONLY"),
            GeometryAuthority.LENGTH_ONLY,
        )
        self.assertFalse(
            geometry_sufficient("MINIMUM", GeometryAuthority.LENGTH_ONLY)
        )

    def test_evaluate_refuses_gaussian_proxy_clearance(self) -> None:
        check = AcceptanceCheck(
            "route-clearance",
            AcceptanceCheckKind.CLEARANCE,
            "duct",
            DecisionVerdict.SATISFIED,
            0.95,
            0.99,
            0.99,
            "a" * 64,
            details={"geometry_authority": "GAUSSIAN_PROXY"},
        )
        outcome = evaluate_acceptance_case(
            AcceptanceCase(
                "route-1",
                WorkflowKind.AS_BUILT_CLEARANCE,
                "duct",
                (check,),
            ),
            policy=AcceptancePolicy(
                "design-review-v1",
                require_verified_evidence_for_accept=False,
            ),
        )
        self.assertEqual(outcome.disposition, AcceptanceDisposition.REQUEST_EVIDENCE)
        self.assertEqual(outcome.insufficient_geometry_check_ids, ("route-clearance",))
        self.assertEqual(
            outcome.to_dict()["checks"][0]["geometry_authority"], "GAUSSIAN_PROXY"
        )

    def test_complete_swept_solid_maps_to_swept_solid(self) -> None:
        self.assertEqual(
            authority_from_beam_status("COMPLETE"),
            GeometryAuthority.SWEPT_SOLID,
        )
        self.assertTrue(
            geometry_sufficient("CLEARANCE", GeometryAuthority.SWEPT_SOLID)
        )


class GatedEvaluatorReachabilityTests(unittest.TestCase):
    """Every way of reaching the evaluator reaches the gated one.

    Two functions share the name ``evaluate_acceptance_case``: the numerical
    policy in :mod:`gat.workflows.acceptance`, which scores verdicts and
    evidence coverage and never asks whether a check had the geometric
    authority to close the case, and the gated wrapper in
    :mod:`gat.workflows.geometry_gate`. ``from gat.workflows.acceptance
    import evaluate_acceptance_case`` reads exactly like the safe one.

    It is the safe one, because ``geometry_gate`` rebinds the base module's
    attribute on import. That rebinding is a real guarantee and an invisible
    one: nothing tested it, so deleting one line at the foot of that module,
    or dropping one import from ``gat/workflows/__init__.py``, would have
    turned the gate off everywhere it is reached by that name -- silently,
    with every existing test still green.
    """

    #: Public paths a caller might plausibly take.
    PATHS = (
        ("gat", "evaluate_acceptance_case"),
        ("gat.workflows", "evaluate_acceptance_case"),
        ("gat.workflows.acceptance", "evaluate_acceptance_case"),
        ("gat.workflows.geometry_gate", "evaluate_acceptance_case"),
        ("gat.headless", "evaluate_acceptance_case"),
    )

    def test_every_public_path_resolves_to_the_gated_evaluator(self) -> None:
        for module_name, attribute in self.PATHS:
            with self.subTest(path=f"{module_name}.{attribute}"):
                resolved = getattr(importlib.import_module(module_name), attribute)
                self.assertIs(resolved, gated_evaluator)

    def test_the_numerical_layer_is_still_reachable_by_its_own_name(self) -> None:
        """The wrapper calls it, so it must not have been replaced outright --
        only the ambiguous name was rebound."""
        self.assertIsNot(ungated_evaluator, gated_evaluator)
        self.assertEqual(
            ungated_evaluator.__module__, "gat.workflows.acceptance"
        )

    def test_the_untrusted_boundary_does_not_depend_on_the_rebinding(self) -> None:
        """``gat.headless`` takes JSON from outside and must be gated because
        it asked to be, not because another module patched an attribute
        before it looked. Undo the rebinding, reload it, and check.
        """
        acceptance = importlib.import_module("gat.workflows.acceptance")
        saved = acceptance.evaluate_acceptance_case
        try:
            acceptance.evaluate_acceptance_case = ungated_evaluator
            headless = importlib.reload(importlib.import_module("gat.headless"))
            self.assertIs(headless.evaluate_acceptance_case, gated_evaluator)
        finally:
            acceptance.evaluate_acceptance_case = saved
            importlib.reload(importlib.import_module("gat.headless"))

    def test_the_two_evaluators_actually_differ_on_a_case(self) -> None:
        """If they agreed everywhere the checks above would prove nothing."""
        check = AcceptanceCheck(
            check_id="C1",
            kind=AcceptanceCheckKind.CLEARANCE,   # defaults to GAUSSIAN_PROXY
            subject="duct vs beam",
            verdict=DecisionVerdict.SATISFIED,
            confidence=0.95,
            p_satisfies_lower=0.99,
            p_satisfies_upper=0.99,
            world_digest="a" * 64,
        )
        case = AcceptanceCase(
            "case-1", WorkflowKind.AS_BUILT_CLEARANCE, "duct", (check,)
        )
        policy = AcceptancePolicy(require_verified_evidence_for_accept=False)

        self.assertIs(
            ungated_evaluator(case, (), (), policy).disposition,
            AcceptanceDisposition.ACCEPT,
        )
        self.assertIs(
            gated_evaluator(case, (), (), policy).disposition,
            AcceptanceDisposition.REQUEST_EVIDENCE,
        )


class TargetDrivenAuthorityTests(unittest.TestCase):
    """A check's support follows from what it is about, not what it is called.

    ``check_geometry_authority`` read the check's *kind*: CLEARANCE meant
    GAUSSIAN_PROXY, CAPACITY meant INSUFFICIENT, and everything else took
    QUANTITY_ONLY -- the dimensional-quantity default. So the identical
    criterion, P(DesignMomentCapacity >= factored demand), reached
    REQUEST_EVIDENCE as a CAPACITY check and ACCEPT with ``may_authorize``
    True as a MINIMUM one, on the same world, to the same last bit of
    ``target_mean`` and ``p_satisfies``. The stored check then positively
    asserted QUANTITY_ONLY support for a verdict resting on a section modulus
    nobody measured.

    It was reachable from outside: ``gat.headless`` accepts a ``minimum``
    check over any ``{entity_name, quantity}`` pair and has no capacity kind
    at all, so relabelling was the only way to ask a capacity question there.
    """

    DIGEST = "b" * 64

    def _check(self, kind, details) -> AcceptanceCheck:
        return AcceptanceCheck(
            check_id="C1",
            kind=kind,
            subject="Beam-B1 factored bending",
            verdict=DecisionVerdict.SATISFIED,
            confidence=0.95,
            p_satisfies_lower=0.99,
            p_satisfies_upper=0.99,
            world_digest=self.DIGEST,
            details=details,
        )

    def _disposition(self, check) -> AcceptanceDisposition:
        case = AcceptanceCase(
            "case-1", WorkflowKind.AS_BUILT_CLEARANCE, "Beam-B1", (check,)
        )
        policy = AcceptancePolicy(require_verified_evidence_for_accept=False)
        return gated_evaluator(case, (), (), policy).disposition

    def test_a_declaration_backed_target_is_declared_property_whatever_the_kind(
        self,
    ) -> None:
        for kind in (AcceptanceCheckKind.MINIMUM, AcceptanceCheckKind.DIFFERENCE):
            for quantity in sorted(DECLARATION_BACKED_QUANTITIES):
                with self.subTest(kind=kind, quantity=quantity):
                    check = self._check(kind, {"target_quantities": [quantity]})
                    self.assertIs(
                        check_geometry_authority(check),
                        GeometryAuthority.DECLARED_PROPERTY,
                    )
                    self.assertIs(
                        self._disposition(check),
                        AcceptanceDisposition.REQUEST_EVIDENCE,
                    )

    def test_one_declared_target_in_a_difference_is_enough_to_close_it(self) -> None:
        """A difference against a declared capacity is still a capacity
        question: the declaration is on one side of the subtraction."""
        check = self._check(
            AcceptanceCheckKind.DIFFERENCE,
            {"target_quantities": ["DesignMomentCapacity", "Width"]},
        )
        self.assertIs(
            check_geometry_authority(check), GeometryAuthority.DECLARED_PROPERTY
        )

    def test_dimensional_targets_still_take_the_quantity_default(self) -> None:
        for kind in (AcceptanceCheckKind.MINIMUM, AcceptanceCheckKind.DIFFERENCE):
            with self.subTest(kind=kind):
                check = self._check(
                    kind, {"target_quantities": ["Width", "Height"]}
                )
                self.assertIs(
                    check_geometry_authority(check), GeometryAuthority.QUANTITY_ONLY
                )
                self.assertIs(
                    self._disposition(check), AcceptanceDisposition.ACCEPT
                )

    def test_a_structural_kind_that_names_no_target_falls_closed(self) -> None:
        """Unknown is not a licence. A check that reaches the gate without
        saying what it is about cannot be shown to be dimensional, and
        treating unknown as dimensional is the assumption that caused this."""
        for kind in (AcceptanceCheckKind.MINIMUM, AcceptanceCheckKind.DIFFERENCE):
            with self.subTest(kind=kind):
                check = self._check(kind, {})
                self.assertIs(
                    check_geometry_authority(check), GeometryAuthority.INSUFFICIENT
                )
                self.assertIs(
                    self._disposition(check),
                    AcceptanceDisposition.REQUEST_EVIDENCE,
                )

    def test_a_declared_authority_already_on_the_check_still_wins(self) -> None:
        """The corroborated route records its own support; the target rule
        must not overwrite a check that already earned a better one."""
        check = self._check(
            AcceptanceCheckKind.MINIMUM,
            {
                "target_quantities": ["DesignMomentCapacity"],
                "geometry_authority": GeometryAuthority.DECLARED_CORROBORATED.value,
            },
        )
        self.assertIs(
            check_geometry_authority(check), GeometryAuthority.DECLARED_CORROBORATED
        )
        self.assertIs(self._disposition(check), AcceptanceDisposition.ACCEPT)

    def test_a_malformed_target_list_is_not_a_way_through(self) -> None:
        """``details`` comes from JSON. A target that is not a list of names
        must not be read as 'no declared quantity here'."""
        for details in (
            {"target_quantities": "DesignMomentCapacity"},
            {"target_quantities": None},
            {"target_quantities": 7},
            {"target_quantities": {"q": "DesignMomentCapacity"}},
        ):
            with self.subTest(details=details):
                check = self._check(AcceptanceCheckKind.MINIMUM, details)
                self.assertIs(
                    check_geometry_authority(check), GeometryAuthority.INSUFFICIENT
                )


class RelabelledCapacityTests(unittest.TestCase):
    """The end-to-end shape of the defect, on the real beam model.

    Built through the library's own constructors, over a world loaded from
    ``beam_model.ifc``, so it fails if ``minimum_check`` ever stops recording
    its target or if the beam's declared quantities are renamed.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.session = GatSession.load_ifc(BEAM_MODEL)
        cls.beam = cls.session.entity_by_name("Beam-B1")

    def _minimum_over(self, quantity: str, minimum: float) -> AcceptanceCheck:
        decision = MinimumDecision(
            target=self.session.var("Beam-B1", quantity),
            minimum=minimum,
            confidence=0.95,
            label=f"Beam-B1 {quantity}",
        )
        return minimum_check(
            "b1", assess_decision(self.session.world, decision)
        )

    def test_the_capacity_criterion_cannot_be_laundered_through_minimum(
        self,
    ) -> None:
        check = self._minimum_over("DesignMomentCapacity", 301_000.0)
        self.assertIs(check.verdict, DecisionVerdict.SATISFIED)
        self.assertIs(
            check_geometry_authority(check), GeometryAuthority.DECLARED_PROPERTY
        )
        case = AcceptanceCase(
            "beam-capacity-as-minimum",
            WorkflowKind.AS_BUILT_CLEARANCE,
            "Beam-B1 factored bending",
            (check,),
        )
        outcome = gated_evaluator(
            case, (), (), AcceptancePolicy(require_verified_evidence_for_accept=False)
        )
        self.assertIs(outcome.disposition, AcceptanceDisposition.REQUEST_EVIDENCE)
        self.assertFalse(outcome.may_authorize)
        self.assertEqual(outcome.insufficient_geometry_check_ids, ("b1",))

    def test_the_rendered_check_no_longer_claims_quantity_support(self) -> None:
        """The recorded authority is part of the artifact a reviewer reads."""
        check = self._minimum_over("DesignMomentCapacity", 301_000.0)
        case = AcceptanceCase(
            "beam-capacity-as-minimum",
            WorkflowKind.AS_BUILT_CLEARANCE,
            "Beam-B1",
            (check,),
        )
        rendered = gated_evaluator(
            case, (), (), AcceptancePolicy(require_verified_evidence_for_accept=False)
        ).to_dict()
        self.assertEqual(
            [c["geometry_authority"] for c in rendered["checks"]],
            [GeometryAuthority.DECLARED_PROPERTY.value],
        )

    def test_a_dimensional_minimum_on_the_same_beam_is_unaffected(self) -> None:
        """The fix must not close questions that geometry does answer."""
        check = self._minimum_over("Length", 0.1)
        self.assertIs(
            check_geometry_authority(check), GeometryAuthority.QUANTITY_ONLY
        )

    def test_the_untrusted_boundary_refuses_it_too(self) -> None:
        """``gat.headless`` has no capacity kind, so relabelling is the only
        way to ask a capacity question there. It reached ACCEPT with
        ``may_authorize`` True, zero evidence requests, and a recorded
        QUANTITY_ONLY support."""
        headless = importlib.import_module("gat.headless")
        response = headless.handle_request(
            {
                "format": headless.REQUEST_FORMAT,
                "request_id": "relabel-1",
                "operation": "acceptance",
                "state": {"kind": "ifc", "path": BEAM_MODEL},
                "payload": {
                    "case_id": "beam-capacity-as-minimum",
                    "workflow": "AS_BUILT_CLEARANCE",
                    "subject": "Beam-B1 factored bending",
                    "checks": [
                        {
                            "kind": "minimum",
                            "check_id": "b1",
                            "target": {
                                "entity_name": "Beam-B1",
                                "quantity": "DesignMomentCapacity",
                            },
                            "minimum": 301_000.0,
                            "confidence": 0.95,
                            "label": "Beam-B1 factored bending",
                        }
                    ],
                    "policy": {
                        "policy_id": "design-review-v1",
                        "require_verified_evidence_for_accept": False,
                        "accepted_evidence_kinds": [
                            "calibrated-scan-clearance-likelihood"
                        ],
                    },
                },
            }
        )
        result = response["result"]
        self.assertEqual(
            result["disposition"], AcceptanceDisposition.REQUEST_EVIDENCE.value
        )
        self.assertFalse(result["may_authorize"])
        self.assertEqual(
            [c["geometry_authority"] for c in result["checks"]],
            [GeometryAuthority.DECLARED_PROPERTY.value],
        )
        self.assertEqual(
            [r["action"] for r in result["evidence_requests"]],
            ["ACQUIRE_CALIBRATED_EVIDENCE"],
        )

    def test_there_is_still_no_capacity_kind_at_that_boundary(self) -> None:
        """If one is ever added it must carry its own support, not inherit
        this rule by accident."""
        headless = importlib.import_module("gat.headless")
        with self.assertRaisesRegex(ValueError, "unsupported acceptance check kind"):
            headless.handle_request(
                {
                    "format": headless.REQUEST_FORMAT,
                    "request_id": "relabel-2",
                    "operation": "acceptance",
                    "state": {"kind": "ifc", "path": BEAM_MODEL},
                    "payload": {
                        "case_id": "c",
                        "workflow": "AS_BUILT_CLEARANCE",
                        "subject": "Beam-B1",
                        "checks": [{"kind": "capacity", "check_id": "b1"}],
                    },
                }
            )


if __name__ == "__main__":
    unittest.main()
