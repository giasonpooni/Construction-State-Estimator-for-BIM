"""u_c arrives as noise_sigma, and nothing else crosses.

RCI owns uncertainty-budget-v1: Type A and Type B components, the GUM law of
propagation, Welch-Satterthwaite, coverage factors, a Monte Carlo cross-check.
CSE sees one number. These tests pin the seam in both directions -- that a valid
budget conditions exactly one slot, and that everything which would widen the
seam is refused.

The bottom class runs against the installed RCI package when there is one, which
is where "agreement, not import" is actually checked.

stdlib unittest only.
"""

from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
import unittest

import gat.demo
from gat.adapters.budget_cite import (
    ADMISSIBLE_TRACEABILITY,
    BUDGET_SCHEMA,
    BudgetCiteError,
    budget_digest,
    check_cite,
    observe_from_budget,
    read_budget,
)
from gat.session import GatSession

BIND_FILE = Path(__file__).resolve().parents[1] / "validation" / "cse-point-bind-v1.json"


def rci_available() -> bool:
    try:
        return importlib.util.find_spec("instrument_chain") is not None
    except (ImportError, ValueError):
        return False


def _budget(**overrides) -> dict:
    """A budget record of the shape RCI's Budget.to_record() produces."""
    record = {
        "schema": BUDGET_SCHEMA,
        "measurand": "Width",
        "unit": "m",
        "components": [
            {
                "type": "A",
                "source": "repeat-readings",
                "s": 0.0042,
                "n": 10,
                "statistic": "mean",
                "c": 1.0,
                "unit": "m",
                "u": 0.0013281566172707193,
                "dof": 9.0,
            },
            {
                "type": "B",
                "source": "tape-resolution",
                "dist": "rectangular",
                "half_width": 0.0005,
                "c": 1.0,
                "unit": "m",
                "u": 0.0002886751345948129,
                "dof": None,
            },
        ],
        "correlations": [],
        "combination": "gum_lpu",
        "u_c": 0.0013591664111996487,
        "dof_eff": 10.7,
        "p": 0.95,
        "k": 2.21,
        "U": 0.003,
        "contributions": [],
        "traceability": "none_claimed",
    }
    record.update(overrides)
    return record


def _cite(record: dict, **overrides) -> dict:
    cite = {
        "schema": "rci-budget-cite-v1",
        "budget_schema": BUDGET_SCHEMA,
        "budget_digest": budget_digest(record),
        "measurand": record["measurand"],
        "unit": record["unit"],
        "u_c": record["u_c"],
        "traceability": record["traceability"],
    }
    cite.update(overrides)
    return cite


def _bind(**payload_overrides) -> dict:
    bind = json.loads(BIND_FILE.read_text(encoding="utf-8"))
    bind["payload"].update(payload_overrides)
    return bind


class AdmittedBudgetTests(unittest.TestCase):
    def test_u_c_is_read_not_recomputed(self) -> None:
        # The seam's whole point: CSE combines nothing. The admitted u_c is the
        # number RCI put in the record, to the bit.
        record = _budget()
        admitted = read_budget(record)
        self.assertEqual(admitted.u_c, record["u_c"])
        self.assertEqual(admitted.measurand, "Width")
        self.assertEqual(admitted.unit, "m")
        self.assertEqual(admitted.component_count, 2)

    def test_the_record_says_it_did_not_compute_the_budget(self) -> None:
        document = read_budget(_budget()).as_dict()
        self.assertEqual(document["law_applied"]["budget_schema"], BUDGET_SCHEMA)
        self.assertIn("u_c was read, not recomputed", document["law_applied"]["note"])
        self.assertIn(
            "CSE did not verify traceability and admits only none_claimed",
            document["not_claimed"],
        )

    def test_the_digest_ignores_how_the_budget_was_reported(self) -> None:
        # Same budget at 95% and 99% is one budget. If the digest moved with p, a
        # cite written at one coverage could not be checked against a record
        # serialised at another.
        at_95 = _budget(p=0.95, k=2.21, U=0.003)
        at_99 = _budget(p=0.99, k=3.17, U=0.0043)
        self.assertEqual(budget_digest(at_95), budget_digest(at_99))

    def test_the_digest_moves_with_a_component(self) -> None:
        moved = _budget()
        moved["components"][0]["s"] = 0.0043
        self.assertNotEqual(budget_digest(moved), budget_digest(_budget()))


