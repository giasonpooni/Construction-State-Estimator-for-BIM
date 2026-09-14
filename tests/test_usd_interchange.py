"""State-space interchange through OpenUSD: D(E(S)) ~= S, and continuation."""

from __future__ import annotations

import filecmp
import math
import os
import tempfile
import unittest

from gat.adapters.usd_io import FORMAT, load_usd, state_equivalence
from gat.engine.transform import ObserveQuantity, SetParameter
from gat.errors import SnapshotError, SpfParseError
from gat.session import GatSession

MODEL = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "gat", "demo", "model.ifc",
)


class UsdInterchangeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        cls.session = GatSession.load_ifc(MODEL)
        vol_a = cls.session.var("Office-A", "Volume")
        cls.session.run(ObserveQuantity.single(vol_a, 59.4, 0.05))
        cls.usd_path = os.path.join(cls.tmp.name, "state.usda")
        cls.session.export_usd(cls.usd_path)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def test_invariant_suite_passes(self) -> None:
        world, _ = load_usd(self.usd_path)
        report = state_equivalence(self.session.world, world)
        for check in report.checks:
            self.assertTrue(check.passed, f"I_{check.name} failed: {check.detail}")
        self.assertTrue(report.equivalent)

    def test_belief_restored_bitwise(self) -> None:
        world, _ = load_usd(self.usd_path)
        self.assertEqual(
            world.belief.mu.tobytes(), self.session.world.belief.mu.tobytes()
        )
        self.assertEqual(
            world.belief.sigma.tobytes(), self.session.world.belief.sigma.tobytes()
        )

    def test_reconstructed_world_verifies(self) -> None:
        reconstructed = GatSession.load_usd(self.usd_path)
        self.assertTrue(reconstructed.verify().passed)

    def test_provenance_events_carried(self) -> None:
        _, trace = load_usd(self.usd_path)
        self.assertGreaterEqual(len(trace), 2)  # compile + observe
        self.assertEqual(trace[0]["stage"], "compile")

    def test_continuation_is_bitwise_identical(self) -> None:
        # Continuous runtime: T2 on the original session's world.
        continuous = GatSession.load_ifc(MODEL)
        vol_a = continuous.var("Office-A", "Volume")
        continuous.run(ObserveQuantity.single(vol_a, 59.4, 0.05))
        ch = continuous.var("Level 1", "ClearHeight")
        continuous.run(SetParameter(ch, 3.4, design_sigma=0.01))

        # Transferred runtime: reconstruct, then the same T2.
        transferred = GatSession.load_usd(self.usd_path)
        ch_b = transferred.var("Level 1", "ClearHeight")
        transferred.run(SetParameter(ch_b, 3.4, design_sigma=0.01))

        self.assertEqual(
            transferred.world.full.mu.tobytes(), continuous.world.full.mu.tobytes()
        )
        self.assertEqual(
            transferred.world.full.sigma.tobytes(),
            continuous.world.full.sigma.tobytes(),
        )
        self.assertTrue(
            state_equivalence(continuous.world, transferred.world).equivalent
        )

    def test_export_is_deterministic(self) -> None:
        other = os.path.join(self.tmp.name, "state2.usda")
        # A fresh session replays the same program; its trace digests match,
        # so the stage bytes must too.
        session = GatSession.load_ifc(MODEL)
        vol_a = session.var("Office-A", "Volume")
        session.run(ObserveQuantity.single(vol_a, 59.4, 0.05))
        session.export_usd(other)
        self.assertTrue(filecmp.cmp(self.usd_path, other, shallow=False))

    def test_unsupported_format_rejected(self) -> None:
        with self.assertRaises(SpfParseError):
            load_usd(self._edited("bad.usda", FORMAT, "gat-usd v999", count=-1))

    def test_a_legacy_carrier_is_named_rather_than_puzzled_over(self) -> None:
        """A v0 stage predates both the check and the world identity."""
        with self.assertRaises(SpfParseError) as caught:
            load_usd(self._edited("legacy.usda", FORMAT, "gat-usd v0", count=-1))
        self.assertIn("re-export", str(caught.exception))

    # -- the carrier answers for its own contents --------------------------

    def _edited(self, name: str, old: str, new: str, count: int = -1) -> str:
        with open(self.usd_path, encoding="utf-8") as fh:
            text = fh.read()
        self.assertIn(old, text, "the forgery must actually change the stage")
        edited = text.replace(old, new, count)
        self.assertNotEqual(text, edited, "the forgery must change the stage")
        path = os.path.join(self.tmp.name, name)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(edited)
        return path

    def test_an_edited_mean_is_refused(self) -> None:
        """The stage is a text file. Editing a storey height used to pass."""
        mu = float(self.session.world.belief.mu[0])
        with self.assertRaises(SnapshotError) as caught:
            load_usd(self._edited("mean.usda", f'"mu": [{mu!r},', '"mu": [8.0,'))
        self.assertIn("altered after export", str(caught.exception))

    def test_an_edited_ir_is_refused_as_a_different_ir(self) -> None:
        with self.assertRaises(SnapshotError) as caught:
            load_usd(self._edited("name.usda", '"name": "Level 1"', '"name": "G"'))
        self.assertIn("not the IR this carrier was written from", str(caught.exception))

    def test_a_sub_tolerance_edit_is_still_refused(self) -> None:
        """One ULP on a covariance term.

        Configuration identity quantizes to 1e-6, so it cannot see this and
        says so; the bytewise world digest is what catches it. That is the
        same branch a runtime with a different numeric configuration lands
        in, which is why the refusal states both readings.
        """
        off = self._off_diagonal()
        nudged = math.nextafter(off, math.inf)
        with self.assertRaises(SnapshotError) as caught:
            load_usd(self._edited("cov.usda", repr(off), repr(nudged)))
        message = str(caught.exception)
        self.assertIn("does not reproduce bytewise", message)
        self.assertIn("configuration still matches", message)

    def _off_diagonal(self) -> float:
        """Any non-zero covariance term. Sigma is symmetric, so its text
        appears twice and both copies move together."""
        with open(self.usd_path, encoding="utf-8") as fh:
            text = fh.read()
        sigma = self.session.world.belief.sigma
        for i in range(sigma.shape[0]):
            for j in range(i + 1, sigma.shape[1]):
                value = float(sigma[i, j])
                if value != 0.0 and repr(value) in text:
                    return value
        self.skipTest("this belief has no uniquely addressable covariance term")

    def test_a_carrier_without_a_commitment_cannot_be_loaded(self) -> None:
        for key in ("module_digest", "world_digest", "configuration_digest"):
            with self.subTest(commitment=key):
                with self.assertRaises(SnapshotError) as caught:
                    load_usd(
                        self._edited(f"no_{key}.usda", f'"{key}":', f'"x_{key}":')
                    )
                self.assertIn(f"records no {key}", str(caught.exception))

    # -- the carrier answers for its provenance too ------------------------

    def test_a_rewritten_source_is_refused(self) -> None:
        """``meta["source"]`` is deliberately outside the *world* digest -- a
        world is named by its model's bytes, not the caller's path -- so
        without a carrier-level commitment a stage could be edited to name an
        approved model while carrying a different one, and verify clean."""
        with self.assertRaises(SnapshotError) as caught:
            load_usd(
                self._edited(
                    "source.usda",
                    '"source": "' + MODEL.replace("\\", "/"),
                    '"source": "/approved/CERTIFIED-final.ifc',
                )
            )
        self.assertIn("provenance around it", str(caught.exception))

    def test_an_invented_approval_event_is_refused(self) -> None:
        """The trace is provenance, not state, so every number stays intact."""
        forged = (
            '{"detail": "approved for construction", "digest": "'
            + "0" * 64
            + '", "name": "SIGNED OFF BY ENGINEER", "seq": 99, '
            '"stage": "approval", "verify": "pass"}, '
        )
        with self.assertRaises(SnapshotError) as caught:
            load_usd(self._edited("approval.usda", '"trace": [', '"trace": [' + forged))
        self.assertIn("provenance around it", str(caught.exception))

    def test_the_provenance_refusal_is_not_a_state_refusal(self) -> None:
        """A reader must be able to tell 'someone edited a quantity' from
        'the numbers are intact but the story around them was rewritten'."""
        with self.assertRaises(SnapshotError) as caught:
            load_usd(
                self._edited(
                    "source2.usda",
                    '"source": "' + MODEL.replace("\\", "/"),
                    '"source": "/elsewhere.ifc',
                )
            )
        message = str(caught.exception)
        self.assertIn("the state is intact", message)
        self.assertNotIn("altered after export", message)

    def test_an_honest_carrier_still_loads(self) -> None:
        world, _ = load_usd(self.usd_path)
        self.assertEqual(world.digest(), self.session.world.digest())


if __name__ == "__main__":
    unittest.main()
