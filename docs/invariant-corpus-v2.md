# Invariant reference corpus v2

Focal split for this stack:

```text
I  invariant corpus     declared identity of the plant
   needle
x  free coordinates     what measurements may still move
   chart                the coordinate system a declaration fixes x in
```

Inference does not invent names. If a tool cannot point at a row in
`validation/invariant-corpus-v2.json`, it is another file, not reconstruction.

Load: `from gat.corpus import load_corpus`.
Needle only `var.*` rows. Invariants raise `CorpusError`.

## What v2 adds, and why

A needle names a quantity that is free until a declaration fixes it. v1 said
*which kind* of declaration fixes it (`needs: ["declared-A"]`) but not *which
coordinate system* it is fixed in. Across the portfolio that is not a detail:

| member | needle | fixed by | chart |
|---|---|---|---|
| Construction-State-Estimator-for-BIM | `var.opening-width` | `cal.declared`, `bind.point_to_guid`, `observe` | `chart.cse-ifc-space` |
| Retrofitted-Computational-Instrumentation | `var.indicated` | `declared-calibration` | `chart.rci-indication` |
| Jacobian-Sensitivity-Propagation-Testbed | `var.dx` | `declared-J` | `chart.jspt-tangent` |
| Parameterized-Lyapunov-Stability-Runtime | `var.x` | `declared-A` | `chart.plsr-plant` |
| State-Estimation-Testbed | `var.x` | `declared-H` | `chart.set-observation` |
| Fluid-State-Reconstruction-Testbed | `var.storage` | `declared-balance`, `gauge` | `chart.fsrt-balance` |
| Flat-Torus-Moduli-and-Geodesic-Explorer | `var.geodesic-point` | `declared-lattice` | `chart.ftmge-lattice` |
| Geodesic-Flow-and-Jacobi-Field-Testbed | `var.jacobi` | `declared-flow` | `chart.gfjft-flow` |
| CNC-Machine-MCP | `var.pose` | `observe` | `chart.cnc-axis` |
| Atelier-MCP | `var.stock` | `observe` | `chart.atelier-stock` |
| Geodesic-Telemetry-Engine | `var.state` | `observe` | `chart.gte-manifold` |
| Lattice-Calibration-Module | `var.local-estimate` | `declared-constraint` | `chart.lcm-constraint` |

PLSR and the State-Estimation-Testbed both declare `var.x` with quantity
`state`. One is fixed by a declared plant `A`, the other by a declared
observation `H`. They are not the same coordinate, and a covariance on one may
not be read as a covariance on the other. Under v1 nothing in the index could
say so; the needle id alone made them look like one name.

So: **a needle is only unique with its chart.** Charts are globally unique
across `validation/invariant-corpus-index-v2.json`, and two members may share
a needle id only in different charts.

## Crossing a chart

A quantity may not be carried from one chart to another by renaming it. The
transport law is owned upstream, pinned in `validation/jspt-pin-v1.json`:
JSPT owns `first_order_covariance` and chart law A3. CSE cites it one way and
keeps its own local pushforward, asserting agreement rather than importing the
companion at runtime — see `tests/test_jspt_pin.py`.

That is the whole of the interoperability contract. Nothing here makes two
charts into one world; `identity_gap` exists to keep `forced_common_world`
false.

## Migrating a sibling corpus

v1 documents still load, so each repo can migrate on its own commit. `chart`
is required only once a document declares `schema: invariant-corpus-v2`, and
`Corpus.chart_of` raises on a v1 document rather than guessing.

To migrate, take the chart from the table above and:

```bash
python3 validation/migrate_corpus_v2.py <path-to-sibling-repo> <chart.id>
```

Cross-repo copies must keep `claim_scope: computational-integrity-only`. They
add local identities; they do not add a second engine.
