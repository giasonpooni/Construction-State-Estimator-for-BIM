# Atlas v1

Walkable slots. Not a second Kalman.

`x' = T x + c` is declared on an edge. `P' = T P T^T` stays in JSPT.

Observation edges without `sigma` are refused. Tank level does not walk
onto opening width. Beam-B1 lives in a different world; identity is the
Guid plus a cited digest, not a merged `world_digest`.

```bash
python -m gat.demo.atlas_gap -o out/atlas
```

## The world gate, and the hole an audit found in it

`add_edge` refuses any edge whose endpoints are in different worlds. An edge is
transport: it carries a value from one coordinate to another and so asserts they
measure one thing, and no kind of edge may assert that across worlds — a
`coupling` with a written reason least of all, because a reason is prose and this
is the one claim the system exists to refuse. Worlds are related by citing them
side by side (`atlas_cov.cite_disposition_worlds`), never by transporting between
them.

That gate validates **when the edge is inserted, and never again**, and
`slot_id()` is built from `ifc_class`, `global_id`, `quantity` and `unit` — the
world is deliberately not in it. So the same quantity in two worlds is one key in
`Atlas.slots`, and re-declaring a slot used to replace it silently, changing the
world of every edge already pointing at that id.

Probed directly, the result was a `cse-atlas-v1` document that said

```json
"worlds": ["world-one", "world-two"],
"world_rule": "every edge stays inside one world; worlds are cited, not transported"
```

while carrying a `representation` edge from `world-one` to `world-two`. The gate
had passed; the endpoint moved afterwards.

`add_slot` now refuses a re-declaration that changes a slot's world, so "a slot's
world is fixed once declared" is an enforced invariant rather than an assumption
`add_edge` makes. An identical re-declaration stays idempotent.
`tests/test_atlas_world_gate.py::SlotWorldIsFixedTests` pins all of it, including
that every edge in an atlas still ends in one world after a refused
re-declaration.

The narrower alternative — putting the world into `slot_id()` — would change
every slot id string, and slot ids appear in published `cse-atlas-v1` documents.
That is a schema change and this is not, so the invariant is enforced where it is
cheapest to enforce.
