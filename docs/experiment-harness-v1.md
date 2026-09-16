# Experiment harness v1

Satellite. Status: in-development. Not a kernel change.

The harness sequences independently owned tools by binding their
record digests. It does not import those tools. It does not prove.

```text
RCI record digest
Torus report digest
GAT disposition pin
        -> harness bundle
            -> optional later SP1 guest on one arithmetic claim
```

## What a user runs

In this repository:

```bash
python -m gat.demo.beam_assurance out/beam
python -m gat.demo.experiment_harness \
  --disposition validation/beam-b1-disposition-v1.json \
  -o out/harness-bundle.json
```

To attach records produced by the other repos (clone them separately;
do not submodule):

```bash
python -m gat.demo.experiment_harness \
  --disposition validation/beam-b1-disposition-v1.json \
  --commit path/to/rci-evidence-commitment.json \
  --commit path/to/torus-report-commitment.json \
  -o out/harness-bundle.json
```

## What the bundle is allowed to say

- These files existed and their payloads hashed to these hex strings.
- Beam-B1 prior/revised verdicts are whatever the disposition pin says.
- SP1 was not invoked, or is `BACKEND_REQUIRED`.

## What it is forbidden to say

- The millimetre is Fy.
- A3 or J Sigma J^T holds because a sensor ticked.
- The torus length and the beam verdict share a proof.
- The guest verified covariance.

JSPT stays out of the guest. RCI never proves. Torus lengths are
already replayable algebra.
