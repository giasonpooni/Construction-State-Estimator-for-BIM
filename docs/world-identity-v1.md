# World identity: what a digest names

Two identities, answering different questions.

```text
world_digest      this lowering, here, named this way
portable_digest    this model and this belief, anywhere
```

## The thing to know first

`World.digest()` hashes the IR printer's dump, and the printer emits every
`meta` key — including `source`, which is the path string the caller passed to
`load_ifc`. So one file, byte for byte, has as many world digests as there are
ways to spell its name:

| spelled as | `world_digest` |
|---|---|
| `gat/demo/model.ifc` | `020383e8…` |
| `./gat/demo/model.ifc` | `e7f0d899…` |
| `/home/user/…/gat/demo/model.ifc` | `ae337184…` |
| `gat/demo/../demo/model.ifc` | `c9d15bef…` |

This is not a bug in `world_digest`. It is what `world_digest` is for: checking
that a decision and a model are the *same lowering*, which is exactly the
mismatch `gat view` reports when it says a decision "was evaluated on a
different world than the model … load it with the same path form the headless
request used".

It does mean one thing that matters for the portfolio: **a pinned
`world_digest` is only reproducible from the same checkout, with the same path
spelling.** Two checkouts of this repo at different absolute paths produce
`ae337184…` and `53ef806a…` for the same file.

## What that cost, concretely

`validation/opening-fit-disposition-v1.json` and
`validation/opening-fit-design-review-disposition-v1.json` pin
`world_digest: be62ab70…` and `case_digest: 548200b5…`. No current path form
reproduces those, and nothing in the tree reads either file — so the
opening-fit replay, which is one of the two dispositions the kernel freeze
protects, has been unverifiable rather than verified. Re-pinning it is a
version bump, not a repair, so it is left as it stands and recorded here.

## The portable identity

`gat.adapters.portable_identity` adds a second digest and changes no existing
one. Same composition as the kernel's — module digest, then the full-view mean
and covariance — with location meta elided:

```python
from gat.adapters.portable_identity import portable_world_digest, world_identity

portable_world_digest(world)   # same for every spelling of the same file
world_identity(world)          # both digests + the source, for a citation
```

Only `source` is elided. `lowering_scope` is not: a scope is what the world
**is**, not where it came from, so a scoped world keeps a distinct portable
digest. The belief participates too — an `ObserveQuantity` moves the portable
digest, or it would not identify a world at all.

## Which to use

- Same lowering? → `world_digest`. Keep using it, keep pinning it locally.
- Crossing a repo, a machine, or a checkout? → `portable_digest`.

`identity_gap` still compares `world_digest` values, so its
`beam_pin_is_live_ifc` answers a question about path spellings. Moving it to
the portable digest would change `validation/identity-gap-v1.json`, which the
harness reads, so that is a deliberate follow-up rather than a side effect of
adding this.

Nothing here merges worlds. `forced_common_world` stays false; equal names
still do not imply equal worlds, and now a citation can actually say which.
