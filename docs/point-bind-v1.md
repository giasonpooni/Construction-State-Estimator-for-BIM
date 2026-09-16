# Point-to-IfcGuid bind v1

Satellite. See inspectability-index and kernel-v1.

## Job

Name one layout point as the same object as one IFC entity.

A **survey bind** (`gat.geometry.survey_bind`) additionally requires the
measurement constitution:

`project_space_id`, `chart_id`, `installation_id` (HI / prism height),
`session_id`, `sequence`, raw tuple.

`frame_id` is a setup name. It is not a JSPT chart. Covariance on the
bind is `gat.adapters.jspt.chart_covariance`.

Dropped or unavailable ticks stay in the pack. They do not bind.
Empty raw is refused (no last-value fill). Binding does not condition
belief and does not change Beam-B1 or opening-fit replay.

## Non-claims

- Not as-built evidence.
- Not a station resection.
- Not an occupancy permit.
- Not a new IFC class for HI.
