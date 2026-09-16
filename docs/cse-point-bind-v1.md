# Point-to-IfcGuid bind v1

Satellite. A bind is a named identity claim. It is not a measurement
and it is not a harness digest.

## Record

See [validation/cse-point-bind-v1.json](../validation/cse-point-bind-v1.json).

Required fields:

- `schema`: `cse-point-bind-v1`
- `point_id`: crew/layout point name
- `global_id`: IFC GlobalId of the target entity
- `ifc_class`: IFC class of that entity

## Rules

- `gat.harness` `--commit` files never satisfy `bind.point_to_guid`.
- A JSON object that only says `schema: cse-point-bind-v1` is not a bind.
- A paragraph from an MCP agent is not a bind.
- Binding Opening-1 does not change Beam-B1 or shrink `Sigma`.
