"""Inspectability fold is read-only and stays REQUEST_EVIDENCE without a bind."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from gat.adapters.ifcopenshell_adapter import inventory_identities_cse
from gat.demo.experiment_harness import (
    _DEMO_COMMITS,
    _DEMO_RECEIPT,
    _DEMO_SPACE,
    run_inspectability,
)
from gat.harness.inspectability import fold_inspectability, tickets_from_index

OFFICE_A = "GATSPC0000000000000300"
OPENING_1 = "GATOPN0000000000000200"
DEMO_IFC = Path(__file__).resolve().parents[1] / "gat" / "demo" / "model.ifc"
EXAMPLE_BIND = Path(__file__).resolve().parents[1] / "validation" / "cse-point-bind-v1.json"


class InspectabilityIndexTests(unittest.TestCase):
    def test_demo_fold_uses_office_a_guid_from_model(self) -> None:
        self.assertTrue(_DEMO_SPACE.is_file())
        self.assertTrue(_DEMO_RECEIPT.is_file())
        inventory = inventory_identities_cse(DEMO_IFC)
        self.assertIn(OFFICE_A, inventory.space_global_ids)
        names = {row.global_id: row.name for row in inventory.products}
        self.assertEqual(names.get(OFFICE_A), "Office-A")
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
        self.assertEqual(document["space_ref"]["global_id"], OFFICE_A)
        self.assertEqual(document["space_ref"]["name"], "Office-A")
        self.assertEqual(document["space_id"], f"space:ifc:{OFFICE_A}")
        self.assertEqual(document["inspectability"], "REQUEST_EVIDENCE")
        codes = {row["code"] for row in document["open_requests"]}
        self.assertIn("bind.point_to_guid", codes)
        self.assertIn("evidence.as_built", codes)
        self.assertNotIn("identity.space", codes)

    def test_demo_fold_requests_evidence_without_a_bind(self) -> None:
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
        self.assertEqual(document["bound_cases"][0]["case_id"], "opening-17")
        self.assertEqual(len(document["cited"]), 2)
        self.assertIn("not an occupancy permit", document["non_claims"])

    def test_harness_commit_cannot_satisfy_a_point_bind(self) -> None:
        space = json.loads(_DEMO_SPACE.read_text())
        commits = [json.loads(path.read_text()) for path in _DEMO_COMMITS]
        fake = {"schema": "cse-point-bind-v1", "note": "schema only"}
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
            commitments=[(row, "c.json") for row in commits],
            binds=[(fake, "fake-bind.json"), (commits[0], "rci-as-bind.json")],
        )
        self.assertEqual(index.inspectability, "REQUEST_EVIDENCE")
        codes = {row["code"] for row in index.document["open_requests"]}
        self.assertIn("bind.point_to_guid", codes)

    def test_example_bind_file_closes_only_the_bind_hole(self) -> None:
        space = json.loads(_DEMO_SPACE.read_text())
        bind = json.loads(EXAMPLE_BIND.read_text())
        self.assertEqual(bind["global_id"], OPENING_1)
        index = fold_inspectability(
            space=space,
            receipts=[({"case_id": "opening-17", "disposition": "ACCEPT"}, "r.json")],
            binds=[(bind, str(EXAMPLE_BIND))],
        )
        codes = {row["code"] for row in index.document["open_requests"]}
        self.assertNotIn("bind.point_to_guid", codes)
        self.assertIn("evidence.as_built", codes)
        self.assertEqual(index.inspectability, "REQUEST_EVIDENCE")

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
                "global_id": OFFICE_A,
                "name": "Office-A",
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
                "global_id": OFFICE_A,
            }
        }
        bind = {
            "schema": "cse-point-bind-v1",
            "point_id": "P-Opening-1",
            "global_id": OPENING_1,
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
                "global_id": OFFICE_A,
            }
        }
        bind = {
            "schema": "cse-point-bind-v1",
            "point_id": "P-Opening-1",
            "global_id": OPENING_1,
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
                "global_id": OFFICE_A,
            }
        }
        bind = {
            "schema": "cse-point-bind-v1",
            "point_id": "P-Opening-1",
            "global_id": OPENING_1,
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
