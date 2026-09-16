"""Tests for gat.geometry.clash + gat.geometry.stateio on the demo scene.

The demo model (gat/demo/model.ifc) lowers to a scene whose solid elements
are the five walls and the door; the two office spaces are non-solid.
Element boxes (verified against the IFC placements/quantities):

    Wall-South  origin (0, -0.3, 0)  angle 0     extents (9.2, 0.3, 3.0)
    Wall-North  origin (0,  4.0, 0)  angle 0     extents (9.2, 0.3, 3.0)
    Wall-West   origin (0, -0.3, 0)  angle pi/2  extents (4.6, 0.3, 3.0)
    Wall-East   origin (9.5,-0.3, 0) angle pi/2  extents (4.6, 0.3, 3.0)
    Wall-Party  origin (5.2, 0,  0)  angle pi/2  extents (4.0, 0.2, 3.0)

(the wall height 3.0 is the storey ClearHeight, shared by every wall).
All geometric assertions below are hand-derived from these numbers.
"""

from __future__ import annotations

import os
import unittest

import gat.demo
from gat.engine.transform import SetParameter
from gat.errors import GatError
from gat.geometry.clash import detect, score_proposed_box
from gat.geometry.gaussianize import OrientedBox
from gat.geometry.stateio import derive_scene, relative_covariance
from gat.session import GatSession

MODEL = os.path.join(os.path.dirname(gat.demo.__file__), "model.ifc")


def _pair_names(item) -> frozenset:
    return frozenset((item.element_a, item.element_b))


