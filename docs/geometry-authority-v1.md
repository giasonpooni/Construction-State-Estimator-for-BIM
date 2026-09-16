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

## The support window used to be pinned to the model

`adapt_clearance_likelihood` finds the element's support face by projecting
the registered returns onto the clearance direction and averaging the ones
inside a band. That band was centred on `predicted` — the BIM's own answer
to the question being asked — and never moved:

```python
predicted = direction @ center + support_radius(element, direction)
face_mask = np.abs(projections - predicted) <= calibration.face_band
```

A face at `predicted + δ` is then **one-side truncated** by its own support
window, so the reported deviation is pulled back toward the model. Measured
through the whole pipeline on Wall-Party's top face, 400 returns at a 10 mm
sensor and the shipped 60 mm band:

| true offset | reported | shortfall | `face_residual_rms` | outcome |
|---|---|---|---|---|
| 30 mm | 29.4 mm | 0.6 mm | 10.00 mm | reported |
| 40 mm | 38.8 mm | 1.2 mm | 9.40 mm | reported |
| 50 mm | 46.7 mm | 3.3 mm | 7.98 mm | reported |
| 55 mm | 49.9 mm | 5.1 mm | 7.17 mm | reported |
| 60 mm | 52.0 mm | 8.0 mm | 6.45 mm | reported |
| 70 mm | 53.9 mm | **16.1 mm** | **4.67 mm** | reported |
| 80 mm | — | — | — | refused |

Three things go wrong at once, and they compound:

1. The reported deviation is short, and short in the direction of agreeing
   with the model — in an instrument whose entire output *is* the deviation.
2. `face_residual_rms` is taken about that already-pulled mean, so a
   truncated sample looks **tighter** than an untruncated one. The gate meant
   to catch "this is a shape, not noise" reads 4.67 mm against its 15 mm
   bound at the point of worst error — quieter than it reads on a face that
   is exactly right.
3. A shrunken deviation is a shrunken innovation, so the 5σ innovation gate
   does not see it either. At a true 60 mm offset the pinned window reported
   52.0 mm and passed; the settled window puts the real number in front of
   the same gate and it fires at 5.29σ.

Past about 80 mm the element's own GMM responsibilities die and the case
refuses on effective points. That part always worked. The hole is the band
either side of it, where a real as-built deviation is reported as a smaller
one with every gate green.

### Settling the window on the returns

The window now starts at `predicted` and re-centres on the weighted mean of
what it retains until it stops moving — mean shift with a flat kernel,
bounded in rounds so two rival clusters give a bounded answer rather than a
loop. The distance it travelled is `walked`, which is the estimator's own
statement of how far the as-built face is from the model, and the one number
the pinned window could not produce.

| true offset | reported | shortfall | `face_residual_rms` |
|---|---|---|---|
| 0–55 mm | accurate | **0.5 mm, flat** | **10.14 mm, flat** |
| 60 mm | refused — innovation gate, 5.29σ | | |
| 70–80 mm | refused — "the support face sits 69 mm from where the model puts it" | | |
| 90 mm+ | refused — 0.000 effective points | | |

The residual 0.5 mm is not the truncation: it is the same at 0 mm as at
55 mm. It comes from weighting the returns by responsibilities that are
themselves centred on the model. Constant, small, and not a function of how
wrong the model is, which is the property that matters.

Two new declared gates bound what settling is allowed to do.

**`max_face_recentre`** (default `0.060`, equal to `face_band`) is how far
the window may walk before the case is refused instead of reported. A face
further off than the window is wide is a deviation this instrument was not
set up to measure, and saying so — with the distance — is more use than a
number. Raising it is a deliberate declaration that the model is expected to
be that wrong.

**`max_rival_plane_share`** (default `0.25`) catches the window settling on
the element's *far* face. A box has two parallel faces exactly 2R apart and
the clearance direction points outward, so the support face is the outer one.
A window on the inner one is a **clean** measurement of the wrong side: the
retained returns are well centred in their own window and every statistic
taken on them is healthy. Only the element's own geometry shows it.

That test applies only when `support_radius > face_band`, so the rival
window is a separate window rather than an overlap of the face being
measured. Below that threshold it reads 0.99 on a clean one-sided scan of
Door-1 — 25 mm of support radius against a 60 mm band — and would refuse
every honest measurement of anything thinner than the band. The thin case is
not unguarded: two faces inside one window make the retained returns
bimodal, and `max_residual_sigma_ratio` reads the half-separation as scatter.
The two gates divide the range between them, and both halves are pinned in
`tests/test_scan_likelihood.py`.

### Only the support face may speak for it

Settling the window surfaced a second, larger defect. The support window is
**one-dimensional** — a band on the projection along `direction` — and a box
has four faces that direction is *perpendicular* to. Their returns fall
inside the band near its far edge.

