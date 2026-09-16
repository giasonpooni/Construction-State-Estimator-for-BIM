# Present space v1

Finished tool on the demo plant. Fail-closed package gate.

```bash
python -m gat.demo.present_space --demo -o out/present.json
gat-present --demo --bind validation/cse-point-bind-v1.json \
  --calibration validation/cse-calibration-v1.json \
  --apply-lab-observation --value 0.90 -o out/present.json
```

Required before `inspectability=ACCEPT`:

1. IfcSpace identity (Office-A `GATSPC0000000000000300`)
2. `cse-point-bind-v1` for Opening-1
3. `cse-calibration-v1` with finite `sigma`
4. ledger-bound observation digest (`--apply-lab-observation`)
5. `session.verify()` passed

Still not an occupancy permit. `may_authorize` stays false while
`traceable` is false.
