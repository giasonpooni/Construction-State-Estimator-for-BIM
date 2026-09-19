# World digest portability v1

Status: finding, not a repair. The remedy is a kernel version bump and is not
taken here.

## The claim that failed

`docs/kernel-v1.md` says a change that moves a disposition, digest, or replay
on the acceptance slice is a version bump of the kernel. That rule assumes a
digest moves only when the code or the model moves.

It does not. `World.digest()` is

```python
h.update(self.module.digest().encode())
h.update(self.full.mu.tobytes())
h.update(self.full.sigma.tobytes())
```

— `gat/engine/executor.py:136`. The third line hashes the raw float64 bytes of
the full-view covariance, which is built by BLAS. BLAS picks its kernel from
the CPU it finds, kernels sum in different orders, and float addition is not
associative. So the same file on the same numpy and the same Python gives a
different world digest on a different processor.

## Measured

`gat/demo/model.ifc`, spelled `gat/demo/model.ifc`, numpy 2.5.3, forcing the
kernel with `OPENBLAS_CORETYPE`:

| kernel | `world_digest` |
|---|---|
| `SKYLAKEX` | `020383e8…` |
| `HASWELL` | `6df20d41…` |
| `ZEN` | `6df20d41…` |
| `SANDYBRIDGE` | `b18ff0a9…` |
| `NEHALEM` | `c4a8d1b7…` |

`020383e8…` is the value this repository documented as frozen. `6df20d41…` is
what GitHub's runner produced. They are the same code on two processors.

The two components that did **not** move, under all five kernels:

| component | value |
|---|---|
| `module.digest()` | `cec15f08…` |
| `sha256(full.mu)` | `cf76cfdd…` |

So the model, the lowering, and the mean are portable. Only the covariance is
not.

## How small the difference is

`SKYLAKEX` against `HASWELL`, on the 63×63 full-view covariance:

- 2 of 3969 entries differ
- largest absolute difference 2.168e-19
- largest relative difference 1.920e-16, which is 0.86 × eps

`SKYLAKEX` against `NEHALEM`: 27 of 3969 entries, same 1.920e-16 relative
bound. Both matrices stay exactly symmetric.

Two entries, at the last bit, flip a sha256 completely. That is what a hash is
for, and it is why a hash over floats cannot express "the same estimate".

## Full sweep: what moves and what does not

Every digest the demo slice produces, computed under `SKYLAKEX`, `HASWELL`,
`ZEN`, `SANDYBRIDGE` and `NEHALEM`.

**Stable on all five** — safe to pin, safe to cite across machines:

| identity | why it survives |
|---|---|
| `module.digest()` (both models) | hashes printed IR text, no floats |
| `configuration_digest()` (before and after transforms) | the coarser quotient |
| `GaussianState.digest()` — the **raw** belief | raw mu and Sigma are never BLAS products |
| `full.mu` | the mean is a shorter contraction than the covariance |
| `beam_model.ifc` `world_digest` | see the caveat below |
| `margin_mean`, `margin_sigma`, `p_satisfies_lower` | decision numbers, bit-identical |
| the disposition | `REQUEST_EVIDENCE` on every kernel |
| `_scan_digest` of a scan | hashes the input points, which is what it is for |

**Moves with the CPU** — four distinct values across the five kernels:

| identity | note |
|---|---|
| `full.sigma` | the root cause |
| `world_digest`, before and after each transform | ends in `full.sigma` |
| `portable_world_digest` | same composition, `source` elided |
| `AcceptanceCase.scope_digest` (the **case digest**) | embeds `world_digest` |
| **BCF topic GUIDs** | `uuid5(TOPIC_NAMESPACE, f"{case_digest}/{check_id}")` |
| `scene.version` / `RegistrationResult.scene_version` | is the world digest |
| the fitted pose: `theta`, `t`, `nll`, `pose_sigma()`, `info_matrix` | last 1–2 ULPs |

Nine moving identities, **one root cause**: `scope_digest` embeds
`world_digest`, `scene.version` *is* the world digest, and the BCF GUID is
derived from the case digest. Repairing `World.digest()` repairs all of them.

Two of those deserve naming separately.

**BCF topic GUIDs are not stable across machines.** `gat/adapters/bcf.py`
derives them deterministically on purpose, so that re-exporting the same
unresolved case yields the same topic and a BIM tool recognises it as the same
issue instead of filing a duplicate. That property holds per machine only. Two
engineers exporting the same case from the same model on different hardware
produce different topic GUIDs, and the receiving tool has no way to tell they
are the same issue. This is the one place where the defect is visible to
somebody who never looks at a digest.

