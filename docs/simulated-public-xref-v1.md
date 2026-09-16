# Simulated public cross-reference v1

Not field evidence. Fills the present-process holes so the packet can
run. Stamp stays refused.

| Quantity | Value | Where it came from |
|---|---|---|
| Opening-1 Width indicated | 1.0 m | shipped IFC QTO, not a tape |
| Door-1 Width | 0.9 m | shipped IFC QTO |
| IBC min clear width | 0.813 m | IBC 2024 §1010.1.1 (32 in) |
| Declared σ | 0.003 m | Trimble S5 prism RMSE 2 mm+2 ppm at ~5 m plus ~1 mm centering, RSS rounded up; ISO 17123-5 is the field-test family |

```bash
python -m gat.demo.present_process --demo --public-xref -o out/present-packet-xref
```

CSE does not conclude the opening “meets IBC.” It only conditions Width
with a declared public-spec sigma and still writes `04-stamp-refused.json`.
