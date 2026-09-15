"""Geometry authority is part of the decision contract, not a footnote."""

from __future__ import annotations

import importlib
import unittest

from gat.engine.decision import DecisionVerdict
from gat.workflows.acceptance import (
    AcceptanceCase,
    AcceptanceCheck,
    AcceptanceCheckKind,
    AcceptanceDisposition,
    AcceptancePolicy,
    WorkflowKind,
)
from gat.workflows.geometry_gate import (
    evaluate_acceptance_case,
    evaluate_acceptance_case as gated_evaluator,
    evaluate_acceptance_case_ungated as ungated_evaluator,
)
from gat.workflows.geometry_authority import (
    GeometryAuthority,
    authority_from_beam_status,
    geometry_sufficient,
)


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


if __name__ == "__main__":
    unittest.main()