**The registered pose itself moves, not only its hash.** `theta` differs in the
16th significant digit between `NEHALEM` and the others, and `pose_sigma()`
with it — and `pose_sigma` is what scan evidence reports as its uncertainty.
Checked for the worse version of this and it is not there: `ScanRegistrar`
selects among multi-start EM basins where "ties break by start index", so a tie
inside float noise could have selected a different pose entirely. Measured over
three scans, the best-to-second gap is 0.52 to 0.59 and the smallest gap between
any two starts is 0.004, against an eps scale of 1e-15. Twelve orders of
headroom. The basin choice is safe; only the winning pose's last bits move.

### The beam digest is stable for a reason, not by guarantee

`beam_model.ifc` gives the same `world_digest` on all five kernels, which is
why the freeze's beam slice is intact. The reason is its dependency structure,
not its size:

| model | pushforward `J` | nonzeros per row | full view |
|---|---|---|---|
| `beam_model.ifc` | 6×4 | max **2** | 6×6 |
| `model.ifc` | 63×24 | max **18**, mean 2.44 | 63×63 |

Each entry of `J Σ Jᵀ` is a sum over the nonzeros of two rows. At two nonzeros
that is a sum of at most four products, too short to reassociate. At eighteen
it is a sum of up to 324, and it does.

Size alone does not explain it: a dense 6×6 `H Σ Hᵀ` with pseudo-random entries
already differs between `SKYLAKEX` and `NEHALEM`, as does a 4×4. So the beam's
stability is a property of that model having no derived quantity that combines
more than two raw variables. Add one and the beam digest becomes
CPU-dependent too. It is not a safe harbour.

## What this invalidates

1. **The freeze rule cannot tell a code change from a different machine.** A
   digest that moves is supposed to mean somebody changed the decision slice.
   It can equally mean the runner was Haswell this time. CI run 223 failed
   `test (3.12)`; run 224 passed the same commit on the same job. Not
   flakiness — different hardware.
2. **Every pinned `world_digest` in `validation/` is a statement about the
   processor that produced it**, on top of being a statement about the path
   spelling (`docs/world-identity-v1.md`). This is the better explanation for
   the opening-fit pins: no path spelling in this checkout reproduces
   `be62ab70…`, and no spelling ever would, because the pin also carries a CPU.
3. **`portable_world_digest` does not fix this.** It elides `source`, which
   addresses path spelling only. Its composition still ends in
   `full.sigma.tobytes()`, so it is portable across repositories and not across
   processors. The name promises more than it delivers.

## What is *not* affected

- Replay on one machine. Two independent lowerings of the same file agree bit
  for bit; `tests/test_portable_identity.py` pins that.
- The module digest, so every claim that turns on the lowering, the IFC
  content, or the path spelling is unaffected.
- Any decision. `SATISFIED`/`VIOLATED`, `ACCEPT`/`REJECT`/`REQUEST_EVIDENCE`
  and every margin turn on quantities far above 1e-16. Measured directly:
  `margin_mean`, `margin_sigma` and `p_satisfies_lower` on the opening-fit
  checks are bit-identical under all five kernels, and so is the disposition.
  **The estimates are fine. The identity of the estimate is what is broken.**

  The suite passes outright under `SANDYBRIDGE`, `HASWELL`, `SKYLAKEX` and
  `ZEN`. Under `NEHALEM` two tests error, and both are digest-equality checks
  rather than decisions — see the second finding below. An earlier draft of
  this list said the suite passed under all five, which was written before the
  sweep had been run and was wrong seven lines above the evidence against it.

## A second finding, from the same probe

Running the whole suite under each kernel turned up something worse than a
moved digest. Under `NEHALEM`, two tests do not merely disagree about a digest,
they **error**:

```
tests.test_state_snapshot.StateSnapshotTests.test_separate_process_portability_demo
tests.test_openusd.OpenUsdCarrierTests.test_separate_process_openusd_continuation_demo
gat.errors.SnapshotError: reconstructed world digest differs from source
```

Both are the portability demos. The feature named portability is the one that
breaks.

It is not about separate processes, and not about two machines. The demo's exact
sequence, run entirely in one process on one kernel:

```
load model -> observe Office-A Volume -> export checkpoint
load that checkpoint -> shift Level 1 ClearHeight -> export resumed
read the resumed file straight back
```

| kernel | written digest | reread |
|---|---|---|
| `SKYLAKEX` | `aed6712d…` | `aed6712d…` — round-trips |
| `NEHALEM` | `6bd0181b…` | **refused**: reconstructed world digest differs from source |

