"""Non-mutating design-change and RFI impact reports."""

from __future__ import annotations

import os
import unittest

import gat.demo
from gat.engine.executor import preview
from gat.engine.transform import ObserveQuantity, SetParameter
from gat.session import GatSession
from gat.workflows import ChangeDisposition, preview_change


MODEL = os.path.join(os.path.dirname(gat.demo.__file__), "model.ifc")


class ChangeImpactTests(unittest.TestCase):
    def setUp(self) -> None:
        self.session = GatSession.load_ifc(MODEL)
        self.before = self.session.world.digest()

    def test_admissible_height_change_reports_every_propagated_impact(self) -> None:
        change = SetParameter(
            self.session.var("Level 1", "ClearHeight"), 3.4, 0.01
        )
        report = preview_change(self.session.world, change)

        self.assertEqual(report.disposition, ChangeDisposition.ADMISSIBLE)
        self.assertTrue(report.admissible)
        self.assertEqual(self.session.world.digest(), self.before)
        self.assertNotEqual(report.candidate_world_digest, self.before)
        self.assertEqual(len(report.affected), 34)
        self.assertIn("Level 1", report.impacted_entities)
        self.assertIn("Office-A", report.impacted_entities)
        self.assertTrue(any(item.target for item in report.impacts))
        self.assertTrue(any(item.affected for item in report.impacts))

    def test_infeasible_opening_change_exposes_failed_candidate_without_commit(self) -> None:
        change = SetParameter(
            self.session.var("Opening-1", "Height"), 3.6, 0.005
        )
        report = preview_change(self.session.world, change)

        self.assertEqual(report.disposition, ChangeDisposition.BLOCKED)
        self.assertFalse(report.admissible)
        self.assertTrue(report.failures)
        self.assertEqual(self.session.world.digest(), self.before)
        self.assertNotEqual(report.candidate_world_digest, self.before)
        self.assertTrue(
            any(item.invariant_id == "CONS-02" for item in report.failures)
        )

    def test_executor_preview_uses_the_same_verified_candidate_pipeline(self) -> None:
        change = SetParameter(
            self.session.var("Level 1", "ClearHeight"), 3.4, 0.01
        )
        raw = preview(self.session.world, change)
        report = preview_change(self.session.world, change)
        self.assertTrue(raw.admissible)
        self.assertEqual(raw.candidate.digest(), report.candidate_world_digest)
        self.assertEqual(raw.targets, report.targets)
        self.assertEqual(raw.affected, report.affected)

    def test_change_scope_and_rendering_are_deterministic(self) -> None:
        change = SetParameter(
            self.session.var("Level 1", "ClearHeight"), 3.4, 0.01
        )
        first = preview_change(self.session.world, change)
        second = preview_change(self.session.world, change)
        self.assertEqual(first.scope_digest, second.scope_digest)
        self.assertEqual(first.to_dict(), second.to_dict())


class ObservationAffectedSetTests(unittest.TestCase):
    """An observation's impact preview must not report that it touched nothing.

    ``preview`` derived the affected set from the transformation's *declared*
    target. For a parameter edit that is right: the declared target is what
    moves. A conditioning update is not like that -- it moves every raw
    variable correlated with the measured one, and therefore their derived
    descendants too.

    MEASURED on the shipped model before the fix: observing ``GrossVolume``
    reported ``affected: []`` while 34 of the 39 derived quantities moved,
    ``TotalWallCost`` among them. A change-impact preview whose entire job is
    to say what a change touches said it touched nothing.

    ``ObserveQuantity.raw_targets`` already resolved this and documented
    itself as doing so; the executor never called it. No test exercised
    ``affected`` with any observation, which is why it stood.
    """

    MODEL = os.path.join(os.path.dirname(gat.demo.__file__), "model.ifc")

    def _session(self) -> GatSession:
        return GatSession.load_ifc(self.MODEL)

    def _observe_gross_volume(self, world):
        var = next(
            v for v in world.binding.full_index.vars if v.quantity == "GrossVolume"
        )
        return ObserveQuantity.single(var, float(world.full.mean(var)) * 1.02, 0.02)

    def test_an_observation_reports_the_quantities_it_moves(self) -> None:
        session = self._session()
        world = session.world
        transformation = self._observe_gross_volume(world)

        affected = preview_change(world, transformation).to_dict()["affected"]
        result = session.run(transformation)
        moved = [v for v, _ in result.deltas if not world.binding.is_raw(v)]

        self.assertTrue(moved, "the observation must actually move something")
        self.assertGreaterEqual(
            len(affected),
            len(moved),
            "the affected set must cover what moved",
        )

    def test_the_affected_set_is_conservative_not_exact(self) -> None:
        """``raw_targets`` says "conservatively all raw vars with nonzero
        gain". Over-reporting is the safe direction for an impact preview;
        under-reporting is what this test exists to stop."""
        session = self._session()
        world = session.world
        affected = preview_change(
            world, self._observe_gross_volume(world)
        ).to_dict()["affected"]
        self.assertLessEqual(len(affected), len(world.binding.deps.derived_vars))

    def test_a_parameter_edit_still_reports_exactly_its_descendants(self) -> None:
        """The fix must not widen the set for the case that was already right."""
        session = self._session()
        world = session.world
        edit = SetParameter(session.var("Wall-Party", "Width"), 0.21, 0.002)

        affected = preview_change(world, edit).to_dict()["affected"]
        moved = [
            v for v, _ in session.run(edit).deltas if not world.binding.is_raw(v)
        ]
        self.assertEqual(len(affected), len(moved))


if __name__ == "__main__":
    unittest.main()
