# Inspectability index v1

Satellite. Does not change kernel dispositions, world digests, or replay
on the acceptance / beam / RFI slice. See [kernel-v1.md](kernel-v1.md).

## Job

Give a construction team one handle for the question they actually stall
on:

> Is this space ready to *present* to an inspector, and if not, which
> evidence is still unnamed?

The handle is an id, not a stamp.

```text
project_id / building_id / space_id
        →
inspectability record
        →
index of cited artifacts + open REQUEST_EVIDENCE items
        →
human inspector (unchanged)
```

`ACCEPT` on a bound acceptance case still means only what
[workflow-deployment-v1.md](workflow-deployment-v1.md) says: the case may
be presented for authorization. It is not an `ApprovalRecord` and not an
occupancy permit.

## Identity and binding

Variable identity in the ledger is already structural
(`ifc_class`, `global_id`, `quantity`). Teams do not stall on that math.
They stall because a layout CSV, an IFC revision, an RFI, and a scan live
under four different nicknames for the same room.

A shared `space_id` is the cross-reference key for work already labored
for. It is not a reason to own a total station or a scan-to-BIM pipeline.
Foreign artifacts enter only as
[external evidence commitments](external-evidence-commitment-v1.md):
content-addressed, `record-integrity-only`, forbidden from becoming
`YieldStrengthMPa`.

## Record

```json
{
  "format": "cse-inspectability-index-v1",
  "project_id": "proj:example-hall",
  "building_id": "bldg:hall-a",
  "space_id": "space:ifc:3Abc...",
  "space_ref": {
    "ifc_class": "IfcSpace",
    "global_id": "3Abc...",
    "name": "L3-Office-A"
  },
  "inspectability": "REQUEST_EVIDENCE",
  "open_requests": [
    {
      "code": "bind.point_to_guid",
      "asks_for": "layout point P-204 bound to an IfcGuid"
    }
  ],
  "cited": [],
  "non_claims": [
    "not an occupancy permit",
    "not a replacement for a human inspector",
    "pace thesis is not a measured result"
  ]
}
```

`space_id` prefers the IFC `GlobalId` of an `IfcSpace` when one exists.
If the model has no space entity, the index stays `REQUEST_EVIDENCE` with
code `identity.space`. Do not invent a room from a display string.

Allowed `inspectability` values are the existing decision vocabulary:

| Value | Meaning for this index |
|---|---|
| `REQUEST_EVIDENCE` | Named holes remain. Package is not presentable. |
| `REJECT` | At least one bound case on this space is `VIOLATED`. |
| `ACCEPT` | Bound cases on this space are presentable. Still not a stamp. |

The index is a fold over already-computed case dispositions plus the
open-request list. It does not run a fifth workflow and it does not
recompute Beam-B1.

## What may be cited

Each `cited` entry is a digest already legal for the harness or the
external-commitment adapter:

- IFC world / case receipt already in the execution ledger
- `rci-evidence-commitment-v1`
- `torus-report-commitment-v1`

A citation does not condition belief. A later `ObserveQuantity` or
`ObserveLinearized` transition is the only path from a field file into
the Gaussian state, and that path remains the kernel.