One process, one kernel, one file written and immediately read: the snapshot
refuses its own output. The raw belief is not the problem — the 24×24 raw
covariance is bit-identical across every kernel tested and survives the
snapshot's decimal text exactly, measured both before and after a
transformation. What differs is the full view recomputed from that raw belief
during reconstruction. `reconstruct_snapshot` rebuilds it, compares
`world.digest()` against the recorded `source_world_digest`
(`gat/state_snapshot.py:259`), and whether those agree is a property of the
BLAS kernel rather than of the snapshot.

So the demo's closing line — "operational identity preserved" — is true on this
container's processor and not on a Nehalem-class one. Nothing is wrong with the
numbers; `computational_equivalence` passes. The bit-exactness check is what is
wrong, because it tests equality of float64 bytes for a quantity that is only
equal to within reassociation.

GitHub's runners are Haswell/Skylake-class, where it passes, so this is not
what CI is failing on. It is a claim the repository makes that does not hold on
hardware nobody has ruled out.

## The remedy, and why it is not applied here

Any fix changes `World.digest()`, which moves every digest on all four frozen
slices at once. That is the largest possible version bump, so it is a decision
to take deliberately rather than a repair to slip in. Three options:

1. **Quantize before hashing.** Hash the covariance rounded to a declared
   number of significant digits, with the rounding rule named in the record.
   Keeps one digest, makes the tolerance explicit, and needs the same number
   the sparse-belief exit test needs and does not have
   (`docs/sparse-belief-v1.md:41`, "the stated tolerance").
2. **Drop the covariance from the identity.** Digest the module and the mean,
   and cite the covariance separately with a tolerance. Loses the property that
   a changed uncertainty changes the identity, which is a real loss for an
   uncertainty runtime.
3. **Declare the digest machine-local and add a portable identity that is not a
   float hash.** Most honest, most work, and needs the same tolerance as (1).

**Option 1 already exists in this repository.** The audit that produced the
sweep above found it: `configuration_digest` reads the same BLAS output the
world digest does — `_entity_intrinsic` calls `world.full.mean(slot.var)` and
`world.full.std(slot.var)` — and survives the kernel sweep because every value
goes through `_q`, which rounds to `QUANT = 1e-6`, declared in
`gat/engine/configuration.py` and stated in its module docstring. So the
quantize-before-hashing remedy is not a design waiting for a number. It is a
working precedent one module over, with its number, already proven portable on
five kernels.

That changes the recommendation. `World.digest()` should adopt the same treatment
`configuration_digest` already applies, and the open question shrinks from "what
tolerance?" to "is `QUANT` the right quantum for a covariance, whose entries here
run to 4.55e+04 in the office model and 6.86e+07 in the beam?"

**With one caveat that has to travel with it.** Rounding is not a homomorphism.
Two values a hair apart still round differently if they straddle a boundary, so
quantizing converts a certainty into a probability. Measured, on the values
`configuration_digest` actually quantizes — 126 for the office model, 12 for the
beam, being one mean and one standard deviation per slot rather than the whole
covariance:

| | office | beam |
|---|---|---|
| quantized values | 126 | 12 |
| closest approach to a rounding flip | 1.364e-09 | 4.216e-08 |
| worst cross-kernel perturbation observed | 1.455e-11 | 1.455e-11 |
| margin | **94×** | 2900× |
| expected flipped values if boundaries were uniform | 1.8e-03 | 1.8e-04 |

So `configuration_digest` is portable with a 94× margin on the model that
stresses it most, and portable with probability rather than by construction:
about one model in 550 would land a value close enough to a boundary to flip.
That is a number worth publishing next to the digest rather than discovering
later. `tests/test_digest_portability.py` fails if either shipped model ever
drifts within one perturbation of a boundary.

The only remedy with no residual probability is to keep floats out of an
equality-tested identity altogether — option 3 — comparing beliefs to a declared
tolerance and citing the comparison, rather than hashing them and comparing hashes.

The sparse-belief exit test still needs its own number, and it is a different
number: `docs/sparse-belief-v1.md:41` wants a relative agreement bound between a
dense and a sparse path, not a representation quantum. Quantization does not
answer that one.

The snapshot round-trip needs the same choice as the digest, and would be fixed
by it: compare reconstructed beliefs to a declared tolerance rather than by
float64 byte equality, and say in the record which tolerance was applied. The
raw belief can keep its exact check, because that one is genuinely portable.

## What the tests assert now

`tests/test_portable_identity.py` pins the module digest and the mean exactly,
recomposes `world.digest()` by hand so the claim about which parts are portable
cannot silently stop holding, shows that one ULP in the covariance moves the
composite, and shows the digest is stable within one machine. It no longer pins
the composite, because that pin was a fact about this container's CPU.
