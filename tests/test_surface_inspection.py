"""BIM planning binding and optional genuine CSG interoperability, never approval."""

from copy import deepcopy
from hashlib import sha256
import importlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import gat.demo
from gat import GatSession, EntityId, SetParameter
from gat.adapters import surface_inspection as adapter
from gat.workflows import (
    AcceptanceCase,
    AcceptanceDisposition,
    DifferenceDecision,
    WorkflowKind,
    assess_difference,
    difference_check,
    evaluate_acceptance_case,
)


TOLERANCE = {"lateral_m": 0.001, "heading_rad": 0.001}
LIMITS = {
    "cross_track_m": 0.004,
    "heading_rad": 0.003,
    "path_length_m": 8.0,
    "wronskian_drift": 1e-8,
}


def session():
    return GatSession.load_ifc(Path(gat.demo.__file__).parent / "model.ifc")


def prepare(current, records, **changes):
    args = dict(
        quantity="Width",
        spatial_frame_id="declared-ifc-fixture-frame",
        mapping_digest=sha256(b"explicit fixture mapping, not a registration").hexdigest(),
        records=records,
        tolerance=deepcopy(TOLERANCE),
        limits=deepcopy(LIMITS),
    )
    args.update(changes)
    return adapter.prepare_request(current.world, current.var("Opening-1", "Width").entity, **args)


def disposition(current):
    checks = []
    for quantity in ("Width", "Height"):
        assessment = assess_difference(
            current.world,
            DifferenceDecision(
                current.var("Opening-1", quantity),
                current.var("Door-1", quantity),
                minimum_margin=0.05,
                confidence=0.95,
            ),
        )
        checks.append(difference_check(quantity.lower(), assessment))
    return evaluate_acceptance_case(
        AcceptanceCase(
            "inspection-planning-demo",
            WorkflowKind.OPENING_VERIFICATION,
            "Door-1 into Opening-1",
            tuple(checks),
        )
    )


class PreparationTests(unittest.TestCase):
    def setUp(self):
        self.session = session()
        # Preparation alone hashes opaque declared records; it does not run a solver.
        self.records = {"candidate": {"label": "opaque record for preparation only"}}

    def test_preparation_is_detached_and_keeps_world(self):
        before = self.session.world.digest()
        request = prepare(self.session, self.records)
        saved = deepcopy(request)
        self.records["candidate"]["label"] = "edited"
        self.assertEqual(request, saved)
        self.assertEqual(self.session.world.digest(), before)
        self.assertEqual(request["scope"], "sampled-first-order-planning-only")
        self.assertEqual(
            request["context"]["global_id"], self.session.var("Opening-1", "Width").entity.global_id
        )

    def test_base_import_never_loads_geodesic(self):
        code = "import sys; import gat.adapters.surface_inspection; assert not any(k.startswith('geodesic_testbed') for k in sys.modules)"
        run = subprocess.run([sys.executable, "-c", code], capture_output=True, timeout=30)
        self.assertEqual(run.returncode, 0, run.stderr)

    def test_display_name_is_not_entity_identity(self):
        with self.assertRaises(ValueError):
            adapter.prepare_request(
                self.session.world,
                "Opening-1",
                quantity="Width",
                spatial_frame_id="frame",
                mapping_digest="a" * 64,
                records=self.records,
                tolerance=TOLERANCE,
                limits=LIMITS,
            )

    def test_wrong_entity_and_wrong_class(self):
        for entity in (
            EntityId("IfcDoor", "absent"),
            EntityId("IfcWall", self.session.var("Opening-1", "Width").entity.global_id),
        ):
            with self.subTest(entity=str(entity)), self.assertRaises(ValueError):
                adapter.prepare_request(
                    self.session.world,
                    entity,
                    quantity="Width",
                    spatial_frame_id="frame",
                    mapping_digest="a" * 64,
                    records=self.records,
                    tolerance=TOLERANCE,
                    limits=LIMITS,
                )

    def test_unknown_quantity(self):
        with self.assertRaises(ValueError):
            prepare(self.session, self.records, quantity="Invented")

    def test_nonlength_quantity_is_not_convertible_by_guess(self):
        entity = self.session.var("Office-A", "Volume").entity
        with self.assertRaises(ValueError):
            adapter.prepare_request(
                self.session.world,
                entity,
                quantity="Volume",
                spatial_frame_id="frame",
                mapping_digest="a" * 64,
                records=self.records,
                tolerance=TOLERANCE,
                limits=LIMITS,
            )

    def test_mapping_and_frame_are_required(self):
        for change in (
            {"mapping_digest": "abc"},
            {"spatial_frame_id": ""},
            {"spatial_frame_id": "a\nb"},
        ):
            with self.subTest(change=change), self.assertRaises(ValueError):
                prepare(self.session, self.records, **change)

    def test_candidate_count_labels_and_types(self):
        for bad in ({}, {str(i): {} for i in range(17)}, {"": {}}, {"x": []}, []):
            with self.subTest(bad=type(bad).__name__), self.assertRaises(ValueError):
                prepare(self.session, bad)

    def test_numeric_inputs_are_not_coerced(self):
        for number in (True, "0.01", 0, -1, float("inf"), float("nan"), 10**400):
            with self.subTest(kind=type(number).__name__), self.assertRaises(ValueError):
                prepare(self.session, self.records, tolerance={**TOLERANCE, "lateral_m": number})

    def test_extra_limit_is_not_silently_ignored(self):
        with self.assertRaises(ValueError):
            prepare(self.session, self.records, limits={**LIMITS, "collision_free": True})


class NativeExchangeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.g = importlib.import_module("geodesic_testbed")
            cls.exchange = importlib.import_module("geodesic_testbed.inspection")
        except ImportError:
            if os.environ.get("CSE_REQUIRE_INSPECTION_PROVIDER") == "1":
                raise AssertionError("Required actual CSG inspection provider is missing") from None
            raise unittest.SkipTest("Optional CSG inspection provider is not installed") from None

    def setUp(self):
        import numpy as np

        self.session = session()
        self.records = {
            label: self.g.constant_curvature_trace(np.linspace(0, length, 21), 0)
            .as_transfer_record(units=self.g.Units("m", "radian"))
            .to_dict()
            for label, length in (("short", 2), ("long", 6))
        }
        self.request = prepare(self.session, self.records)
        self.report = self.exchange.evaluate(self.request, self.records)

    def reseal(self):
        self.report["report_digest"] = self.exchange.digest(
            {k: v for k, v in self.report.items() if k != "report_digest"}
        )

    def test_independent_serializers_agree(self):
        self.exchange.validate_request(self.request)
        for value in ({"π": -0.0, "nested": [1e-280, 1e280]}, self.records, self.request):
            self.assertEqual(adapter._bytes(value), self.exchange.canonical(value))
            self.assertEqual(adapter._digest(value), self.exchange.digest(value))

    def test_bind_and_replay_with_no_world_change_or_acceptance(self):
        before = self.session.world.digest()
        before_decision = disposition(self.session)
        bound = adapter.inspect_report(self.session.world, self.request, self.report)
        self.assertEqual(bound["status"], "bound_unverified_plan")
        first = adapter.replay_report(self.session.world, self.request, self.report)
        second = adapter.replay_report(self.session.world, self.request, self.report)
        self.assertEqual(first["status"], "bound_replayed_plan")
        self.assertNotEqual(
            first["verification"]["verification_id"], second["verification"]["verification_id"]
        )
        self.assertEqual(first["report_digest"], second["report_digest"])
        self.assertFalse(first["as_built_evidence"])
        self.assertFalse(first["may_authorize"])
        self.assertEqual(self.session.world.digest(), before)
        self.assertEqual(disposition(self.session), before_decision)
        self.assertIs(before_decision.disposition, AcceptanceDisposition.REQUEST_EVIDENCE)

    def test_integrity_inspection_does_not_run_companion(self):
        from unittest.mock import patch

        with patch.object(self.exchange, "evaluate", side_effect=AssertionError("must not run")):
            self.assertEqual(
                adapter.inspect_report(self.session.world, self.request, self.report)[
                    "numerical_replay"
                ],
                "not_performed",
            )

    def test_stale_world_refused_after_design_change(self):
        self.session.run(SetParameter(self.session.var("Opening-1", "Width"), 1.05, 0.005))
        with self.assertRaisesRegex(ValueError, "Stale"):
            adapter.inspect_report(self.session.world, self.request, self.report)

    def test_original_request_binding_not_self_asserted(self):
        original = deepcopy(self.request)
        self.report["request"]["context"]["mapping_digest"] = "9" * 64
        self.report["request"]["request_digest"] = adapter._digest(
            {k: v for k, v in self.report["request"].items() if k != "request_digest"}
        )
        self.reseal()
        with self.assertRaises(ValueError):
            adapter.inspect_report(self.session.world, original, self.report)

    def test_consistently_rehashed_numeric_lie_stays_unverified_then_replay_refuses(self):
        self.report["results"][0]["values"]["cross_track_m"] += 0.123
        self.reseal()
        bound = adapter.inspect_report(self.session.world, self.request, self.report)
        self.assertEqual(bound["numerical_replay"], "not_performed")
        with self.assertRaisesRegex(ValueError, "replay"):
            adapter.replay_report(self.session.world, self.request, self.report)

    def test_rehashed_candidate_content_cannot_replace_original(self):
        self.report["records"]["short"]["b"][-1] += 1
        self.reseal()
        with self.assertRaises(ValueError):
            adapter.inspect_report(self.session.world, self.request, self.report)

    def test_authority_flags_cannot_be_lifted(self):
        for key, value in (
            ("may_authorize", True),
            ("physical_validation", "passed"),
            ("cryptographic_verification", "verified"),
        ):
            report = deepcopy(self.report)
            report[key] = value
            report["report_digest"] = adapter._digest(
                {k: v for k, v in report.items() if k != "report_digest"}
            )
            with self.subTest(key=key), self.assertRaises(ValueError):
                adapter.inspect_report(self.session.world, self.request, report)

    def test_unexpected_nested_authority_not_accepted(self):
        self.report["results"][0]["approved"] = True
        self.reseal()
        with self.assertRaises(ValueError):
            adapter.inspect_report(self.session.world, self.request, self.report)

    def test_missing_or_duplicate_candidates_cannot_be_hidden(self):
        for action in ("drop", "duplicate", "bad-label"):
            report = deepcopy(self.report)
            if action == "drop":
                report["results"].pop()
            elif action == "duplicate":
                report["results"][1] = deepcopy(report["results"][0])
            else:
                report["ranking"][0] = []
            report["report_digest"] = adapter._digest(
                {k: v for k, v in report.items() if k != "report_digest"}
            )
            with self.subTest(action=action), self.assertRaises(ValueError):
                adapter.inspect_report(self.session.world, self.request, report)

    def test_request_reordering_does_not_create_a_new_claim(self):
        other = dict(reversed(list(self.request.items())))
        self.assertEqual(
            adapter.inspect_report(self.session.world, other, self.report)["request_digest"],
            self.request["request_digest"],
        )

    def test_demo_retains_plan_without_changing_acceptance(self):
        from gat.demo.surface_inspection import run

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "retained"
            summary = run(output)
            self.assertEqual(summary["as_built_disposition"], "REQUEST_EVIDENCE")
            self.assertTrue(summary["world_unchanged"])
            self.assertEqual(summary["numerical_replay"], "matched")
            self.assertEqual(summary["within_sampled_limits"], {"short": True, "long": False})
            original = {p.name: p.read_bytes() for p in output.iterdir()}
            self.assertEqual(len(original), 7)
            with self.assertRaises(FileExistsError):
                run(output)
            self.assertEqual(original, {p.name: p.read_bytes() for p in output.iterdir()})

    def test_report_tampering_without_resealing(self):
        self.report["results"][0]["values"]["cross_track_m"] += 0.01
        with self.assertRaisesRegex(ValueError, "digest"):
            adapter.inspect_report(self.session.world, self.request, self.report)


if __name__ == "__main__":
    unittest.main()
