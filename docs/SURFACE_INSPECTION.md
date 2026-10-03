# BIM-linked surface inspection planning

State Estimator for BIM is a **Notation Systems project**. Its role in this
workflow is to bind a planned investigation to the current BIM world, not to
replace the Curved Surface Runtime or turn a computed path into an observation.

## Implemented path

The adapter is `gat/adapters/surface_inspection.py`. It adds three explicit calls:

| Call | Work performed | Claim made |
|---|---|---|
| `prepare_request` | Resolve a typed IFC identity and length quantity in the actual world; commit supplied records and policy. | Prepared, not calculated. |
| `inspect_report` | Rebuild the expected request; validate the returned record set, schema, restrictions, and digest. | Bound, unverified plan. |
| `replay_report` | Perform inspection, then explicitly invoke the optional companion's verifier. | Bound plan with matching record-postprocessing replay. |

No call applies an observation, updates the world, appends a ledger event,
changes an acceptance disposition, or dispatches an equipment command. The
companion is imported only by explicit replay. The core dependency list does
not become a compulsory multi-engine installation.

## Request and result

`surface-inspection-request-v1` binds IFC class, GlobalId, quantity, world digest,
spatial-frame identifier, mapping-declaration digest, metre/radian units, tolerance,
limits, and full candidate-record commitments. A display label is not a GlobalId.
A three-dimensional BIM frame and a transverse Jacobi frame are different things;
this interface records their association rather than inventing a transformation.
The caller must retain the mapping declaration separately. Its digest is a binding,
not evidence that geometry has been registered or physically measured.

The companion's `surface-inspection-study-v1` contains the original request,
complete transfer records, metrics, failed limits, deterministic candidate ranking,
runtime versions, and report digest. It explicitly carries no authorization,
physical validation, or cryptographic verification. The identifiers of the existing
CSE world, dispositions, and geodesic records are unchanged.

Fresh replay recomputes the assessment from the stored transfer records. It does
not rerun the surface/geodesic integration or establish the validity of an external
surface reconstruction. Replay gets a new verification occurrence; the content
identity of an unchanged report stays the same. A record's own first-order validity
claim is reported, not converted into physical validation. In this implementation
ranking orders sampled-limit satisfaction, amplification score, and candidate ID;
it is not a device-trajectory optimizer or a complete suitability decision.

## Reproduce the example

Install this branch and the paired inspection extension of Curved Surface Runtime
in the same Python 3.12+ environment. Keep the two repositories separate. From the
BIM repository:

```sh
python -m gat.demo.surface_inspection out/inspection
```

This uses the shipped IFC and two **synthetic plane-path fixtures**, not an
IFC-to-surface extractor. The initial lateral/heading tolerances are 0.001 m and
0.001 rad. At lengths 2 m and 6 m, the plane reference predicts maximum cross-track
bounds of 0.003 m and 0.007 m. The declared cross-track limit is 0.004 m, so only
the short candidate meets that sampled limit. Both candidates remain in the result.

The example retains the mapping, request, records, report, identity-inspection
receipt, replay receipt, and summary in a new directory. The world remains
unchanged and the original as-built case still returns `REQUEST_EVIDENCE`.
Output creation refuses an existing directory; multi-file publication is not a
power-loss-safe transaction.

## Verification boundaries

`tests/test_surface_inspection.py` covers typed identity, missing quantities,
unit mismatch, stale worlds, detached inputs, changed commitments, duplicate
candidate results, forbidden claims, cross-serializer agreement, and fresh
numerical replay. A consistently rehashed numerical lie can pass integrity-only
inspection, remains explicitly unverified there, and is rejected by fresh replay.

The paired workflow runs the real companion, not a fake provider. Set
`CSE_REQUIRE_INSPECTION_PROVIDER=1` when running the focused suite to make a missing
companion an error rather than an optional skip. Existing CSE unit tests, acceptance
examples, beam checks, proof code, and licenses are preserved. The existing native
SP1 tests retain their separate requirements.

## Next qualified extensions

A measured trial needs independently checked spatial registration, actual calibrated
observations, uncertainty including shared terms, and a declared comparison protocol.
An IFC solid-to-surface extractor, collision checker, scanner driver, new SP1 guest,
and automatic Notations terminal registration are not implemented by this seam.
These should extend their current owners through versioned interfaces, not duplicate
the world, solver, or evidence-admission model here.