class DemoClashTest(unittest.TestCase):
    """Shared read-only session/scene; tests that transform state build
    their own session."""

    @classmethod
    def setUpClass(cls):
        cls.session = GatSession.load_ifc(MODEL)
        cls.world = cls.session.world
        cls.scene = derive_scene(cls.world)
        cls.report = detect(cls.scene)

    # -- corner joints -----------------------------------------------------

    def test_corner_joined_walls_are_contact_not_clash(self):
        # Every scored pair in the demo is a construction joint: e.g.
        # Wall-South (x in [0, 9.2], y in [-0.3, 0]) meets Wall-West
        # (x in [-0.3, 0], y in [-0.3, 4.3]) exactly at the x = 0 plane, so
        # the separating-axis clearance is 0 (up to roundoff), never a real
        # interpenetration; with the 0.01 m penetration tolerance the clash
        # probability must stay low.
        self.assertGreater(len(self.report.items), 0)
        for item in self.report.items:
            with self.subTest(pair=(item.element_a, item.element_b)):
                self.assertGreaterEqual(item.clearance, -1e-9)
                self.assertLess(item.p_clash, 0.05)
        # The south/west corner joint itself must be among the scored pairs.
        pairs = {_pair_names(it) for it in self.report.items}
        self.assertIn(frozenset({"Wall-South", "Wall-West"}), pairs)

    # -- proposed duct -----------------------------------------------------

    def test_crossing_duct_clashes_with_party_wall(self):
        # Duct box: x in [4.0, 7.0], y in [1.8, 2.2], z in [2.6, 3.0];
        # center (5.5, 2.0, 2.8).  Wall-Party occupies x in [5.0, 5.2],
        # y in [0, 4], z in [0, 3]; center (5.1, 2.0, 1.5).
        # SAT hand computation, delta = duct_center - wall_center
        # = (0.4, 0.0, 1.3), candidate axes are z, world y (wall local x)
        # and world x (wall local y == duct local x, deduplicated):
        #   x: |0.4| - (0.1 + 1.5) = -1.2
        #   y: |0.0| - (2.0 + 0.2) = -2.2
        #   z: |1.3| - (1.5 + 0.2) = -0.4   <- maximum
        # so the minimum-translation clearance is exactly -0.4 m (the duct
        # top is flush with the wall top; pushing the duct up 0.4 m frees
        # it along z).
        duct = OrientedBox(origin=(4.0, 1.8, 2.6), angle=0.0, extents=(3.0, 0.4, 0.4))
        report = score_proposed_box(self.scene, duct, position_sigma=0.02)
        self.assertEqual(len(report.items), 1)
        item = report.items[0]
        self.assertEqual(item.element_a, "Wall-Party")
        self.assertEqual(item.element_b, "<proposed>")
        self.assertAlmostEqual(item.clearance, -0.4, delta=1e-12)
        self.assertGreater(item.p_clash, 0.999)
        self.assertGreater(item.overlap_mass, 0.0)

    def test_rerouted_duct_above_storey_is_clear(self):
        # Rerouted at z in [3.55, 3.95]: every wall tops out at z = 3.0, so
        # the vertical gap is 0.55 m > the 0.5 m broad-phase clearance
        # window -> zero scored items.
        duct_hi = OrientedBox(
            origin=(4.0, 1.8, 3.55), angle=0.0, extents=(3.0, 0.4, 0.4)
        )
        report = score_proposed_box(self.scene, duct_hi, position_sigma=0.02)
        self.assertEqual(len(report.items), 0)

    # -- correlated cancellation ------------------------------------------

    def test_shared_clear_height_cancels_in_relative_z(self):
        # Both walls' Height derives from the single storey ClearHeight, so
        # each center's z jitters with Var = (dz_center/dH)^2 Var(H)
        # = 0.25 Var(H) > 0, but the RELATIVE z offset uses (J_a - J_b)
        # where the shared row subtracts to zero: exact cancellation.
        south = self.scene.element_by_name("Wall-South")
        party = self.scene.element_by_name("Wall-Party")
        rel = relative_covariance(self.scene, south, party)
        self.assertLess(abs(rel[2, 2]), 1e-12)
        sigma_raw = self.world.belief.sigma
        for element in (south, party):
            J = self.scene.center_jacobian_wrt_raw(element)
            own = J @ sigma_raw @ J.T
            with self.subTest(element=element.name):
                self.assertGreater(own[2, 2], 1e-6)

    # -- exemptions --------------------------------------------------------

    def test_exempt_pairs_absent_from_detect(self):
        door = self.scene.element_by_name("Door-1")
        party = self.scene.element_by_name("Wall-Party")
        office_a = self.scene.element_by_name("Office-A")
        south = self.scene.element_by_name("Wall-South")

        # The relationship graph registers the door x host wall and each
        # space x bounding wall as expected contacts.
        self.assertIn(
            (min(door.row, party.row), max(door.row, party.row)),
            self.scene.exempt_pairs,
        )
        self.assertIn(
            (min(office_a.row, south.row), max(office_a.row, south.row)),
            self.scene.exempt_pairs,
        )

        # No exempt pair may be scored, and no space/door-host pair appears.
        row_of = {e.name: e.row for e in self.scene.elements}
        for item in self.report.items:
            names = _pair_names(item)
            self.assertNotEqual(names, frozenset({"Door-1", "Wall-Party"}))
            self.assertFalse(names & {"Office-A", "Office-B"})
            rows = (row_of[item.element_a], row_of[item.element_b])
            self.assertNotIn((min(rows), max(rows)), self.scene.exempt_pairs)

    # -- staleness ---------------------------------------------------------

    def test_stale_scene_raises_gat_error(self):
        session = GatSession.load_ifc(MODEL)
        scene = derive_scene(session.world)
        # Fresh: querying against the world it was derived from is fine.
        scene.check_fresh(session.world)
        detect(scene)  # must not raise while fresh

        session.run(
            SetParameter(session.var("Wall-South", "Length"), 9.3, design_sigma=0.005)
        )
        # The world moved on; the old scene's version no longer matches the
        # current world digest -> querying it is a hard error.
        self.assertNotEqual(scene.version, session.world.digest())
        with self.assertRaises(GatError):
            scene.check_fresh(session.world)

    # -- determinism -------------------------------------------------------

    def test_detect_is_deterministic(self):
        scene_a = derive_scene(self.world)
        scene_b = derive_scene(self.world)
        report_a = detect(scene_a)
        report_b = detect(scene_b)
        self.assertEqual(report_a.render(), report_b.render())
        # And equal to the class-level report computed at setUpClass time.
        self.assertEqual(report_a.render(), self.report.render())


