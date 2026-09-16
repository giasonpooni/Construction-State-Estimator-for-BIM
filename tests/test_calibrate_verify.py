"""The tool will not observe without calibration, and will not stamp a prototype."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from gat.demo.calibrate_verify import run_calibrate_verify
from gat.harness.calibration import load_calibration, load_measurement


ROOT = Path(__file__).resolve().parents[1]
CAL = ROOT / "gat" / "demo" / "harness_fixtures" / "p204-opening-calibration-v1.json"
MEAS = ROOT / "gat" / "demo" / "harness_fixtures" / "p204-opening-measurement-v1.json"
BIND = ROOT / "gat" / "demo" / "harness_fixtures" / "p204-opening-bind.json"
SPACE = ROOT / "gat" / "demo" / "harness_fixtures" / "space-office-a-model.json"
MODEL = ROOT / "gat" / "demo" / "model.ifc"


class CalibrationContractTests(unittest.TestCase):
    def test_unknown_key_is_refused(self) -> None:
        raw = json.loads(CAL.read_text(encoding="utf-8"))
        raw["preference"] = "wide"
        with self.assertRaisesRegex(ValueError, "unknown keys"):
            load_calibration(raw)

    def test_measurement_without_sigma_is_refused(self) -> None:
        raw = json.loads(MEAS.read_text(encoding="utf-8"))
        raw.pop("sigma")
        raw.pop("digest", None)
        with self.assertRaisesRegex(ValueError, "sigma"):
            load_measurement(raw)


class CalibrateVerifyTests(unittest.TestCase):
    def test_demo_requires_calibration_and_does_not_stamp(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            document = run_calibrate_verify(
                model_path=MODEL,
                calibration_path=CAL,
                measurement_path=MEAS,
                bind_path=BIND,
                space_path=SPACE,
                output_dir=raw,
            )
            report = Path(raw) / "calibrate-verify-report.json"
            ledger = Path(raw) / "ledger.json"
            self.assertTrue(report.is_file())
            self.assertTrue(ledger.is_file())
        self.assertEqual(document["calibration"]["status"], "prototype")
        self.assertTrue(document["calibration"]["not_traceable"])
        self.assertFalse(document["receipt"]["usable_as_field_evidence"])
        self.assertEqual(document["verification"]["disposition"], "REQUEST_EVIDENCE")
        self.assertTrue(document["verification"]["passed"])
        self.assertGreaterEqual(document["verification"]["fit_margin_m"], 0.05)
        self.assertEqual(document["inspectability"], "ACCEPT")


if __name__ == "__main__":
    unittest.main()
