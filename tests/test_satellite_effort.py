"""Effort gate may only refuse or defer closed satellites. It does not run them."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from gat.demo.experiment_harness import (
    _DEFAULT_DISPOSITION,
    _DEFAULT_EFFORT,
    _DEMO_COMMITS,
    run_experiment_harness,
)
from gat.harness.effort import decide_satellite, load_effort_table


class SatelliteEffortTests(unittest.TestCase):
    def test_default_table_refuses_closed_gates(self) -> None:
        table = load_effort_table(_DEFAULT_EFFORT)
        sp1 = decide_satellite(table, "sp1_zkvm", hole="bind.point_to_guid", expected_information_nats=100.0)
        cuda = decide_satellite(table, "cuda_jspt", hole="bind.point_to_guid", expected_information_nats=100.0)
        rust = decide_satellite(table, "rust_ingest")
        self.assertEqual(sp1.disposition, "REFUSE")
        self.assertEqual(cuda.disposition, "REFUSE")
        self.assertEqual(rust.disposition, "REFUSE")
        self.assertFalse(sp1.as_policy()["invoked"])

    def test_python_path_defers_without_a_named_hole(self) -> None:
        table = load_effort_table(_DEFAULT_EFFORT)
        decision = decide_satellite(table, "python_uv")
        self.assertEqual(decision.disposition, "DEFER")
        self.assertTrue(decision.allowed)

    def test_python_path_may_invoke_when_information_exceeds_cost(self) -> None:
        table = load_effort_table(_DEFAULT_EFFORT)
        decision = decide_satellite(
            table,
            "python_uv",
            hole="bind.point_to_guid",
            expected_information_nats=1.0,
        )
        self.assertEqual(decision.disposition, "INVOKE")
        self.assertFalse(decision.as_policy()["invoked"])

    def test_unknown_satellite_is_refused(self) -> None:
        table = load_effort_table(_DEFAULT_EFFORT)
        decision = decide_satellite(table, "graph_transformer")
        self.assertEqual(decision.disposition, "REFUSE")

    def test_harness_records_policy_without_changing_beam_verdict(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            output = Path(raw) / "bundle.json"
            document = run_experiment_harness(
                disposition_path=_DEFAULT_DISPOSITION,
                commitment_paths=list(_DEMO_COMMITS),
                output_path=output,
                quiet=True,
                request_satellites=["sp1_zkvm", "cuda_jspt"],
                hole="bind.point_to_guid",
                expected_information_nats=50.0,
            )
        self.assertFalse(document["sp1"]["invoked"])
        self.assertEqual(document["disposition"]["revised_verdict"], "VIOLATED")
        decisions = {row["satellite"]: row for row in document["effort"]["decisions"]}
        self.assertEqual(decisions["sp1_zkvm"]["disposition"], "REFUSE")
        self.assertEqual(decisions["cuda_jspt"]["disposition"], "REFUSE")
        self.assertTrue(decisions["sp1_zkvm"]["world_digest_unchanged"])
        self.assertFalse(decisions["sp1_zkvm"]["invoked"])


if __name__ == "__main__":
    unittest.main()