class BroadPhaseWindowIsNotAFilterTests(unittest.TestCase):
    """A negative ``max_clearance`` published "nothing was checked" as
    "nothing is wrong".

    ``detect`` passed ``margin=0.5 * max_clearance`` straight into
    ``SceneElement.aabb``, which adds it to the max corner and subtracts it
    from the min. At margin -0.5 Wall-Party's own bounds invert --
    lo [5.65 2.05 0.5] > hi [4.7 1.95 1.5] -- so ``(lo_a > hi_b).any()``
    rejects every pair unconditionally. Measured on the demo scene before
    the fix: max_clearance 0.5 and 0.0 both scored 6 pairs out of 15
    considered with worst p_clash 0.03165889341501993, while -0.01 and -1.0
    scored 0 pairs and reported worst p_clash 0.0. It is a cliff at any
    negative value, not a graduated filter. ``gat check --max-clearance -1``
    exited 0 on that empty report, while the same flag on the same
    invocation plus ``--proposed`` already exited 2, because
    ``score_proposed_box`` carried the guard ``detect`` did not.
    """

    @classmethod
    def setUpClass(cls):
        cls.world = GatSession.load_ifc(MODEL).world
        cls.scene = derive_scene(cls.world)

    def test_the_smallest_negative_window_is_refused(self):
        # -0.01 is where the cliff already is: 6 scored pairs -> 0.
        for value in (-0.01, -0.5, -1.0, -1e6):
            with self.subTest(max_clearance=value):
                with self.assertRaises(ValueError) as caught:
                    detect(self.scene, max_clearance=value)
                self.assertIn("max_clearance must be non-negative", str(caught.exception))

    def test_a_non_finite_window_is_refused(self):
        # nan compares False against every bound, so it silently disabled
        # pruning; None is the spelling that asks for that.
        for value in (float("nan"), float("inf"), float("-inf")):
            with self.subTest(max_clearance=value):
                with self.assertRaises(ValueError):
                    detect(self.scene, max_clearance=value)

    def test_zero_is_still_a_valid_window(self):
        # The fix must not move the valid boundary: touching boxes still score.
        report = detect(self.scene, max_clearance=0.0)
        self.assertEqual(len(report.items), 6)
        self.assertEqual(report.n_pairs_broadphase, 6)
        self.assertEqual(report.n_pairs_considered, 15)

    def test_none_disables_pruning_as_it_does_for_a_proposal(self):
        # score_proposed_box has always spelled "no pruning" None; detect
        # divided None by two and raised TypeError.
        report = detect(self.scene, max_clearance=None)
        self.assertEqual(report.n_pairs_considered, 15)
        self.assertGreaterEqual(report.n_pairs_broadphase, 6)
        self.assertGreaterEqual(len(report.items), len(detect(self.scene).items))

    def test_the_two_entry_points_refuse_alike(self):
        duct = OrientedBox(origin=(4.0, 1.8, 2.6), angle=0.0, extents=(3.0, 0.4, 0.4))
        with self.assertRaises(ValueError):
            score_proposed_box(self.scene, duct, max_clearance=-0.01)
        with self.assertRaises(ValueError):
            detect(self.scene, max_clearance=-0.01)