class TraceabilityTests(unittest.TestCase):
    def test_only_none_claimed_is_admitted(self) -> None:
        self.assertEqual(ADMISSIBLE_TRACEABILITY, "none_claimed")
        read_budget(_budget())  # does not raise

    def test_a_traceable_budget_is_refused_rather_than_promoted(self) -> None:
        """A traceable budget is not worse. It is not admissible through this seam.

        CSE cannot verify a traceability chain, so admitting a record that asserts
        one would have the estimator repeat a statement about national standards
        that nothing here checked.
        """
        for claim in ("si-traceable", "nist", "traceable", "", None):
            with self.subTest(claim=claim):
                with self.assertRaisesRegex(BudgetCiteError, "traceability"):
                    read_budget(_budget(traceability=claim))


class CiteAgreementTests(unittest.TestCase):
    def test_a_cite_must_match_the_budget_it_names(self) -> None:
        record = _budget()
        check_cite(_cite(record), record)  # agrees

        with self.assertRaisesRegex(BudgetCiteError, "budget_digest"):
            check_cite(_cite(record, budget_digest="0" * 64), record)

    def test_a_cite_may_not_contradict_its_budgets_u_c(self) -> None:
        # A cite carries u_c so a reader need not re-derive it. That convenience
        # is also how a cite could lie about the budget it points at.
        record = _budget()
        with self.assertRaisesRegex(BudgetCiteError, "combines to"):
            check_cite(_cite(record, u_c=0.001), record)

    def test_a_cite_is_optional_but_the_budget_is_not(self) -> None:
        record = _budget()
        self.assertEqual(read_budget(record).u_c, record["u_c"])


class MalformedBudgetTests(unittest.TestCase):
    def test_wrong_schema(self) -> None:
        with self.assertRaisesRegex(BudgetCiteError, "budget schema must be"):
            read_budget(_budget(schema="uncertainty-budget-v2"))

    def test_no_components(self) -> None:
        with self.assertRaisesRegex(BudgetCiteError, "no components"):
            read_budget(_budget(components=[]))

    def test_no_unit(self) -> None:
        record = _budget()
        del record["unit"]
        with self.assertRaisesRegex(BudgetCiteError, "declared unit"):
            read_budget(record)

    def test_u_c_of_zero_claims_an_exact_measurement(self) -> None:
        with self.assertRaisesRegex(BudgetCiteError, "positive"):
            read_budget(_budget(u_c=0.0))

    def test_nan_and_infinite_u_c_are_told_apart(self) -> None:
        # They are different mistakes and the message says which.
        with self.assertRaisesRegex(BudgetCiteError, "NaN.*absent uncertainty"):
            read_budget(_budget(u_c=float("nan")))
        with self.assertRaisesRegex(BudgetCiteError, "infinite.*refusal to state"):
            read_budget(_budget(u_c=float("inf")))

    def test_a_non_finite_number_buried_in_a_component_is_named(self) -> None:
        """Found by a test, not by reading.

        The field checks never look inside components, and canonical_digest sets
        allow_nan=False, so this escaped as "Out of range float values are not
        JSON compliant" from the JSON encoder -- true, and it names neither the
        budget nor the component.
        """
        record = _budget()
        record["components"][0]["u"] = float("nan")
        with self.assertRaisesRegex(BudgetCiteError, "non-finite number"):
            read_budget(record)

        correlated = _budget(correlations=[{"a": "x", "b": "y", "r": float("inf")}])
        with self.assertRaisesRegex(BudgetCiteError, "non-finite number"):
            read_budget(correlated)


