# Geometry authority v1

Status: implemented on the acceptance boundary.

A probabilistic clearance or capacity number is not enough to close a case.
The check must also declare what geometric or quantity support it used.

## Codes

| Code | Meaning | Can close as-built clearance? | Can close quantity fit / beam capacity? |
|---|---|---|---|
| `SWEPT_SOLID` | IFC swept-solid body with derived section properties | yes | yes |
| `SCAN_GMM` | Calibrated scan likelihood bound to this world | yes | yes |
| `QUANTITY_ONLY` | IFC dimensional quantities / placements, no solid | no | yes |
| `LENGTH_ONLY` | Beam axis length only; no section authority | no | no |
| `GAUSSIAN_PROXY` | Oriented-box Gaussianization; openings not subtracted | no | no |
| `DECLARED_PROPERTY` | Section property asserted in a property set, uncorroborated | no | no |
| `DECLARED_CORROBORATED` | The same declaration, bracketed by the model's own solid | no | yes |
| `INSUFFICIENT` | Support missing or blocked | no | no |

## Policy

`AcceptancePolicy.require_sufficient_geometry_for_accept` defaults to true.

- Clearance accepts only `SWEPT_SOLID` or `SCAN_GMM`.
- Minimum / difference checks accept `QUANTITY_ONLY`, `SWEPT_SOLID`, or
  `SCAN_GMM`.
- A verified `calibrated-scan-clearance-likelihood` receipt covering a check
  upgrades that check to `SCAN_GMM` for the policy decision. The stored check
  still reports the authority it was constructed with.
- Insufficient geometry yields `REQUEST_EVIDENCE`, never `ACCEPT`.
- `REJECT` still wins if any check is `VIOLATED`.

v0 clearance from `assess_clearance` is constructed as `GAUSSIAN_PROXY`.
That is intentional. A green Gaussian overlap is not an as-built clearance
acceptance.

## What `SCAN_GMM` now has to survive

A calibrated scan likelihood is the strongest authority this runtime issues,
so the quantities that qualify it are gates, not annotations:

| Gate | Refuses | Measured on the demo wall |
|---|---|---|
| basin separation | a pose the scan does not determine | yaw 0 and yaw 180 tie within 6.5e-05 nats/point, 10.2 m apart |
| `max_yaw_sigma` / `max_translation_sigma` | a pose too few returns can locate | a 10-point capture cleared fit and margin with the pose 10.9 deg and 865 mm out, reading 0.77 deg of yaw sigma |
| `registration.accepted` | a pose that failed its own fit gate | was computed and never read downstream |
| `min_face_coverage` | returns that span a face without sampling it | two 4 mm clusters read 0.07 against a sweep's 0.35 |
| `max_residual_sigma_ratio` | a face whose scatter is shape, not noise | a 45 mm bulge scatters 20.7 mm rms, past 15.0 mm |

The pose-uncertainty pair is there because the two gates above it are both
*means over points*. A dozen returns can separate two basins by 2.2
nats/point and fit them well and still leave the pose a metre out; there are
simply not enough of them for either number to mean what it says. The
information matrix is the one quantity in the registration that counts
evidence rather than averaging it, and it was computed, reported, and never
asked. It is added to basin separation rather than replacing it: the matrix
is local curvature at one optimum and cannot see a rival basin -- on the
ambiguous single wall it reads a comfortable 0.20 deg -- while the margin
cannot see how few points it was measured over. Both readings are lower
bounds on the uncertainty, so passing is the weaker claim and failing is
decisive.

The last one also states the premise of the noise model: dividing the face
residual by the return count is the standard error of a mean, which is the
right formula only while the residual is independent noise. A face that
fails the gate is not a support plane, and scanning it harder does not make
its mean one.

## What a surface capture does that a drawn scan does not

Every scan this runtime was measured against until now came from
`synthesize_scan`, which samples **all six faces** of every element box:
both sides of every wall, the faces buried between adjacent elements, and
the outside of the exterior. That is a complete, symmetric shell of the
model, and it is the right instrument for testing the estimator. It is also
something no scanner can produce — a scanner sees the faces pointing at it.

Matching a one-sided shell against a model built from a two-sided one
offsets the fit by about half the element thickness. Measured on a
four-station simulated survey of the shipped model, whose exterior walls are
0.30 m: the pose lands 0.150 m out while `pose_sigma` reports 6 mm, and the
registration accepts it. Sampling every face instead, through the same
estimator and the same gates, lands at 2.8 mm.