class ProposedBoxMustBeRepresentableTests(unittest.TestCase):
    """A mirrored proposed box named an occupied region and scored it clear.

    ``score_proposed_box`` never checked its box, so extents could be
    negative or zero. origin (7.0, 2.2, 3.0) extents (-3.0, -0.4, -0.4) has
    the same centre [5.5, 2.0, 2.8] and the same AABB
    [4, 1.8, 2.6]-[7, 2.2, 3.0] as the crossing duct above, i.e. it passes
    through Wall-Party just as that one does. Measured before the fix: the
    duct scored clearance -0.4000, P(clash) 1.0000, overlap 0.01857 m3 and
    ``gat check`` exited 1; the mirrored spelling scored clearance +1.8000,
    P(clash) 0.0000, overlap mass -0.02955 m3 and exited 0 -- the clean
    code for a duct through a party wall. Underneath, ``support_radius``
    returns -1.5 for it and ``gaussianize_box`` emits a weight sum of
    -0.48: a negative radius and a negative mass, geometry the runtime
    cannot represent, emitted without complaint. ``ClearanceDecision``, the
    repo's declared type for this same question, refused it all along with
    "proposed box extents must be positive"; the CLI called past it.
    """

    @classmethod
    def setUpClass(cls):
        cls.scene = derive_scene(GatSession.load_ifc(MODEL).world)

    def test_the_mirrored_duct_is_refused_not_scored_clear(self):
        mirrored = OrientedBox(
            origin=(7.0, 2.2, 3.0), angle=0.0, extents=(-3.0, -0.4, -0.4)
        )
        with self.assertRaises(ValueError) as caught:
            score_proposed_box(self.scene, mirrored, position_sigma=0.02)
        self.assertEqual(str(caught.exception), "proposed box extents must be positive")

    def test_a_flat_box_is_refused(self):
        for extents in ((0.0, 0.4, 0.4), (3.0, 0.0, 0.4), (3.0, 0.4, 0.0)):
            with self.subTest(extents=extents):
                with self.assertRaises(ValueError):
                    score_proposed_box(
                        self.scene,
                        OrientedBox(origin=(4.0, 1.8, 2.6), angle=0.0, extents=extents),
                    )

    def test_non_finite_geometry_is_refused(self):
        nan = float("nan")
        boxes = (
            OrientedBox(origin=(nan, 1.8, 2.6), angle=0.0, extents=(3.0, 0.4, 0.4)),
            OrientedBox(origin=(4.0, 1.8, 2.6), angle=nan, extents=(3.0, 0.4, 0.4)),
            OrientedBox(origin=(4.0, 1.8, 2.6), angle=0.0, extents=(float("inf"), 0.4, 0.4)),
        )
        for box in boxes:
            with self.subTest(box=box):
                with self.assertRaises(ValueError):
                    score_proposed_box(self.scene, box)

    def test_a_negative_position_sigma_is_refused(self):
        # It was squared into extra_var, so -0.02 scored as +0.02: an
        # uncertainty budget silently accepted from a nonsense number.
        duct = OrientedBox(origin=(4.0, 1.8, 2.6), angle=0.0, extents=(3.0, 0.4, 0.4))
        with self.assertRaises(ValueError):
            score_proposed_box(self.scene, duct, position_sigma=-0.02)
        with self.assertRaises(ValueError):
            score_proposed_box(self.scene, duct, position_sigma=float("nan"))

    def test_the_honest_spelling_of_the_same_region_still_scores(self):
        # The guard must refuse only the unrepresentable spelling.
        duct = OrientedBox(origin=(4.0, 1.8, 2.6), angle=0.0, extents=(3.0, 0.4, 0.4))
        report = score_proposed_box(self.scene, duct, position_sigma=0.02)
        self.assertEqual(len(report.items), 1)
        self.assertAlmostEqual(report.items[0].clearance, -0.4, delta=1e-12)
        self.assertGreater(report.items[0].p_clash, 0.999)
        self.assertGreater(report.items[0].overlap_mass, 0.0)


if __name__ == "__main__":
    unittest.main()
