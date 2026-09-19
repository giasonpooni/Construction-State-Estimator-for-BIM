"""The geometry gate installs itself by monkey-patching. Pin what that relies on.

``gat/workflows/geometry_gate.py`` ends by rebinding
``gat.workflows.acceptance.evaluate_acceptance_case`` to its gated wrapper. So
"is the geometry gate active?" is not a property of the call site, it is a
property of import order, and the gate is what stops a ``GAUSSIAN_PROXY``
clearance from closing an as-built case.

Audited and found sound: importing any submodule runs ``gat/workflows/__init__``
first, and that module's line 23 installs the gate, so every consumer in the
tree holds the gated function. These tests keep it that way. They fail if
somebody reorders ``gat/workflows/__init__.py``, introduces an import cycle that
reaches a consumer early, or rebinds the name back.

stdlib unittest only.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from pathlib import Path
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
    GatedAcceptanceOutcome,
    evaluate_acceptance_case as gated,
)


def _proxy_clearance_case() -> AcceptanceCase:
    """A satisfied clearance check whose geometry cannot close it."""
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
    return AcceptanceCase(
        "route-1", WorkflowKind.AS_BUILT_CLEARANCE, "duct", (check,)
    )


class GateBindingTests(unittest.TestCase):
    def test_every_consumer_in_the_tree_holds_the_gated_function(self) -> None:
        import gat
        import gat.demo.workflow
        import gat.headless
        import gat.workflows
        import gat.workflows.acceptance

        for module in (
            gat,
            gat.headless,
            gat.demo.workflow,
            gat.workflows,
            gat.workflows.acceptance,
        ):
            with self.subTest(module=module.__name__):
                self.assertIs(
                    module.evaluate_acceptance_case,
                    gated,
                    f"{module.__name__} holds the ungated function; the geometry "
                    "gate is not installed for its callers",
                )

    def test_the_headless_boundary_does_not_depend_on_the_patch(self) -> None:
        # headless.py imports the symbol from the package rather than from the
        # patched module, so its binding does not rely on import order at all.
        import gat.headless

        source = Path(gat.headless.__file__).read_text(encoding="utf-8")
        self.assertIn("from gat.workflows import evaluate_acceptance_case", source)

    def test_the_gate_actually_refuses_proxy_geometry(self) -> None:
        # If this passes while the binding tests fail, the gate exists and is
        # simply not reaching callers -- which is the failure mode that matters.
        outcome = gated(
            _proxy_clearance_case(),
            policy=AcceptancePolicy(
                "design-review-v1", require_verified_evidence_for_accept=False
            ),
        )
        self.assertIsInstance(outcome, GatedAcceptanceOutcome)
        self.assertEqual(outcome.disposition, AcceptanceDisposition.REQUEST_EVIDENCE)
        self.assertEqual(outcome.insufficient_geometry_check_ids, ("route-clearance",))
        self.assertFalse(outcome.may_authorize)


class GateOffSwitchTests(unittest.TestCase):
    """The gate reads a policy field that does not exist. Name both halves."""

    def test_the_shipped_policy_cannot_turn_the_gate_off(self) -> None:
        # geometry_gate does
        #     getattr(policy, "require_sufficient_geometry_for_accept", True)
        # and AcceptancePolicy has no such field, so through the shipped type the
        # answer is always True. Fail-closed, and asserted rather than assumed.
        names = {field.name for field in fields(AcceptancePolicy)}
        self.assertNotIn("require_sufficient_geometry_for_accept", names)
        self.assertTrue(
            getattr(
                AcceptancePolicy(), "require_sufficient_geometry_for_accept", True
            )
        )
        outcome = gated(_proxy_clearance_case(), policy=AcceptancePolicy())
        self.assertEqual(outcome.disposition, AcceptanceDisposition.REQUEST_EVIDENCE)

    def test_a_duck_typed_policy_can_turn_it_off_and_that_is_recorded(self) -> None:
        # The hazard stated out loud: the off switch is reachable by any object
        # carrying that attribute, and the outcome does not say it was used. A
        # caller inside the process can disable a safety gate and leave a record
        # that looks like an ordinary ACCEPT. Not reachable through gat.headless,
        # which builds AcceptancePolicy itself from the request.
        @dataclass(frozen=True)
        class LooseGeometryPolicy:
            policy_id: str = "loose-geometry-v1"
            require_verified_evidence_for_accept: bool = False
            accepted_evidence_kinds: frozenset[str] = frozenset()
            require_sufficient_geometry_for_accept: bool = False

        outcome = gated(_proxy_clearance_case(), policy=LooseGeometryPolicy())
        self.assertEqual(outcome.disposition, AcceptanceDisposition.ACCEPT)
        self.assertEqual(outcome.insufficient_geometry_check_ids, ())
        record = outcome.to_dict()
        self.assertEqual(record["insufficient_geometry_check_ids"], [])
        self.assertNotIn(
            "require_sufficient_geometry_for_accept",
            record,
            "the record does not say the geometry gate was switched off -- see "
            "docs/digest-portability-v1.md for the same defect in acceptance",
        )


if __name__ == "__main__":
    unittest.main()
