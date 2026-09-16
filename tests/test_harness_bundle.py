"""Harness binds records. It does not fuse them into evidence or a proof."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from gat.adapters.external_commitment import canonical_digest
from gat.demo.experiment_harness import _DEMO_COMMITS, _DEFAULT_DISPOSITION, run_experiment_harness
from gat.harness.bundle import assemble_bundle, bind_commitment_file


def _envelope(payload: dict, *, schema: str, kind: str) -> dict:
    return {
        "schema": schema,
        "kind": kind,
        "claim_scope": "record-integrity-only",
        "observation_id": payload.get("observation_id"),
        "payload": payload,
        "digest": canonical_digest(payload),
    }


class HarnessBundleTests(unittest.TestCase):
    def test_binds_instrument_and_torus_without_changing_verdict(self) -> None:
        rci = _envelope(
            {
                "observation_id": "bench-1:1",
                "indicated": 2.0,
                "indicated_unit": "mm",
            },
            schema="rci-evidence-commitment-v1",
            kind="instrument-observation",
        )
        torus = _envelope(
            {"title": "first-release", "result": {"loop_length": 2.06}},
            schema="torus-report-commitment-v1",
            kind="torus-report",
        )
        disposition = {
            "format": "gat-beam-disposition-v1",
            "prior": {"verdict": "SATISFIED", "world_digest": "aa"},
            "revised_after_certificate": {
                "verdict": "VIOLATED",
                "world_digest": "bb",
            },
        }
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            rci_path = root / "rci.json"
            torus_path = root / "torus.json"
            rci_path.write_text(json.dumps(rci))
            torus_path.write_text(json.dumps(torus))
            bundle = assemble_bundle(
                commitments=[
                    (bind_commitment_file(rci_path), str(rci_path)),
                    (bind_commitment_file(torus_path), str(torus_path)),
                ],
                disposition=disposition,
            )
        document = bundle.document
        self.assertEqual(document["schema"], "notation-systems-harness-bundle-v1")
        self.assertFalse(document["released"])
        self.assertEqual(document["claim_scope"], "record-integrity-only")
        self.assertEqual(document["disposition"]["prior_verdict"], "SATISFIED")
        self.assertEqual(document["disposition"]["revised_verdict"], "VIOLATED")
        self.assertEqual(len(document["commitments"]), 2)
        self.assertFalse(document["sp1"]["invoked"])
        self.assertFalse(document["sp1"]["proof_verified"])
        self.assertFalse(document["commitments"][0]["usable_as_calibrated_observation"])

    def test_refuses_unknown_sp1_status(self) -> None:
        with self.assertRaisesRegex(ValueError, "sp1_status"):
            assemble_bundle(sp1_status="PROVED")

    def test_demo_fixtures_bind_against_beam_pin(self) -> None:
        self.assertTrue(_DEFAULT_DISPOSITION.is_file())
        for path in _DEMO_COMMITS:
            self.assertTrue(path.is_file(), msg=str(path))
        with tempfile.TemporaryDirectory() as raw:
            output = Path(raw) / "bundle.json"
            document = run_experiment_harness(
                disposition_path=_DEFAULT_DISPOSITION,
                commitment_paths=list(_DEMO_COMMITS),
                output_path=output,
                quiet=True,
            )
        self.assertEqual(len(document["commitments"]), 2)
        self.assertEqual(document["disposition"]["revised_verdict"], "VIOLATED")
        kinds = {row["kind"] for row in document["commitments"]}
        self.assertEqual(kinds, {"instrument-observation", "torus-report"})
        self.assertFalse(document["sp1"]["invoked"])


if __name__ == "__main__":
    unittest.main()
