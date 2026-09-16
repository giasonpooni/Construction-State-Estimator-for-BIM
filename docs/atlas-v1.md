# Atlas v1

Walkable slots. Not a second Kalman.

`x' = T x + c` is declared on an edge. `P' = T P T^T` stays in JSPT.

Observation edges without `sigma` are refused. Tank level does not walk
onto opening width. Beam-B1 lives in a different world; identity is the
Guid plus a cited digest, not a merged `world_digest`.

```bash
python -m gat.demo.atlas_gap -o out/atlas
```