Wall-Party is 3.0 m tall and 0.2 m thick, so every return on its sides and
ends within one `face_band` of the top landed in the support window. On the
shipped `gat.demo.geometry` scan that is **21.3% of the weight**:

| support window | `face_mass` | `observed` | residual rms |
|---|---|---|---|
| all returns in the band | 36.35 | 2.993521 | 15.08 mm |
| support-face returns only | 28.61 | **2.998803** | **8.84 mm** |

The true wall top is 3.000, so filtering also takes the measurement from
6.5 mm below it to 1.2 mm below it. Those returns were never scatter about
the support plane — they are a *different plane seen edge-on*, and their
spread is what `max_residual_sigma_ratio` had been reading.

`min_face_alignment` already checks that the *direction* names a face rather
than an edge or a corner. Nothing checked that each *return* did.
`_on_support_face` now assigns every return to the box face it is nearest, in
the box's own frame — for half-extents h and local coordinates x, the
distance to the face pair on axis i is `| |x_i| - h_i |`, smallest wins — and
keeps only the face the direction points at. It is the rule a scanner's own
geometry obeys, so it needs no tolerance and no new calibration constant.

The sign matters: the support axis carries two faces, and keeping both would
put a thin element's near and far faces inside one retained set, which is
exactly what `max_rival_plane_share` exists to refuse.

The strongest evidence that this is the right filter is that **with it, the
pinned window and the settled window return bit-identical numbers** — mass
28.61, observed 2.998803, rms 8.84 mm. A correct extraction cannot depend on
its own starting guess, and before the filter it did.

### What the demo was actually doing

Worth recording, because it is the reason this was invisible. The demo had
been passing the 15 mm shape gate at 11.96 mm — and only because the window
was pinned 6.5 mm above the returns and clipped more of the contaminating
tail. Settling the window honestly took it to 15.08 mm and refused. **Both
numbers were wrong.** The face filter is what makes them agree, and it takes
the demo to 8.84 mm rms with a support reading 1.2 mm off the truth instead
of 4.9 mm off.

A gate passing is not the same as a gate being right, and a fixture that
passes on a bias will keep passing until something changes the bias.


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

## Support follows the target, not the label

A check's authority used to be derived from its `AcceptanceCheckKind`:
`CLEARANCE` meant `GAUSSIAN_PROXY`, `CAPACITY` meant `INSUFFICIENT`, and
everything else took `QUANTITY_ONLY`. The default was written for `MINIMUM`
and `DIFFERENCE` checks over dimensional quantities — a width, a height, a
length — where IFC quantities really are the support.

But nothing stops a `MINIMUM` check naming a declared structural quantity as
its target. Submitted that way, the same criterion the capacity route
refuses:

| Route | Kind | Authority | Verdict | Disposition | `may_authorize` |
|---|---|---|---|---|---|
| A | `CAPACITY` | `DECLARED_PROPERTY` | `SATISFIED` | `REQUEST_EVIDENCE` | false |
| B | `MINIMUM` | `QUANTITY_ONLY` | `SATISFIED` | `ACCEPT` | **true** |

Same world, same `target_mean` to the last bit (315000.00000000006 N·m),
same `p_satisfies` (0.9625778267382401). Only the label differed. The
accepted case then recorded `QUANTITY_ONLY` — a positive claim of
dimensional support — for a verdict resting on a section modulus nobody
measured.

The route was reachable from outside. `gat.headless` accepts a `minimum`
check over any `{entity_name, quantity}` pair and offers no capacity kind at
all, so relabelling was the *only* way to put a capacity question to that
boundary — and it answered `ACCEPT`, `may_authorize: true`, "all checks are
satisfied and required evidence is verified", with zero evidence requests.

So authority now follows what the check is **about**:

- `minimum_check()` and `difference_check()` record their targets in
  `details["target_quantities"]`.
- A check naming any member of
  `gat.engineering.beam.DECLARATION_BACKED_QUANTITIES`
  (`YieldStrengthMPa`, `PlasticSectionModulusMajorM3`,
  `NominalMomentCapacity`, `DesignMomentCapacity`) reads as
  `DECLARED_PROPERTY` whatever kind it arrived under. One such target on
  either side of a difference is enough — the declaration is still on one
  side of the subtraction.
- A `MINIMUM` or `DIFFERENCE` check that names no target at all reads as
  `INSUFFICIENT`. Unknown is not a licence: a check that reaches the gate
  without saying what it is about cannot be shown to be dimensional, and
  treating unknown as dimensional is precisely the assumption that caused
  this. Every check built through this library's own constructors carries
  its target, so falling closed costs nothing on any real path.
- An explicit `details["geometry_authority"]` still wins, so the
  corroborated route keeps the `DECLARED_CORROBORATED` it earned.

The `QUANTITY_ONLY` default therefore applies only to checks that have
actually named dimensional targets.
