# ReadoutSpec v1 and the CSE Console

`gat console` composes the human surfaces of this repository into one
offline scientific instrument: a **specimen** whose identity is always
visible, a **function selector** of six readouts, and a **reading** of what
the instrument currently makes of what is loaded. This document is the
contract behind it: what a readout is allowed to claim, how it declares
itself, how readouts share one identity, and what the instrument declares it
does not measure. The code is `gat/workbench.py`; the design language it
inherits is `docs/design-language-v1.md`.

## What changed from v1 of this document

The previous shell was called the Notation Workbench and organised itself
around a projection triad borrowed from a geospatial platform: kepler.gl for
analytical geography, CesiumJS for geodetic reality, Three.js for structure.
Two of its eight modes, MAP and GLOBE, were seats reserved for libraries
this instrument does not contain and could never fill offline — permanently
unavailable positions on the selector.

Declaring what you cannot measure is right. Doing it as dead knobs is not: a
selector with positions that never turn teaches an operator to distrust the
ones that do, and it gave the instrument another product's silhouette. The
limits are now a standing declaration (`NOT_MEASURED`, rendered under *this
instrument does not measure*), and every position on the selector reads
something.

## The requirement

> Every representation identifies its source, its transformation, its
> supported meaning, and its information loss.

A building element appears as an IFC entity, as scan geometry, as a
computational variable, and as a selected object on a screen. A visually
convincing correspondence between those is not evidence that they describe
the same subject at compatible times and in compatible coordinate frames.
So every readout carries a `ReadoutSpec` that states, verbatim on the page,
what it reads and what it drops.

## The six readouts

| # | Readout | Reads | Question | Surface class |
|---|---|---|---|---|
| 1 | FIELD | the belief, rendered | How is it constituted? | instrument |
| 2 | RELATIONS | what relates to what | What relates to what, on whose authority? | instrument |
| 3 | BELIEF | mu and sigma per quantity | What is believed, and how surely? | instrument |
| 4 | LOG | what happened, in order | What happened, in what order, did the chain hold? | report |
| 5 | DECISION | what was decided, and why | What was decided, on what evidence, what is missing? | report |
| 6 | INTAKE | what this file can offer | What can this corpus represent, and what not? | report |

The order is the one an operator works through: what is there, how it
relates, what is believed, what was done, what was decided, and what this
file could offer in the first place. Positions are numbered 1–6 on the
selector and on the keyboard.

## What this instrument does not measure

Stated once, in the footer, rather than as unfillable readouts:

| Quantity | Why not |
|---|---|
| geographic position | No IfcSite placement, IfcMapConversion or coordinate reference system reaches the IR. Nothing here can be put on a map without inventing a position, and an invented position is visual adjacency presented as evidence. |
| geodetic reality | No geodetic datum is lowered, and terrain or imagery would be fetched over the network. This instrument is self-contained by construction. |
| time | A world is one belief state. LOG orders recorded transitions by sequence; FIELD's realizations are draws from one posterior. Nothing here is a time series. |

Whether those semantics are ever lowered is an engine decision. This
document names what would have to exist first — a frame with a CRS, a time
with a survey epoch, and for anything networked, a *connected instrument*
surface class this release does not define.

## ReadoutSpec fields (`gat-readout-spec-v1`)

| Field | Meaning |
|---|---|
| `readout` | one of the six names above |
| `instrument` | what this readout reads with |
| `question` | the one question the readout answers |
| `surface_class` | `report` (script-free, inert), `instrument` (self-contained, offline, inline scripts), or `connected instrument` (would fetch external resources — **not yet defined** as a class, and nothing here claims it) |
| `source` | the engine artifact the projection reads |
| `transformation` | what the mode does to its source to draw it |
| `meaning` | what the picture may be read as |
| `loss` | what the projection drops or approximates |
| `identity` | how subjects are named in this mode (`EntityId`, `VarId`, request id, event hash, world digest) |
| `frame` | the coordinate frame or unit system, or `none` |
| `time` | which state in time the mode shows (one world digest, ledger sequence, file version) |
| `availability` | `available` or `empty` (below) |
| `reason` | for `empty`: why, and which flag or artifact fills the readout |
| `mutates_specimen` | always `false` |

The specs are embedded in the page twice: as a disclosure strip at the top
of each readout, and in full as JSON in the footer.

## Availability

Two states, and every readout on the selector has a source it can read.

* **available** — the readout has a source and renders it.
* **empty** — the readout exists for this specimen, but nothing is bound to
  it in this document (no `--ledger`, no `--decision`, `--no-audit`). The
  panel says exactly which flag or artifact fills it, and the selector shows
  the position unlit. It is never hidden: an operator should be able to see
  that a reading is missing, not discover it by its absence.

