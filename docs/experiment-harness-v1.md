# Experiment harness v1

Satellite. Status: in-development. Not a kernel change.

The harness names a project space and binds independently owned tool
records by digest. BIM spaces are the first names. The same bundle is the
maintained-evidence packet for a line, vessel, or yard when those
declarations exist. See [domain-v1.md](domain-v1.md).

It does not import those tools. It does not prove.

```text
RCI record digest
Torus report digest
GAT disposition pin
        -> harness bundle (project_space_id + merkle root)
            -> optional later SP1 guest on one arithmetic claim

on-disk case receipts + optional binds + cited digests
        -> inspectability index (read-only fold)
```

## What a user runs

```bash
python -m gat.demo.beam_assurance out/beam
python -m gat.demo.experiment_harness --demo -o out/harness-bundle.json
```

To attach live records from the other clones:

```bash
python -m gat.demo.experiment_harness \
  --disposition validation/beam-b1-disposition-v1.json \
  --commit path/to/rci-evidence-commitment.json \
  --commit path/to/torus-report-commitment.json \
  -o out/harness-bundle.json
```

Fold receipts already on disk into an inspectability index:

```bash
python -m gat.demo.experiment_harness --inspectability --demo \
  -o out/inspectability.json
```

See [inspectability-index-v1.md](inspectability-index-v1.md).

## What the bundle is allowed to say

- This packet belongs to one `project_space_id`.
- These files hashed to these hex strings; the Merkle root commits that set.
- Beam-B1 prior/revised verdicts are whatever the disposition pin says.
- SP1 was not invoked, or is `BACKEND_REQUIRED`.

## What it is forbidden to say

- The millimetre is Fy, or a lot code, or a cold-store temperature.
- A3 holds because a sensor ticked.
- The guest verified covariance.
- The index is an occupancy permit, a CFIA stamp, or a human inspector.
- OpenUSD orbiting the camera changed the belief.

JSPT stays out of the guest. RCI never proves. Torus lengths are
already replayable algebra.
