# Next grain (Office-A declared + RCI + tank)

```bash
python -m gat.demo.calibrate_verify --demo -o out/calibrate-verify
python -m gat.demo.tank_level
```

`--measurement` is RCI JSONL (`office-a-p204:1`). CSV is refused.
Calibration status is `declared` with `source_digest` of `p204-layout-note.txt`.
`not_traceable` stays true until an instrument log exists.
`usable_as_field_evidence` stays false.

USD overlay written next to the report cites `calibration_digest` and `world_digest`.

Tank-T1 is the second noun: `IndustrialSlot:TANK-T1.Level`, no IFC, same contract.