There is no third state. A readout that could never be filled is not a
readout; it belongs in *what this instrument does not measure*.

## Identity across readouts

One selection is shared by every readout. It is an `EntityId`
(`IfcClass:GlobalId`) — never a name, never a position, never an index into
a readout's own arrays. The identity strip shows the name *and* the id.

* RELATIONS nodes, BELIEF list entries and FIELD elements all carry the
  `EntityId`; selecting in any one selects in all.
* The page and the embedded viewer share one world digest, and every
  message between them carries it; a message from a different world is
  ignored, not reconciled.
* Report panels (LOG, DECISION, INTAKE) mark exact-name mentions of
  the selected entity so the reader sees where the identity appears in the
  evidence. Because `gat-headless` responses name subjects by entity *name*,
  a name shared by several entities is an ambiguous identity: nothing is
  marked and the strip says so. Carrying `EntityId`s in responses would
  remove the ambiguity — an engine contract, noted here rather than worked
  around.
* The URL hash carries `#READOUT/EntityId`, so a view can be shared and
  restored by identity.

## Message contract (`gat-console-message-v1`)

The FIELD viewer runs in a sandboxed `srcdoc` frame (`allow-scripts`
only; opaque origin). Messages are the only channel between it and the
page; there is no DOM access in either direction.

| Direction | `kind` | Fields | Meaning |
|---|---|---|---|
| viewer → page | `ready` | `world_digest` | the frame has booted; the page replays its current selection |
| viewer → page | `selection` | `world_digest`, `entity` or `null`, `name` | the user selected (or cleared) an element in the viewer |
| page → viewer | `select` | `world_digest`, `entity` or `null` | select (or clear) this identity in the viewer, quietly |

Every message carries `format: "gat-console-message-v1"`. Receivers check
the format, the source window, and the world digest before acting, and
drop anything else silently. No message mutates state on either side:
selection is a view property, not a model property.

## Exploded views are reading offsets

FIELD can pull the asset apart. The displacement of each piece is
derived from the relationship graph (radially from the plan centroid; an
opening with the wall it voids, a door with the opening it fills, one step
further each; spaces lifted), scaled by a slider, and drawn with leader
lines back to the assembled place. It is declared in the readout's
`transformation` and `loss`, stated on the inspection card ("drawn N m from
its place for reading; not a position"), and never written anywhere: the
scene, the world and the carrier are untouched. The same rule would hold
for an OpenUSD expression of the exploded layout — a variant or
time-sampled transforms over the derived view, never over `/GAT/State`.

Audit statuses ride along per piece, bound by GlobalId from a
`gat-ifc-audit-v1` document and refused if the vocabulary is unknown. A
piece the corpus could not fully represent is outlined in its status
colour; its fill keeps the identity hue, because an audit status describes
the corpus, not a verdict on the asset.

## Rules that hold in every readout

1. **A readout never mutates its specimen.** The console renders and
   re-checks; it never writes. Fail-closed rules from the report layer
   apply unchanged: a decision from another world is refused, a tampered
   ledger is refused before drawing, an audit whose readiness contradicts
   its stages is refused.
2. **Identity survives representation.** The same `EntityId` and the same
   world digest name the same thing in every readout and across the frame
   boundary.
3. **Visual adjacency is never evidence.** The RELATIONS layout is a reading
   order by IFC class rank and says so on the panel; distances on the
   canvas carry no information. Nothing on any panel proposes anything to
   the corpus.

## What the frontend contributes to industrial gates

Of the five readiness gates — representation fidelity, computational
validity, uncertainty calibration, operational reliability, workflow
validation — the frontend can only help with the first and the last, and
only partly:

* *Representation fidelity*: the identity contract above is tested
  (`tests/test_workbench.py::StatePayloadTests::test_identity_survives_representation`),
  and every `ReadoutSpec` declares its loss, frame and time so that a
  reader can tell whether two representations are even comparable.
* *Workflow validation*: the instrument lets a practitioner see the
  decision at the spot it was decided (FIELD), the evidence it rests on
  and the evidence still requested (DECISION), the history (LOG) and the
  corpus limits (INTAKE) without leaving one file. Whether people use
  it correctly is a field question this document cannot answer.

## Non-goals

The console adds no judgement of its own: no derived scores, no aggregated
traffic lights, no inferred correspondences between readouts. It does not
fetch anything. It does not reserve positions for instruments it does not
have: what it cannot measure is declared, not mocked up.