class TheBindGatesTheObservationTests(unittest.TestCase):
    """An observation reaches the kernel only after a bind names the quantity."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.model = str(Path(gat.demo.__file__).resolve().parent / "model.ifc")

    def setUp(self) -> None:
        self.session = GatSession.load_ifc(self.model)
        self.var = self.session.var("Opening-1", "Width")
        entity = self.session.world.module.entities[
            self.session.entity_by_name("Opening-1")
        ]
        self.slot_unit = entity.slots["Width"].unit.value

    def _observe(self, **kwargs):
        record = kwargs.pop("budget", None) or _budget()
        bind = kwargs.pop("bind", None) or _bind()
        return observe_from_budget(
            kwargs.pop("var", self.var),
            kwargs.pop("value", 1.002),
            record,
            bind=bind,
            slot_unit=kwargs.pop("slot_unit", self.slot_unit),
            cite=kwargs.pop("cite", _cite(record)),
        )

    def test_a_valid_budget_and_bind_condition_exactly_one_slot(self) -> None:
        before_mean = self.session.world.full.mean(self.var)
        before_std = self.session.world.full.std(self.var)
        transform, record = self._observe()

        self.assertEqual(record["observed"]["noise_sigma"], _budget()["u_c"])
        self.assertEqual(record["observed"]["bind_point_id"], "P-Opening-1")

        self.session.run(transform)
        after_std = self.session.world.full.std(self.var)
        self.assertLess(after_std, before_std)
        self.assertNotEqual(self.session.world.full.mean(self.var), before_mean)

        # The posterior is the ordinary Gaussian update on the declared sigma --
        # no part of the budget survives into the belief except its u_c.
        prior_precision = 1.0 / before_std**2
        noise_precision = 1.0 / _budget()["u_c"] ** 2
        expected = (prior_precision + noise_precision) ** -0.5
        self.assertAlmostEqual(after_std, expected, places=12)

    def test_a_bind_with_no_quantity_is_refused(self) -> None:
        bind = _bind()
        del bind["payload"]["quantity"]
        with self.assertRaisesRegex(BudgetCiteError, "names no quantity"):
            self._observe(bind=bind)

    def test_a_bind_for_another_quantity_cannot_condition_this_one(self) -> None:
        with self.assertRaisesRegex(BudgetCiteError, "does not\\s+condition another"):
            self._observe(bind=_bind(quantity="Height"))

    def test_the_bind_and_the_observed_variable_must_agree(self) -> None:
        height = self.session.var("Opening-1", "Height")
        with self.assertRaisesRegex(BudgetCiteError, "observation targets"):
            self._observe(var=height)

    def test_a_unit_mismatch_is_not_silently_converted(self) -> None:
        with self.assertRaisesRegex(BudgetCiteError, "does not convert"):
            self._observe(slot_unit="mm")

    def test_a_non_finite_observed_value_is_refused(self) -> None:
        for value in (float("nan"), float("inf")):
            with self.subTest(value=value):
                with self.assertRaisesRegex(BudgetCiteError, "must be finite"):
                    self._observe(value=value)

    def test_nothing_is_observed_when_the_seam_refuses(self) -> None:
        before = self.session.world.digest()
        with self.assertRaises(BudgetCiteError):
            self._observe(slot_unit="mm")
        self.assertEqual(self.session.world.digest(), before)


@unittest.skipUnless(rci_available(), "RCI clone is not importable")
class AgreementWithRciTests(unittest.TestCase):
    """Agreement, not import. Checked where RCI is actually installed."""

    def test_the_schema_name_matches_the_companion(self) -> None:
        from instrument_chain.uncertainty_budget import SCHEMA

        self.assertEqual(BUDGET_SCHEMA, SCHEMA)

    def test_the_default_traceability_matches_the_companion(self) -> None:
        from instrument_chain.uncertainty_budget import Budget

        self.assertEqual(Budget(measurand="x").traceability, ADMISSIBLE_TRACEABILITY)

    def test_the_two_canonical_digests_agree(self) -> None:
        """The load-bearing coincidence, asserted.

        A cite's digest is computed in RCI and verified in CSE by two independent
        canonical_digest implementations. If they ever disagree on key order,
        unicode, negative zero or an extreme float, every cite fails verification
        for a reason no message would explain.
        """
        from gat.adapters.external_commitment import canonical_digest as cse
        from instrument_chain.digest import canonical_digest as rci

        for payload in (
            {"a": 1, "b": "x"},
            {"b": "x", "a": 1},
            {"u": 0.001370158, "n": None, "t": True},
            {"nested": {"z": [1, 2, {"k": "v"}]}},
            {"unicode": "µm ± 0.5"},
            {"neg_zero": -0.0},
            {"big": 1e300, "small": 1e-300},
        ):
            with self.subTest(payload=payload):
                self.assertEqual(cse(payload), rci(payload))

    def test_a_cite_emitted_by_rci_is_admitted_by_cse(self) -> None:
        """The seam, over the real objects rather than a fixture of their shape."""
        from instrument_chain.budget_cite import attach_cite
        from instrument_chain.uncertainty_budget import Budget, Dist, TypeA, TypeB

        budget = Budget(
            measurand="Width",
            unit="m",
            components=[
                TypeA(source="repeat", s=0.0042, n=10, statistic="mean", unit="m"),
                TypeB(
                    source="resolution",
                    dist=Dist.RECTANGULAR,
                    half_width=0.0005,
                    unit="m",
                ),
            ],
        )
        emitted = attach_cite({"schema": "rci-measurement-v1", "indicated": 1.002}, budget)
        # Only text crosses.
        received = json.loads(json.dumps(emitted))

        session = GatSession.load_ifc(
            str(Path(gat.demo.__file__).resolve().parent / "model.ifc")
        )
        var = session.var("Opening-1", "Width")
        entity = session.world.module.entities[session.entity_by_name("Opening-1")]

        transform, record = observe_from_budget(
            var,
            received["indicated"],
            budget.to_record(),
            bind=_bind(),
            slot_unit=entity.slots["Width"].unit.value,
            cite=received["budget_cite"],
        )
        self.assertAlmostEqual(
            record["observed"]["noise_sigma"], budget.u_c(), places=15
        )
        session.run(transform)  # conditions without raising


if __name__ == "__main__":
    unittest.main()
