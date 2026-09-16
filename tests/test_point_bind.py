"""Point-to-IfcGuid bind is record-integrity only."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from gat.demo import office_a_v0
from gat.harness.inspectability import fold_inspectability, tickets_from_index
from gat.harness.point_bind import (
    BIND_SCHEMA,
    assert_bind_in_world,
    bind_point,
    bind_point_file,
)
from gat.session import GatSession


MODEL = Path(__file__).resolve().parents[1] / "gat" / "demo" / "model.ifc"
BIND = Path(office_a_v0._BIND)


class PointBindTests(unittest.TestCase):
    def test_display_name_is_refused(self) -> None:
        with self.assertRaisesRegex(ValueError, "display name"):
            bind_point(
                {
                    "schema": BIND_SCHEMA,
                    "claim_scope": "record-integrity-only",
                    "point_id": "P-204",
                    "ifc_class": "IfcOpeningElement",
                    "global_id": "Opening-1",
                }
            )

    def test_fixture_matches_compiled_opening(self) -> None:
        bind = bind_point_file(BIND)
        self.assertEqual(bind.point_id, "P-204")
        self.assertEqual(bind.global_id, "GATOPN0000000000000200")
        self.assertEqual(bind.ifc_class, "IfcOpeningElement")
        session = GatSession.load_ifc(str(MODEL))
        assert_bind_in_world(bind, session.world)

    def test_bind_without_as_built_stays_a_hole(self) -> None:
        bind = bind_point_file(BIND)
        space = {
            "space_ref": {
                "ifc_class": "IfcSpace",
                "global_id": "GATSPC0000000000000300",
                "name": "Office-A",
            }
        }
        index = fold_inspectability(
            space=space,
            receipts=[
                ({"case_id": "opening-17", "disposition": "ACCEPT"}, "r.json")
            ],
            binds=[(bind.to_document(), str(BIND))],
        )
        self.assertEqual(index.inspectability, "REQUEST_EVIDENCE")
        codes = {row["code"] for row in index.document["open_requests"]}
        self.assertIn("evidence.as_built", codes)
        self.assertNotIn("bind.point_to_guid", codes)

    def test_missing_sigma_is_refused(self) -> None:
        with self.assertRaisesRegex(ValueError, "sigma"):
            bind_point(
                {
                    "schema": BIND_SCHEMA,
                    "claim_scope": "record-integrity-only",
                    "point_id": "P-204",
                    "ifc_class": "IfcOpeningElement",
                    "global_id": "GATOPN0000000000000200",
                    "frame_id": "office-a-layout-v0",
                    "epoch": "design-declared",
                }
            )

    def test_coordinates_without_guid_are_refused(self) -> None:
        with self.assertRaisesRegex(ValueError, "coordinates"):
            bind_point(
                {
                    "schema": BIND_SCHEMA,
                    "claim_scope": "record-integrity-only",
                    "xyz": [1.0, 2.0, 0.0],
                }
            )

    def test_fixture_declares_frame_epoch_and_sigma(self) -> None:
        bind = bind_point_file(BIND)
        self.assertEqual(bind.frame_id, "office-a-layout-v0")
        self.assertEqual(bind.epoch, "design-declared")
        self.assertEqual(bind.sigma, 0.005)
        self.assertEqual(bind.sigma_unit, "m")


if __name__ == "__main__":
    unittest.main()
