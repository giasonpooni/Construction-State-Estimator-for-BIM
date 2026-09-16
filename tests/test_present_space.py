"""Present-space tool stays closed without calibration and verification."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from gat.demo.present_space import (
    _DEMO_BIND,
    _DEMO_CAL,
    _DEMO_IFC,
    _DEMO_RECEIPT,
    _DEMO_SPACE,
    present_space,
)
from gat.errors import GatError


class PresentSpaceTests(unittest.TestCase):
    def test_demo_package_requests_calibration_bind_and_as_built(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            document = present_space(
                model_path=_DEMO_IFC,
                space_path=_DEMO_SPACE,
                receipt_path=_DEMO_RECEIPT,
                output_path=Path(raw) / "present.json",
            )
        self.assertEqual(document["format"], "cse-present-space-v1")
        self.assertEqual(document["inventory_office_a"], "GATSPC0000000000000300")
        self.assertEqual(document["inspectability"], "REQUEST_EVIDENCE")
        codes = {row["code"] for row in document["open_requests"]}
        self.assertIn("bind.point_to_guid", codes)
        self.assertIn("evidence.as_built", codes)
        self.assertIn("calibration.declared", codes)
        self.assertTrue(document["verification"]["passed"])
        self.assertFalse(document["may_authorize"])

    def test_bind_and_calibration_still_need_an_observation(self) -> None:
        document = present_space(
            model_path=_DEMO_IFC,
            space_path=_DEMO_SPACE,
            receipt_path=_DEMO_RECEIPT,
            bind_path=_DEMO_BIND,
            calibration_path=_DEMO_CAL,
        )
        codes = {row["code"] for row in document["open_requests"]}
        self.assertNotIn("bind.point_to_guid", codes)
        self.assertNotIn("calibration.declared", codes)
        self.assertIn("evidence.as_built", codes)
        self.assertEqual(document["inspectability"], "REQUEST_EVIDENCE")
        self.assertFalse(document["may_authorize"])

    def test_lab_observation_without_calibration_is_refused(self) -> None:
        with self.assertRaisesRegex(GatError, "requires cse-calibration-v1"):
            present_space(
                model_path=_DEMO_IFC,
                space_path=_DEMO_SPACE,
                bind_path=_DEMO_BIND,
                apply_lab_observation=True,
                observed_value=0.9,
            )

    def test_lab_observation_with_calibration_can_close_the_package(self) -> None:
        document = present_space(
            model_path=_DEMO_IFC,
            space_path=_DEMO_SPACE,
            bind_path=_DEMO_BIND,
            calibration_path=_DEMO_CAL,
            apply_lab_observation=True,
            observed_value=0.9,
        )
        self.assertEqual(document["inspectability"], "ACCEPT")
        self.assertEqual(document["open_requests"], [])
        self.assertTrue(document["verification"]["passed"])
        self.assertTrue(document["lab_observation_applied"])
        self.assertFalse(document["calibration"]["traceable"])
        self.assertFalse(document["may_authorize"])


if __name__ == "__main__":
    unittest.main()
