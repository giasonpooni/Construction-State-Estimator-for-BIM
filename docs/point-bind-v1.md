# Point-to-IfcGuid bind v1

Satellite. See [inspectability-index-v1.md](inspectability-index-v1.md)
and [kernel-v1.md](kernel-v1.md).

## Job

Name one layout point as the same object as one IFC entity. Close the
`bind.point_to_guid` hole on an inspectability index.

This is not an observation. It does not condition belief. It does
not make a DWG layer into `SCAN_GMM`.

`frame_id`, `epoch`, `sigma`, `sigma_unit`, and `sigma_reason` are required.
A bind without uncertainty is refused. Coordinates without a GlobalId are
not a bind. Mesh proximity is not a bind. Display names are refused.
`frame_id` may name a survey setup; it is not a JSPT chart.

## Non-claims

- Not as-built evidence.
- Not a station resection.
- Not an occupancy permit.
- Binding P-204 does not change Beam-B1 or opening-fit replay.
