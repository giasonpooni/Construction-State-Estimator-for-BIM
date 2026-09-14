# World identity v2 — path-independent digests

Status: implemented. Runtime contract `gat-world-v2`.

## Problem

The module digest is the SHA-256 of the deterministic IR dump, and that dump
printed every key in `module.meta` — including `source`, the path string the
caller happened to pass to `GatSession.load_ifc`. One model therefore had as
many identities as it had spellings:

```text
gat/demo/beam_model.ifc        -> 88082f94…
/home/user/…/beam_model.ifc    -> 43d636e0…
```

Same bytes, same belief, different world. The consequences were not cosmetic:

- Pinned validation records could not be reproduced on another machine, so
  the `validation/` tier drifted into unverifiable assertion.
- A ledger or signed carrier written on one machine could not replay on
  another that had checked the model out somewhere else.
- `gat view` had to reconstruct the caller's path form from the headless
  request before it could bind a decision to a model, and apologized for it
  in an error message.

## Decision

Identity is the model's **bytes**, not its location.

1. `IfcFile` carries `content_sha256`, the SHA-256 of the source bytes it was
   parsed from. `parse_ifc_file` hashes the file on disk; `parse_ifc` hashes
   the encoded text, so an in-memory model still has a stable identity.
2. Lowering records `source_sha256` in `module.meta`. It is identity.
3. `gat.ir.printer.PROVENANCE_META` names the meta keys that describe *where
   a module came from* rather than *what it is*. Those keys are kept for
   humans and excluded from the digest text. `source` is the only one today.
4. `module.meta` values are all `str`, so a module survives a snapshot or
   carrier round-trip as the same mapping it started as. A lowering scope is
   recorded as a comma-joined subject list rather than a Python list.
5. The IR dump header moves from `gat-ir v0` to `gat-ir v1`.

## What identity must still separate

Path-independence is not digest collapse. All three of these still produce
distinct digests, and `tests/test_world_identity.py` pins each one:

- different models,
- the same model with one quantity edited,
- the same file lowered under different `IfcLoweringScope` subject sets.

## Migration

`LEDGER_RUNTIME_CONTRACT` moves from `gat-world-v1` to `gat-world-v2`.

A ledger written by a v1 runtime carries digests a v2 runtime cannot
reproduce. Replay refuses it with `unsupported genesis runtime contract`
rather than re-interpreting it, which is the intended fail-closed outcome —
an old chain is not silently re-blessed under new identity rules.

There is no in-place migration for v1 ledgers, snapshots, or signed
carriers. Re-run the case against v2 to obtain a chain whose digests this
runtime can verify. Nothing about the belief, the observations, or the
dispositions changed; only what counts as the world's name.

## Non-goals

- Hashing normalized *semantic* content rather than source bytes. Two files
  that differ only in whitespace or instance numbering are, today,
  deliberately different worlds. A semantic identity is a larger change and
  would need its own version bump.
- Treating `source` as untrusted. It remains recorded, and remains useful;
  it simply does not vote on identity.

## What a carrier must still commit to

Excluding `source` from the *world* digest is right — a world is named by its
model's bytes, not by whoever loaded it — but it leaves a field travelling
inside every exported artifact that nothing checks. A stage could be edited to
name `/approved/CERTIFIED-final.ifc` as its source, or to carry a fabricated
"signed off by engineer" trace event, while every number it commits to stayed
intact.

So identity and provenance are committed separately. `gat.adapters.usd_io`
carries a fourth digest, `carrier_digest`, over `meta` in full and the
execution trace, and refuses a stage whose provenance was rewritten with a
message that distinguishes it from an edited quantity. A format that carries
provenance outside the world digest owes its reader the same treatment.
