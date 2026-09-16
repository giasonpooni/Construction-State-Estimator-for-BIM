# Point-to-IfcGuid bind v1

Satellite. See [inspectability-index-v1.md](inspectability-index-v1.md)
and [kernel-v1.md](kernel-v1.md).

## Job

Name one layout point as the same object as one IFC entity. Close the
`bind.point_to_guid` hole on an inspectability index.

This is not an observation. It does not condition belief. It does
not make a DWG layer into `SCAN_GMM`.

## Schema

```json
{
  "schema": "cse-point-bind-v1",
  "claim_scope": "record-integrity-only",
  "payload": {
    "point_id": "P-204",
    "ifc_class": "IfcOpeningElement",
    "global_id": "GATOPN0000000000000200",
    "name": "Opening-1",
    "space_id": "space:ifc:GATSPC0000000000000300",
    "frame_id": null
  },
  "digest": "sha256 of the payload"
}
```

`global_id` is the IFC `GlobalId`. Display names (`Opening-1`, `Office-A`)
are refused. `frame_id` may name a survey setup; it is not a JSPT chart.

## Call path

```
layout point P-204
        |
        v
gat.harness.point_bind.bind_point
        |
        v
inspectability fold (--bind)
        |
        v
later ObserveQuantity / ObserveLinearized on that Guid
```

## Non-claims

- Not as-built evidence.
- Not a station resection.
- Not an occupancy permit.
- Binding P-204 does not change Beam-B1 or opening-fit replay.
