# Combined USD stage v1

Satellite. Viewer assembly only. Restart is still the CSE carrier.

```text
/World
  GAT        reference cse.usdc:/GAT     Path C — restart file
  SiteLook   payload sitelook.usda       Path A — display
```

Binds stay `validation/cse-point-bind-v1.json`. They are not prims.

## Rules

- `GatSession.load_openusd` / `read_openusd` take the **carrier**, not `world.usda`.
- Stronger opinions on `SiteLook` do not change the world digest.
- Stronger opinions on `/World/GAT/State/Belief` without a new snapshot
  digest still fail when the *carrier* is read.
- IfcOpenShell / IfcConvert meshes may replace `sitelook.usda` later.
  Authority remains `INSUFFICIENT`.

```bash
python -m gat.demo.combined_usd_stage -o out/combined
```
