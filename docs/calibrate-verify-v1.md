# Calibrate then verify v1

Finished Office-A tool. Not a stamp.

```bash
python -m gat.demo.calibrate_verify --demo -o out/calibrate-verify
```

The command will not run without a calibration declaration and a measurement.
A prototype calibration yields verification `REQUEST_EVIDENCE` even when
invariants pass and the inspectability packet is presentable.

Unknown keys are refused. Unit mismatch is refused. Missing sigma is refused.

Writes `calibrate-verify-report.json`, `inspectability.json`, and `ledger.json`.

Prototype is not a traceable certificate. Verification is not occupancy.
