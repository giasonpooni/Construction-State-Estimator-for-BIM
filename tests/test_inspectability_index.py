"""Inspectability fold is read-only and stays REQUEST_EVIDENCE without a bind."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from gat.demo.experiment_harness import (
    _DEMO_COMMITS,
    _DEMO_RECEIPT,
    _DEMO_SPACE,
    run_inspectability,
)
from gat.harness.inspectability import fold_inspectability, tickets_from_index


class InspectabilityIndexTests(unittest.TestCase):
    def test_demo_fold_requests_evidence_without_a_bind(self) -> None:
        self.assertTrue(_DEMO_SPACE.is_file())
        self.assertTrue(_DEMO_RECEIPT.is_file())
        with tempfile.TemporaryDirectory() as raw:
            output = Path(raw) / "index.json"
            document = run_inspectability(
                space_path=_DEMO_SPACE,
                receipt_paths=[_DEMO_RECEIPT],
                commitment_paths=list(_DEMO_COMMITS),
                bind_paths=[],
                output_path=output,
                quiet=True,
            )
        self.assertEqual(document["format"], "cse-inspectability-index-v1")
        self.assertEqual(document["inspectability"], "REQUEST_EVIDENCE")
        codes = {row["code"] for row in document["open_requests"]}
        self.assertIn("bind.point_to_guid", codes)
        self.assertIn("evidence.as_built", codes)
        self.assertNotIn("identity.space", codes)
        self.assertEqual(document["bound_cases"][0]["case_id"], "opening-17")
        self.assertEqual(len(document["cited"]), 2)
        self.assertIn("not an occupancy permit", document["non_claims"])

    def test_missing_space_identity_is_a_named_hole(self) -> None:
        index = fold_inspectability(
            receipts=[({"case_id": "opening-17", "disposition": "ACCEPT"}, "r.json")],
        )
        self.assertEqual(index.inspectability, "REQUEST_EVIDENCE")
        codes = {row["code"] for row in index.document["open_requests"]}
        self.assertIn("identity.space", codes)
        self.assertIn("bind.point_to_guid", codes)

    def test_accept_case_without_bind_does_not_become_presentable(self) -> None:
        space = {
            "space_ref": {
                "ifc_class": "IfcSpace",
                "global_id": "3AbcOfficeA00000000000000",
                "name": "L3-Office-A",
            }
        }
        index = fold_inspectability(
            space=space,
            receipts=[
                (
                    {
                        "case_id": "opening-17",
                        "workflow": "OPENING_VERIFICATION",
                        "disposition": "ACCEPT",
                    },
                    "r.json",
                )
            ],
        )
        self.assertEqual(index.inspectability, "REQUEST_EVIDENCE")
        codes = {row["code"] for row in index.document["open_requests"]}
        self.assertIn("bind.point_to_guid", codes)

    def test_violated_case_rejects_even_with_a_bind(self) -> None:
        space = {
            "space_ref": {
                "ifc_class": "IfcSpace",
                "global_id": "3AbcOfficeA00000000000000",
            }
        }
        bind = {
            "schema": "cse-point-bind-v1",
            "point_id": "P-204",
            "global_id": "2OpeningO2040000000000000",
            "ifc_class": "IfcOpeningElement",
        }
        index = fold_inspectability(
            space=space,
            receipts=[
                (
                    {
                        "case_id": "opening-17",
                        "disposition": "VIOLATED",
                        "evidence_digest": "a" * 16,
                    },
                    "r.json",
                )
            ],
            binds=[(bind, "bind.json")],
        )
        self.assertEqual(index.inspectability, "REJECT")
        codes = {row["code"] for row in index.document["open_requests"]}
        self.assertNotIn("bind.point_to_guid", codes)

    def test_bind_and_as_built_can_become_presentable(self) -> None:
        space = {
            "space_ref": {
                "ifc_class": "IfcSpace",
                "global_id": "3AbcOfficeA00000000000000",
            }
        }
        bind = {
            "schema": "cse-point-bind-v1",
            "point_id": "P-204",
            "global_id": "2OpeningO2040000000000000",
        }
        index = fold_inspectability(
            space=space,
            receipts=[
                (
                    {
                        "case_id": "opening-17",
                        "disposition": "ACCEPT",
                        "evidence_digest": "a" * 16,
                    },
                    "r.json",
                )
            ],
            binds=[(bind, "bind.json")],
        )
        self.assertEqual(index.inspectability, "ACCEPT")
        self.assertEqual(index.document["open_requests"], [])
        self.assertEqual(tickets_from_index(index), ())

    def test_open_holes_become_crew_tickets_with_instrument_class(self) -> None:
        index = fold_inspectability(
            receipts=[({"case_id": "opening-17", "disposition": "ACCEPT"}, "r.json")],
        )
        tickets = tickets_from_index(index)
        codes = {ticket.code for ticket in tickets}
        self.assertIn("identity.space", codes)
        self.assertIn("bind.point_to_guid", codes)
        instruments = {ticket.instrument_class for ticket in tickets}
        self.assertIn("ifc-space-entity", instruments)
        self.assertIn("total-station-or-layout", instruments)
        self.assertFalse(any(ticket.presentable for ticket in tickets))

    def test_survey_frame_request_is_a_named_hole_not_a_revit_export(self) -> None:
        space = {
            "space_ref": {
                "ifc_class": "IfcSpace",
                "global_id": "3AbcOfficeA00000000000000",
            }
        }
        bind = {
            "schema": "cse-point-bind-v1",
            "point_id": "P-204",
            "global_id": "2OpeningO2040000000000000",
        }
        index = fold_inspectability(
            space=space,
            receipts=[
                (
                    {
                        "case_id": "opening-17",
                        "disposition": "ACCEPT",
                        "evidence_digest": "a" * 16,
                    },
                    "r.json",
                )
            ],
            binds=[(bind, "bind.json")],
            extra_requests=[
                {
                    "code": "frame.station_setup",
                    "asks_for": "occupied + backsight id for setup S-12",
                }
            ],
        )
        self.assertEqual(index.inspectability, "REQUEST_EVIDENCE")
        tickets = tickets_from_index(index)
        self.assertEqual(tickets[0].instrument_class, "total-station")
        self.assertEqual(tickets[0].code, "frame.station_setup")


if __name__ == "__main__":
    unittest.main()
