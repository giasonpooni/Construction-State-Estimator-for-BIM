# BCF export v1

```text
AcceptanceOutcome.to_dict()   ->   BCF 2.1 .bcfzip   ->   Solibri / Navisworks /
                                                          BIMcollab / Revit
```

```console
gat bcf validation/opening-fit-disposition-v1.json -o opening-fit.bcfzip
```

## Why this exists

A disposition and a BCF topic are nearly the same object already. An
`evidence_request` names a check, a target, an action and a reason; a BCF topic
has a title, a status and a description. BCF is how the construction industry
actually exchanges "this needs attention", so exporting one gives a disposition
a reader who did not produce it.

That matters beyond convenience. Every defect found in this runtime's artifacts
so far shared one cause: each artifact had exactly one producer and no consumer,
so nothing read it back. `validation/opening-fit-disposition-v1.json` was read
by nothing at all. It is now exportable, which makes it consumable.

## What the export keeps that a generic BCF writer would drop

**Replay.** Topic GUIDs are `uuid5` over `(key, check_id)` inside a fixed
namespace — derived, never generated. Zip entries use a fixed `date_time`. So
exporting the same disposition twice produces byte-identical output, and a BCF
file can be digested and replayed like anything else here.

**Portability, and which identity a GUID rests on.** There are two keys, and every
topic says which one it used.

| `world_identity` passed | key | label | what it means |
|---|---|---|---|
| a `cse-world-identity-v1` record | `portable_topic_key(document, portable_digest)` | `identity:portable` | the same case on another processor is the same topic |
| nothing | `case_digest` | `identity:machine-local` | the same case elsewhere may be a *different* topic |

`case_digest` embeds `world_digest`, and `World.digest()` hashes
`full.sigma.tobytes()`, which BLAS sums in a CPU-dependent order. So the
machine-local key is the defect described in `docs/digest-portability-v1.md`: two
engineers exporting the same case on different hardware got different topics, and
the receiving tool could not tell they were the same issue. It is the one defect of
that kind visible without opening hex.

The portable key is `sha256` over the portable digest, `case_id`, `workflow`,
`subject`, `policy_id`, and each check's `(check_id, kind)` — sorted, so check
order does not enter it. What it deliberately **excludes** is every float-derived
field: `verdict`, `confidence`, `p_satisfies_lower`, `p_satisfies_upper`. A verdict
is a float comparison, so near a threshold it is precisely what does not survive a
change of processor, and putting it in the key would put the defect back.

Two consequences, both written into the body of every portable topic rather than
left here:

- A topic **keeps its GUID across re-exports while its `TopicStatus` moves**. This
  is what tracking a topic in Solibri or BIMcollab needs — a reviewer wants the
  same issue to stay the same issue as its state changes.
- Two beliefs differing only in the **13th significant digit** share a portable
  digest, and therefore share a topic. That is the price of portability. It is the
  right trade for BCF and the wrong one for restart identity, which is why
  `portable_world_digest` appears on no reload path.

The identity record must name *this* world: its `world_digest` has to equal the
disposition's, or the export is refused. Without that check, handing over any
identity file would relabel these topics portable while the number came from a
different run — which looks correct and is not. `gat bcf --world-identity` with a
mismatched record exits 2 rather than falling back quietly.

The CLI reads the record from a file and does not recompute it from the model.
Re-lowering the IFC would give the **prior** belief, while the disposition was
computed on a conditioned one, so a digest derived that way would be portable and
wrong.

```
gat bcf validation/opening-fit-disposition-v1.json -o out.bcfzip \
    --world-identity identity.json
```

**No invented time.** BCF requires `CreationDate`. `gat.adapters.bcf` refuses to
supply one: the caller passes it. The CLI defaults it to now in UTC, because the
CLI is the human boundary and that is where a timestamp legitimately enters the
record — the same place evidence enters it. The library never reads a clock.

**Claim scope.** A topic is a request, never a stamp. Every topic body carries
the disposition, `may_authorize`, the `world_digest` and `case_digest` it was
computed on, the check's verdict and margins, and an explicit sentence saying it
is not an approval. `claim_scope:record-integrity-only` is a topic label so it
survives into whatever tool opens the file. Authorization is still a human
`ApprovalRecord`.

**Refusal over an empty file.** An `ACCEPT` disposition raises no evidence
request, so there is nothing for a reviewer to do. Rather than write an empty
archive — which would tell a reviewer there is work — the export refuses, and
`gat bcf` exits 2.

## Schema notes

BCF 2.1. `Topic` children are emitted in the schema's declared sequence —
`Title, Priority, Labels*, CreationDate, CreationAuthor, Description` — because a
lenient reader accepts any order and a validating one does not. The
`world_identity` record comes from `gat.adapters.portable_identity`; its portable
digest is the identity another repository can actually check
(see `docs/world-identity-v1.md`).

Not yet included: viewpoints and snapshots. A `.bcfv` viewpoint needs a camera,
and a camera in this runtime is an RCI record or it does not exist.
