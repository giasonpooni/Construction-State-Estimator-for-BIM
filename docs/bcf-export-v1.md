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

**Replay.** Topic GUIDs are `uuid5` over `(case_digest, check_id)` inside a fixed
namespace — derived, never generated. Zip entries use a fixed `date_time`. So
exporting the same disposition twice produces byte-identical output, and a BCF
file can be digested and replayed like anything else here. A different case
digest gives different GUIDs, so a live outcome never collides with a pin.

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
lenient reader accepts any order and a validating one does not. Pass
`world_identity` from `gat.adapters.portable_identity` to include the portable
digest, which is the identity another repository can actually check
(see `docs/world-identity-v1.md`).

Not yet included: viewpoints and snapshots. A `.bcfv` viewpoint needs a camera,
and a camera in this runtime is an RCI record or it does not exist.
