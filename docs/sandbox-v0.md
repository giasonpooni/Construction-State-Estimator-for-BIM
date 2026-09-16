# BIM sandbox v0

First physically structured world. Not the product category.
See [domain-v1.md](domain-v1.md).

## First experiment

```text
IFC (Beam-B1 / opening)
  → GAT world + ledger          canonical
  → gat-headless / beam_assurance
  → project-space bundle + Merkle root
  → USD projection overlay      look only
  → Blender read-only look
```

```bash
python -m gat.demo.beam_assurance out/beam
python -m gat.demo.experiment_harness --demo -o out/harness-bundle.json
python -m gat.demo.usd_projection --demo -o out/usd-projection.json
```

Success is: the overlay shows the same verdict as the pin; `mutates_source`
is false; `L_simulation` is empty; a millimetre from RCI is still not Fy.

## Layers

The projection document names five USD composition layers. They are a
*picture* of the canonical world, not five owners of Sigma.

| Layer | May hold | May not hold |
| --- | --- | --- |
| L_geometry | IFC-derived view with authority tags | silent reconstruction |
| L_BIM | GlobalId, type, quantities | dense Sigma |
| L_telemetry | commitment hexes | live ADC as a primvar |
| L_estimate | displayed verdict + world digest | a second Kalman |
| L_simulation | empty in v0 | authority for ACCEPT |

Muting L_estimate must not change the ledger. That is the test that USD
is a projection.

## Not this increment

- Synthetic camera as vision net
- Omniverse / RTX sensors
- AutoCAD / Revit plugins
- C++ estimator
- Lyapunov on a free body in a room

Those wait on a declared instrument record, a declared plant, or a paid
adapter. The optional Pixar carrier remains `export_openusd` /
`docs/openusd-carrier-v0.md` and still requires the extra.
