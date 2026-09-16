# Public-data cross-reference for Office-A opening simulation

Not a field measurement. Not a code compliance stamp.
Clear width \(\neq\) IFC `Width` on `IfcOpeningElement` or `IfcDoor`.

## What the IFC already holds

| Subject | Quantity | Prior mean | Prior \(\sigma\) |
| --- | --- | ---: | ---: |
| Opening-1 | Width | 1.000 m | 0.005 m |
| Door-1 | Width | 0.900 m | 0.003 m |

Shipped prototype observation: indicated 1.002 m, \(\sigma=0.005\) m.
Offset from design: \(+2\) mm.

## Published numbers used

| Source | Quantity | Value | Use here |
| --- | --- | --- | --- |
| IBC 2024 \S1010.1.1 | egress *clear* opening width | 32 in = 813 mm | floor, not the IFC slot |
| ADA 2010 \S404.2.3 | accessible *clear* width | 32 in | same distinction |
| NBC / barrier-free path (commonly 800–850 mm) | doorway *clear* width | 800–850 mm | Canadian floor |
| CSA/ASC B652:23 5.7.1 | accessible dwelling *clear* width | 860 mm; note a 965 mm leaf can achieve it | leaf vs clear |
| SDI 117 | unmarked linear dimensions | \(\pm 1/16\) in = \(\pm 1.6\) mm | manufacturing \(\sigma\) candidate |
| HMMA 841-13 install | frame opening width | +1.6 / \(-0.8\) mm | installation envelope |
| ACI 117-10 | concrete opening size | \(+25\) / \(-13\) mm | only if the host is concrete |

## Honest mapping

- Door-1 0.900 m is a metric *leaf*, not IBC clear 0.813 m.
- Opening-1 1.000 m minus Door-1 0.900 m = 100 mm nominal clearance around the leaf; the tool's 50 mm fit margin is a GAT check, not a code clause.
- +2 mm on the opening vs design sits outside SDI \(\pm 1.6\) mm if that were the only budget, and well inside ACI concrete opening undersize/oversize.
- None of these sources is a resection of P-204.

## Simulated packet (still prototype)

`gat/demo/harness_fixtures/p204-opening-measurement-public-sim-v1.json`
keeps indicated 1.002 m and declares \(\sigma=0.0016\) m from SDI 117 linear
tolerance, with the ACI envelope noted in the reason. Calibration remains
`not_traceable`.
