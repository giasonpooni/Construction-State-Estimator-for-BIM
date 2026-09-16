"""USD projection is a look-only overlay of an already-computed world."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from gat.demo.experiment_harness import _DEMO_COMMITS, _DEFAULT_DISPOSITION
from gat.demo.usd_projection import run_usd_projection
from gat.harness.usd_projection import project_canonical_state


class UsdProjectionTests(unittest.TestCase):
    def test_overlay_does_not_mutate_and_keeps_verdict(self) -> None:
        disposition = {
            "format": "gat-beam-disposition-v1",
            "beam": {"name": "Beam-B1"},
            "prior": {"verdict": "SATISFIED", "world_digest": "aa" * 32},
            "revised_after_certificate": {
                "verdict": "VIOLATED",
                "world_digest": "bb" * 32,
            },
        }
        projection = project_canonical_state(
            disposition=disposition,
            project_space_id="sandbox-beam-b1",
        )
        document = projection.document
        self.assertEqual(document["schema"], "notation-systems-usd-projection-v1")
        self.assertFalse(document["mutates_source"])
        self.assertEqual(document["layers"]["estimate"]["revised_verdict"], "VIOLATED")
        self.assertTrue(document["layers"]["estimate"]["overlay_only"])
        self.assertEqual(document["layers"]["simulation"]["status"], "empty")
        self.assertTrue(document["layers"]["bim"]["entity_is_not_mesh"])
        self.assertEqual(document["workbench"]["omniverse"], "not-in-v0")

    def test_demo_projection_binds_shipped_pin(self) -> None:
        self.assertTrue(_DEFAULT_DISPOSITION.is_file())
        with tempfile.TemporaryDirectory() as raw:
            output = Path(raw) / "proj.json"
            document = run_usd_projection(
                disposition_path=_DEFAULT_DISPOSITION,
                commitment_paths=list(_DEMO_COMMITS),
                output_path=output,
                project_space_id="sandbox-beam-b1",
                quiet=True,
            )
        self.assertEqual(document["project_space_id"], "sandbox-beam-b1")
        self.assertEqual(document["layers"]["estimate"]["revised_verdict"], "VIOLATED")
        self.assertGreaterEqual(len(document["layers"]["telemetry"]["commitment_digests"]), 2)
        self.assertFalse(document["layers"]["telemetry"]["usable_as_calibrated_observation"])


if __name__ == "__main__":
    unittest.main()
