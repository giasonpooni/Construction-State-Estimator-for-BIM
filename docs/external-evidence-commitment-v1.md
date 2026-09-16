# External evidence commitment v1

Satellite. Kernel dispositions do not change because a digest arrived.

## Job

Bind a content-addressed record from another Notation Systems repo so it
can later appear in `evidence_commitments` on a computation-proof
manifest. Do not condition belief. Do not run SP1. Do not treat the
record as a mill certificate or as AISC F2-1 input.

## Allowed schemas

- `rci-evidence-commitment-v1` — instrument observation payload
- `torus-report-commitment-v1` — torus experiment record payload

Claim scope is frozen: `record-integrity-only`.

Encoding is the GAT canonical digest: sorted-key compact JSON, UTF-8,
SHA-256 hex.

## Call path

```
RCI / torus produce digest
        |
        v
gat.adapters.external_commitment.bind_external_commitment
        |
        v
hex digest available for a later manifest
        |
        v
optional SP1 beam guest only if that digest is actually an
evidence_commitment on an accepted Beam-B1 transition
```

A displacement millimetre is not `YieldStrengthMPa`. The adapter refuses
that substitution.

## Non-claims

Binding a digest does not prove the sensor, the torus length, the
Gaussian update, or that the building is safe. SP1 remains the existing
beam guest, invoked only by `gat.demo.beam_sp1`.
