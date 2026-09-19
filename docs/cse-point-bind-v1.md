# Point-to-IfcGuid bind v1

Satellite. A bind is a named identity claim: *this layout point is that IFC
entity*, declared to a stated sigma, in a stated frame, at a stated epoch. It is
not a measurement, not a harness digest, and not an authorization.

## The record

Schema: [`validation/cse-point-bind-v1.schema.json`](../validation/cse-point-bind-v1.schema.json)
Example: [`validation/cse-point-bind-v1.json`](../validation/cse-point-bind-v1.json)
Validator: `gat.harness.point_bind.bind_point`

Required at the top level: `schema`, `claim_scope` (`record-integrity-only`),
`point_id`, `global_id`, `ifc_class`, `payload`.

Required inside `payload`: `point_id`, `global_id`, `ifc_class`, `frame_id`,
`epoch`, `sigma`, `sigma_unit`, `sigma_reason`.

**`sigma` is required.** A bind that does not say how well the point is known
cannot license an observation. "The CAD said so" is a sigma with a reason
(`design-declared`, a layout tolerance), not an absence of one.

Optional, and each says something specific:

| field | what it adds |
|---|---|
| `space_id` | the `IfcSpace` the point sits in, as `space:ifc:<GlobalId>` |
| `quantity` | which slot a later observation would touch, so a client does not guess |
| `receipt_digest` | a link to an evidence receipt |
| `world_digest` | which lowering the Guid was checked against |

`receipt_digest` does **not** close `evidence.as_built`. Identity and evidence are
two holes in the fold, and a bind that cites a receipt is still only an identity
claim. `world_digest` is machine-local (`docs/digest-portability-v1.md`), so a
bind that records it can be re-checked offline while one that omits it must be
re-checked against a live world.

## Rules

- `gat.harness --commit` files never satisfy `bind.point_to_guid`. A commit binds
  an external measurement digest; it carries a sigma and a reason, which is most
  of what a bind needs, and that is exactly why it is refused *by name*. It says
  nothing about which IfcGuid the point is.
- A JSON object that only says `schema: cse-point-bind-v1` is not a bind.
- A paragraph from an MCP agent is not a bind.
- A display name is not a GlobalId. `Opening-1` is a label a human chose;
  `GATOPN0000000000000200` is an identity the file carries.
- Coordinates without an IfcGuid are not a bind.
- Binding Opening-1 does not change Beam-B1 or shrink `Sigma`.

## What this file used to leave open

The four rules above were written before anything enforced them, and the tree
ended up with **two definitions of "a bind"**:

| definition | required | used by |
|---|---|---|
| `point_bind.bind_point` | schema, claim_scope, a bindable `ifc_class`, a non-display Guid, `frame_id`, `epoch`, `sigma`+unit+reason, a matching digest | two demos |
| `inspectability._is_bind` | `schema`, non-empty `point_id`, non-empty `global_id` | **the fold** |
| `present_space` | `schema` | the packet |

The fold decides whether `bind.point_to_guid` is an open hole, and it used the
weak one. So this closed it:

```json
{"schema": "cse-point-bind-v1", "point_id": "P-204", "global_id": "GATOPN0000000000000200"}
```

No frame, no epoch, no sigma. That is how every MCP client invents its own bind
shape and all of them are accepted — the third rule above was the one being
broken, and by the most realistic caller.

Worse, `validation/cse-point-bind-v1.json` — the repository's own example of
`cse-point-bind-v1` — declared `claim_scope: identity-bind-only` and carried no
sigma, frame or epoch. The validator that defines the schema **refused the file
named after it**, while the fold's duck-type accepted it.

Both are fixed. There is one definition: `_is_bind` delegates to `bind_point`,
`present_space` uses the same predicate, and the schema file states it so a
client can check before it writes. `tests/test_point_bind_schema.py` asserts the
fold and the validator agree on every candidate document, and reverting the
duck-type fails two of its tests.

An open hole now says *why* it is open. `bind_refusals` puts the refusal reason in
the request, because "nobody wrote a bind" and "somebody wrote one wrong" are
different situations and a superintendent should not have to diff a schema to tell
them apart:

```
bind.point_to_guid  asks_for: layout point bound to an IfcGuid
                    refused:  mcp-agent.json: claim_scope must be record-integrity-only
```

A malformed bind leaves the hole open rather than raising through the fold, so it
cannot hide `identity.space` or `evidence.as_built`.
