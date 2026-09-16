"""Present process writes a packet and never stamps."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from gat.demo.present_process import STAMP, run_process


class PresentProcessTests(unittest.TestCase):
    def test_demo_process_opens_three_holes_and_refuses_stamp(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            manifest = run_process(output_dir=raw, lab=False)
            names = {path.name for path in Path(raw).iterdir()}
        self.assertEqual(manifest["format"], "cse-present-process-v1")
        self.assertEqual(manifest["inspectability"], "REQUEST_EVIDENCE")
        self.assertFalse(manifest["may_authorize"])
        self.assertEqual(manifest["stamp"], STAMP)
        codes = {row["code"] for row in manifest["open_requests"]}
        self.assertEqual(
            codes, {"bind.point_to_guid", "evidence.as_built", "calibration.declared"}
        )
        self.assertTrue(
            {
                "00-manifest.json",
                "01-verify.json",
                "02-inventory.json",
                "03-package.json",
                "04-stamp-refused.json",
            }
            <= names
        )

    def test_lab_process_can_accept_package_and_still_refuses_stamp(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            manifest = run_process(output_dir=raw, lab=True, value=0.9)
            stamp = json.loads((Path(raw) / "04-stamp-refused.json").read_text())
        self.assertEqual(manifest["inspectability"], "ACCEPT")
        self.assertTrue(manifest["verification_passed"])
        self.assertFalse(manifest["may_authorize"])
        self.assertEqual(stamp["kind"], "refused")
        self.assertIsNone(stamp["record"])


if __name__ == "__main__":
    unittest.main()
