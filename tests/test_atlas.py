"""Atlas walks declared charts. Missing sigma cannot justify a walk."""

from __future__ import annotations

import unittest

from gat.harness.atlas import (
    BEAM_B1,
    OPENING_WIDTH_M,
    OPENING_WIDTH_MM,
    TANK_LEVEL_M,
    AtlasError,
    Edge,
    identity_gap,
    office_a_atlas,
)


class AtlasTests(unittest.TestCase):
    def test_metre_to_millimetre_is_explicit(self) -> None:
        atlas = office_a_atlas()
        walked = atlas.walk(OPENING_WIDTH_M, OPENING_WIDTH_MM, 1.002)
        self.assertEqual(walked["kind"], "representation")
        self.assertEqual(walked["scale"], 1000.0)
        self.assertEqual(walked["offset"], 0.0)
        self.assertAlmostEqual(walked["value"], 1002.0)

    def test_observation_without_sigma_is_refused(self) -> None:
        atlas = office_a_atlas()
        with self.assertRaisesRegex(AtlasError, "sigma"):
            atlas.add_edge(
                Edge(
                    OPENING_WIDTH_M,
                    OPENING_WIDTH_M,
                    "observation",
                    1.0,
                    0.0,
                    observation_id="office-a-p204:1",
                    sigma=None,
                )
            )

    def test_tank_does_not_walk_onto_opening(self) -> None:
        atlas = office_a_atlas()
        with self.assertRaisesRegex(AtlasError, "no declared edge"):
            atlas.walk(TANK_LEVEL_M, OPENING_WIDTH_M, 2.41)

    def test_beam_slot_is_another_world(self) -> None:
        atlas = office_a_atlas()
        self.assertEqual(atlas.slots[BEAM_B1].world, "beam-b1-ifc")
        self.assertEqual(atlas.slots[OPENING_WIDTH_M].world, "office-a-ifc")


class IdentityGapTests(unittest.TestCase):
    def test_gap_does_not_force_a_common_world(self) -> None:
        gap = identity_gap(
            office_live_digest="aa" * 32,
            beam_live_digest="bb" * 32,
            beam_prior_digest="cc" * 32,
            beam_revised_digest="dd" * 32,
        )
        self.assertFalse(gap["forced_common_world"])
        self.assertFalse(gap["live_worlds_equal"])
        self.assertFalse(gap["beam_pin_is_live_ifc"])
        self.assertEqual(gap["beam_entity_id"], "IfcBeam:GATBEAMELEMENT00000100")


if __name__ == "__main__":
    unittest.main()
