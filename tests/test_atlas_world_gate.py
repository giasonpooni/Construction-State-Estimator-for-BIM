"""An atlas edge may not cross a world.

identity_gap states the rule in prose -- "share Guid; cite digest; do not
equate worlds" -- and complete_v0 reports forced_common_world false. Nothing
enforced it: Slot carries a world, but add_edge never compared the endpoints,
so a coupling edge with a written reason could equate two worlds and the one
claim the system exists to refuse would pass.

An edge is transport. Carrying a value from one coordinate to another asserts
they measure the same thing, which across worlds is exactly the forbidden
claim. Cross-world relationships are cited side by side instead
(atlas_cov.cite_disposition_worlds).

stdlib unittest only.
"""

from __future__ import annotations

import json
import unittest

from gat.harness.atlas import (
    BEAM_WORLD,
    DOOR_WIDTH_M,
    OFFICE_WORLD,
    OPENING_WIDTH_M,
    OPENING_WIDTH_MM,
    TANK_LEVEL_M,
    TANK_WORLD,
    Atlas,
    AtlasError,
    Edge,
    Slot,
    office_a_atlas,
    slot_id,
)

BEAM_CAPACITY = slot_id("IfcBeam", "GATBEAMELEMENT00000100", "Capacity", "N*m")


class WorldGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.atlas = office_a_atlas()

    def test_the_shipped_atlas_spans_three_worlds(self) -> None:
        self.assertEqual(
            self.atlas.worlds(), (BEAM_WORLD, TANK_WORLD, OFFICE_WORLD)
        )

    def test_its_existing_edges_are_all_in_world(self) -> None:
        # The gate must be additive: nothing declared before it may break.
        self.assertTrue(self.atlas.edges)
        for edge in self.atlas.edges:
            self.assertEqual(
                self.atlas.slots[edge.source].world,
                self.atlas.slots[edge.target].world,
            )

    def test_a_coupling_may_not_equate_two_worlds(self) -> None:
        # The case that matters: a reason is prose, not a licence.
        with self.assertRaisesRegex(AtlasError, "cited, not transported"):
            self.atlas.add_edge(
                Edge(
                    OPENING_WIDTH_M,
                    TANK_LEVEL_M,
                    "coupling",
                    1.0,
                    0.0,
                    reason="both are lengths in metres",
                )
            )

    def test_a_representation_change_may_not_cross_a_world(self) -> None:
        with self.assertRaisesRegex(AtlasError, "cited, not transported"):
            self.atlas.add_edge(
                Edge(OPENING_WIDTH_M, BEAM_CAPACITY, "representation", 1.0, 0.0)
            )

    def test_an_observation_may_not_cross_a_world(self) -> None:
        atlas = Atlas()
        atlas.add_slot(Slot("RCI", "obs-1", "indicated", "m", TANK_WORLD))
        atlas.add_slot(
            Slot("IfcOpeningElement", "GATOPN0000000000000200", "Width", "m", OFFICE_WORLD)
        )
        with self.assertRaisesRegex(AtlasError, "cited, not transported"):
            atlas.add_edge(
                Edge(
                    slot_id("RCI", "obs-1", "indicated", "m"),
                    OPENING_WIDTH_M,
                    "observation",
                    1.0,
                    0.0,
                    observation_id="obs-1",
                    sigma=0.005,
                    sigma_unit="m",
                )
            )

    def test_an_in_world_edge_between_different_entities_is_still_allowed(self) -> None:
        # The gate is about worlds, not about entities: a coupling between two
        # products of one world is a modelling choice, which a reason licenses.
        edge = self.atlas.add_edge(
            Edge(
                OPENING_WIDTH_M,
                DOOR_WIDTH_M,
                "coupling",
                1.0,
                -0.1,
                reason="door leaf is nominally 100 mm under the rough opening",
            )
        )
        self.assertEqual(edge.kind, "coupling")
        self.assertAlmostEqual(self.atlas.walk(OPENING_WIDTH_M, DOOR_WIDTH_M, 1.0)["value"], 0.9)

    def test_transport_still_works_within_a_world(self) -> None:
        got = self.atlas.walk(OPENING_WIDTH_M, OPENING_WIDTH_MM, 1.002)
        self.assertAlmostEqual(got["value"], 1002.0)
        self.assertEqual(got["kind"], "representation")

    def test_walk_refuses_an_undeclared_hop_rather_than_composing(self) -> None:
        # Single-hop by design: no transitive inference across declared edges.
        with self.assertRaisesRegex(AtlasError, "no declared edge"):
            self.atlas.walk(OPENING_WIDTH_MM, DOOR_WIDTH_M, 1000.0)

    def test_the_document_records_the_worlds_and_the_rule(self) -> None:
        document = self.atlas.to_document()
        self.assertEqual(document["worlds"], list(self.atlas.worlds()))
        self.assertIn("cited, not transported", document["world_rule"])
        # still serializable
        json.dumps(document)


if __name__ == "__main__":
    unittest.main()