That mechanism is asserted rather than assumed, because the likelier-sounding
explanations are all false here and were each measured:

| Suspected cause | Test | Result |
|---|---|---|
| too little coverage | 18 stations, full sphere | 158 mm — no better than 4 |
| stray returns | +300 uniform outliers | moves it 1.7 mm |
| mixed pixels at depth edges | switched off | within a few mm |
| clutter, range-dependent noise | switched off | within a few mm |
| the wrong basin won | inspect the converged poses | winner is correct to 0.03°, runner-up a quadrant away |

What is left is which faces exist to be measured at all, and no number of
stations inside a building can see the outside of its exterior wall.

Nothing downstream is fooled, because nothing downstream trusts it. The
independent pose is what the measurement is taken at; the fit is used for
association, and the agreement between the two is checked. That check
refuses this capture at m² of 221 against a gate of 16.

It is not the only thing that refuses it, and the chain does not rest on any
one gate:

| Reduction | Points | Pose error | What refuses it |
|---|---|---|---|
| 0.70 m voxel | 356 | 56 mm | face mass — 2.8 effective points on the face (pose m² is 15, under the gate) |
| 0.50 m voxel | 729 | 150 mm | independent pose, m² 221 |
| 0.30 m voxel | 2017 | 88 mm | independent pose, m² 183 |
| 0.12 m voxel | 11949 | 42 mm | face scatter — 21.7 mm rms against a declared 10 mm sensor |

(The pose error varies down the table because a finer reduction weights the
visible faces differently, not because any reduction escapes the offset.)

The last row is the declared-sensor gate doing exactly what it says: the
simulated instrument delivers range-dependent error the declaration does not
cover, and the face residual is held to the declaration. `tests/
test_surface_capture_chain.py` holds this sequence.

## Beam mapping

`BeamGeometryStatus` from the IFC adapter maps as:

- `COMPLETE` → `SWEPT_SOLID`
- `LENGTH_ONLY` → `LENGTH_ONLY`
- `BLOCKED` → `INSUFFICIENT`

A `LENGTH_ONLY` beam must not be treated as having section-modulus authority.

## Declared section properties

A capacity check has a third kind of support, distinct from both measured
geometry and dimensional quantities. `GAT_Structural` declares
`PlasticSectionModulusMajorM3` (Z) directly. That value is asserted by the
model author: it is neither measured nor derived from the model's geometry,
so on its own it is `DECLARED_PROPERTY` and closes nothing.

The shipped `gat/demo/beam_model.ifc` is exactly this case — it carries no
body representation at all — which is why its `SATISFIED` prior verdict
yields `REQUEST_EVIDENCE` rather than `ACCEPT`.

When the beam *does* carry a swept solid, the adapter independently derives
the **elastic** modulus S = I/c from the profile polygon. Z and S are
different section properties and are never compared for equality; they are
related by the shape factor k = Z/S. `gat.engineering.section_corroboration`
brackets k at `[1.00, 1.30]`:

- k ≥ 1 is a geometric floor — Z ≥ S holds for any solid section, so a
  declaration below it cannot describe that solid at all.
- A filled rectangle gives exactly k = 1.5. Rolled doubly-symmetric
  wide-flange shapes, which is what `GAT_StructuralScope` restricts this
  profile to, sit near 1.10–1.15.

Inside the bracket the check becomes `DECLARED_CORROBORATED` and may close a
capacity case. This is the same shape of upgrade a verified scan receipt
performs for clearance.

Corroboration is not verification. A bracketed declaration has only been
shown to be consistent with a solid the same file asserts; it never becomes
a measurement, and it never closes an as-built clearance case. What the
bracket actually catches is the class of error that occurs in practice: a
wrong unit, a misplaced decimal, a value read from the wrong row of a
section table.

## Capacity checks reach the gate

`AcceptanceCheckKind.CAPACITY` and `capacity_check()` bring a member
capacity verdict under the case policy. `authority` is a required argument,
not a default: a capacity verdict is only as good as the section property
behind it. A capacity check that declares no authority reads as
`INSUFFICIENT`, because dimensional quantities do not establish a section
modulus.
