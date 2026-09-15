# World identity v2 — path-independent digests

Status: implemented. Runtime contract `gat-world-v3`.

> v3 keeps everything v2 decided and adds one thing v2 left out: each
> constraint's `tol`. See **What identity was still missing** below.

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
5. The IR dump header moves from `gat-ir v0` to `gat-ir v1`, and to
   `gat-ir v2` when constraint tolerances entered the text.

## What identity must still separate

Path-independence is not digest collapse. All three of these still produce
distinct digests, and `tests/test_world_identity.py` pins each one:

- different models,
- the same model with one quantity edited,
- the same file lowered under different `IfcLoweringScope` subject sets,
- the same model with one constraint tolerance rewritten (v3).

## What identity was still missing

Every constraint in the IR carries a `tol` — `NonNegative`, `LessEqual` and
`ExprEquals` all default it to `1e-9`. It is not a presentation detail. It is
the entire quantitative content of `CONS-01`, `CONS-02` and `CONS-03`: the
invariants ask whether a mean clears a bound *by more than `tol`*, so
rewriting `tol` from `1e-09` to `1e9` is rewriting "this bound holds" into
"no bound can be violated".

`print_module` emitted a constraint's variables and its shape and stopped.
So the two worlds printed the same bytes and carried the same module, world
and configuration digest.

The snapshot envelope does not close this. Its `integrity.digest` is an
unkeyed SHA-256 of the document — it detects corruption, not an adversary —
and `payload.source_module_digest` is checked against a recomputed
`module.digest()`, which was blind to `tol` in exactly the same way.
Measured on `gat/demo/model.ifc`: rewriting all 74 tolerances and
recomputing the envelope digest produced a state that loads clean, reports
world digest `793474ab…` — byte-identical to the honest one — and then
**accepts** a door driven a metre past its opening, where the honest world
refuses the same change with `VerificationError: CONS-02`. Anything bound to
a world digest, including an evidence receipt's `result_world_digest`, was
bound to both worlds at once.

So `tol` is now printed, unconditionally, including when it equals the
dataclass default. Omitting the default would leave every existing digest
unchanged and would still be lossless *today*, but it would tie identity to
a constant in `gat.ir.core`: change that default and two modules written
under the two values collide. The cost of saying it every time is one short
suffix per constraint line.

With it stated, the restamping attack still "works" in the only sense left
to it — an attacker can write an internally consistent document with loose
tolerances — but that document is now a **different world**, with a
different digest, and nothing bound to the honest one covers it. Which is
what identity is for.

## Migration

`LEDGER_RUNTIME_CONTRACT` moves `gat-world-v1` → `gat-world-v2` →
`gat-world-v3`.

A ledger written by an older runtime carries digests this one cannot
reproduce. Replay refuses it with `unsupported genesis runtime contract`
rather than re-interpreting it, which is the intended fail-closed outcome —
an old chain is not silently re-blessed under new identity rules.

`gat.state_snapshot.RUNTIME_CONTRACT` names the same contract and moves with
it. It had been left at `gat-world-v1` through the whole v2 change, so a
snapshot written under the superseded identity rules cleared that guard and
failed later at the digest comparison instead — reported as `reconstructed
module digest differs from source`, which describes a corrupt document rather
than an obsolete one. Fail-closed either way; it named the wrong cause.
`tests/test_world_identity.py` now pins the two strings equal.

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

## What that provenance discloses

The consequence, stated so it is a known property rather than a discovery:
**an exported artifact contains the exporter's local paths.** `meta["source"]`
is the path the model was loaded from, verbatim, and every `export`, `resume`
and `import` trace event records the path it was given. Both travel inside
every snapshot and USD carrier, and both are integrity-protected, which means
they are preserved exactly and not sanitised.

Measured: loading the same model from `/tmp/clientname_x/copy.ifc` yields a
world digest identical to loading it from `gat/demo/model.ifc` — identity is
path-independent as designed — while the exported snapshot names the temp
directory in `payload.module.meta.source` and in its trace. In a real project
that reads as a client name and a directory layout.

This is deliberate and it is a trade. The path is the honest record of where
the model came from, it is useful to the operator who wrote it, and
`carrier_digest` means nobody can rewrite it to claim a different provenance.
It is also not verifiable by a reader — a path on someone else's disk cannot
be checked and may not exist — so it buys the recipient nothing that the
digests do not already give them.

Two things follow. An operator handing an artifact to a counterparty should
know it carries these paths. And if a project would rather it did not, the
change is to record basenames at every `trace.add` site and in `meta`, which
is a carrier-format change: it moves what `carrier_digest` commits to, so it
needs a format version bump, not a patch. Trimming only the trace would
achieve nothing while making the two disagree.
