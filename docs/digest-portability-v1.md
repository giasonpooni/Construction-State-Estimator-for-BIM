# World digest portability v1

Status: one half fixed, one half a recorded finding. `portable_world_digest` is
now portable across processors. `World.digest()` is not, and making it so is a
kernel version bump that is not taken here.

## The defect

`docs/kernel-v1.md` says a change that moves a disposition, digest, or replay on
the acceptance slice is a version bump of the kernel. That rule assumes a digest
moves only when the code or the model moves.

It does not. `World.digest()` is

```python
h.update(self.module.digest().encode())
h.update(self.full.mu.tobytes())
h.update(self.full.sigma.tobytes())
```

— `gat/engine/executor.py:136`. The third line hashes the raw float64 bytes of
the full-view covariance, which is built by BLAS. BLAS picks its kernel from the
CPU it finds, kernels sum in different orders, and float addition is not
associative. So the same file, on the same numpy and the same Python, gives a
different world digest on a different processor.

## Measured

`gat/demo/model.ifc` spelled `gat/demo/model.ifc`, numpy 2.5.3, forcing the
kernel with `OPENBLAS_CORETYPE`:

| kernel | `world_digest` |
|---|---|
| `SKYLAKEX` | `020383e8…` |
| `HASWELL` | `6df20d41…` |
| `ZEN` | `6df20d41…` |
| `SANDYBRIDGE` | `b18ff0a9…` |
| `NEHALEM` | `c4a8d1b7…` |

`020383e8…` is the value this repository documented as frozen. `6df20d41…` is
what GitHub's runner produced, which is how this was found: CI failed a pin that
passed in every local environment. Run 223 failed `test (3.12)` and run 224
passed the same commit on the same job — not flakiness, different hardware.

The difference is one ULP wide. `SKYLAKEX` against `HASWELL`, on the 63×63
full-view covariance: **2 of 3969 entries** differ, by at most 2.168e-19
absolute and **1.920e-16 relative, which is 0.86 × eps**. `NEHALEM` differs in 27
of 3969, same relative bound. All three matrices stay exactly symmetric.

Two entries at the last bit flip a sha256 completely. That is what a hash is for,
and it is why a hash over floats cannot express "the same estimate".

## Scope: nine identities move, one root cause

Every digest the demo slice produces, computed under all five kernels.

**Stable on all five** — safe to pin, safe to cite across machines:

| identity | why it survives |
|---|---|
| `module.digest()`, both models | hashes printed IR text, no floats |
| `configuration_digest()` | quantizes before hashing — see below |
| `GaussianState.digest()`, the **raw** belief | raw mu and Sigma are never BLAS products |
| `full.mu` | a shorter contraction than the covariance |
| `beam_model.ifc` `world_digest` | for a reason, not by guarantee — see below |
| `margin_mean`, `margin_sigma`, `p_satisfies_lower` | the decision numbers |
| the disposition | `REQUEST_EVIDENCE` on every kernel |
| `_scan_digest` of a scan | hashes the input points, which is its job |

**Moves with the CPU**, four distinct values across the five kernels:

| identity | note |
|---|---|
| `full.sigma` | the root cause |
| `world_digest`, before and after each transform | ends in `full.sigma` |
| `AcceptanceCase.scope_digest` (the case digest) | embeds `world_digest` |
| **BCF topic GUIDs** | `uuid5(TOPIC_NAMESPACE, f"{case_digest}/{check_id}")` |
| `scene.version` / `RegistrationResult.scene_version` | *is* the world digest |
| the fitted pose: `theta`, `t`, `nll`, `pose_sigma()`, `info_matrix` | last 1–2 ULPs |

Nine moving identities, **one root cause**. `scope_digest` embeds `world_digest`,
`scene.version` is it, and the BCF GUID is derived from the case digest.
Repairing `World.digest()` repairs all of them.

### The two that are visible without looking at a digest

**BCF topic GUIDs are not stable across machines.** `gat/adapters/bcf.py` derives
them deterministically on purpose, so that re-exporting the same unresolved case
yields the same topic and a BIM tool recognises it as the same issue instead of
filing a duplicate. That property holds per machine only. Two engineers exporting
the same case from the same model on different hardware produce different topic
GUIDs, and the receiving tool cannot tell they are the same issue.

**The registered pose itself moves, not only its hash.** `theta` differs in the
16th significant digit between `NEHALEM` and the others, and `pose_sigma()` with
it — and `pose_sigma` is what scan evidence reports as its uncertainty. Checked
for the worse version of this and it is not there: `ScanRegistrar` selects among
multi-start EM basins where "ties break by start index", so a tie inside float
noise could have selected a different pose entirely. Measured over three scans,
the best-to-second gap is 0.52 to 0.59 and the smallest gap between any two
starts is 0.004, against an eps scale of 1e-15. Twelve orders of headroom. The
basin choice is safe; only the winning pose's last bits move.

### The beam digest is stable for a reason, not by guarantee

`beam_model.ifc` gives the same `world_digest` on all five kernels, which is why
the freeze's beam slice is intact. The reason is its dependency structure:

| model | pushforward `J` | nonzeros per row | full view |
|---|---|---|---|
| `beam_model.ifc` | 6×4 | max **2** | 6×6 |
| `model.ifc` | 63×24 | max **18**, mean 2.44 | 63×63 |

Each entry of `J Σ Jᵀ` is a sum over the nonzeros of two rows. At two nonzeros
that is a sum of at most four products, too short to reassociate. At eighteen it
is a sum of up to 324, and it does.

Size alone does not explain it, and the first explanation offered here — "too
small for BLAS to switch kernels" — was wrong: a dense 6×6 `H Σ Hᵀ` with
pseudo-random entries already differs between `SKYLAKEX` and `NEHALEM`, as does a
4×4. The beam is stable because that model has no derived quantity combining more
than two raw variables. Add one and it is not. `tests/test_digest_portability.py`
pins the sparsity so the reason is checked rather than remembered.

## The snapshot round-trip fails on the same cause

Running the whole suite under each kernel found something worse than a moved
digest. Under `NEHALEM`, two tests **error**:

```
tests.test_state_snapshot.StateSnapshotTests.test_separate_process_portability_demo
tests.test_openusd.OpenUsdCarrierTests.test_separate_process_openusd_continuation_demo
gat.errors.SnapshotError: reconstructed world digest differs from source
```

Both are the portability demos. The feature named portability is the one that
breaks.

It is not about separate processes, and not about two machines. The demo's exact
sequence, in one process on one kernel:

```
load model -> observe Office-A Volume -> export checkpoint
load that checkpoint -> shift Level 1 ClearHeight -> export resumed
read the resumed file straight back
```

| kernel | written digest | reread |
|---|---|---|
| `SKYLAKEX` | `aed6712d…` | `aed6712d…` — round-trips |
| `NEHALEM` | `6bd0181b…` | **refused**: reconstructed world digest differs from source |

One file written and immediately read: the snapshot refuses its own output. The
raw belief is not at fault — its 24×24 covariance is bit-identical across every
kernel tested and survives the snapshot's decimal text exactly, before and after
a transformation. `reconstruct_snapshot` rebuilds the full view and compares
`world.digest()` against the recorded `source_world_digest`
(`gat/state_snapshot.py:259`), so whether they agree is a property of the BLAS
kernel rather than of the snapshot.

GitHub's runners are Haswell/Skylake-class, where it passes, so this is not what
CI fails on. It is a claim the repository makes that does not hold on hardware
nobody has ruled out.

## What is *not* affected

- **Any decision.** Measured directly: `margin_mean`, `margin_sigma` and
  `p_satisfies_lower` on the opening-fit checks are bit-identical under all five
  kernels, and so is the disposition. Every margin turns on quantities twelve or
  more orders above eps. **The estimates are fine. The identity of the estimate
  is what was broken.**
- **Replay on one machine.** Two independent lowerings of the same file agree bit
  for bit.
- **The module digest**, so every claim turning on the lowering, the IFC content,
  or the path spelling.

The suite passes outright under `SANDYBRIDGE`, `HASWELL`, `SKYLAKEX` and `ZEN`.
Under `NEHALEM` the two errors above, both digest-equality checks rather than
decisions.

## The remedy: three of four layers already had it

The audit checked how every layer that compares floats does it. Three were
already right, by three different correct methods, and the digest path was the
outlier in its own codebase:

| layer | how it compares | portable |
|---|---|---|
| `gat/engine/verify.py` invariants | relative tolerance, `1e-9 * max(1, abs(expected))` | yes |
| `gat/engine/configuration.py` | quantizes to `QUANT = 1e-6` before hashing | yes, with the margin below |
| `computational_equivalence` | takes `atol` and `rtol` | yes — if they are ever passed |
| `World.digest()`, `reconstruct_snapshot` | raw float64 bytes | **no** |

The invariant registry never compares a computed float exactly. So the runtime's
*verification* layer was written with reassociation in mind and its *identity*
layer was not.

`configuration_digest` is the sharpest case: `_entity_intrinsic` calls
`world.full.mean(slot.var)` and `world.full.std(slot.var)` — the very quantities
whose last bits move — and survives because every value passes through `_q`.
Quantize-before-hashing was never a design waiting for a number. It was a working
precedent one module over, with its number.

And `computational_equivalence` in `gat/state_snapshot.py` already carries the
remedy with the use case named in its own docstring:

> The default is exact same-platform identity. Nonzero tolerances support
> cross-platform carriers while identity, topology and expression semantics
> remain exact.

That is this finding, written down before it was measured. The parameters exist,
they default to `0.0`, and **nothing in the repository ever passes a nonzero
value**. Meanwhile `reconstruct_snapshot` does not call
`computational_equivalence` at all for its portability check — it compares
`world.digest()`, the byte comparison the tolerances were added to avoid.

### What is now fixed: `portable_world_digest`

That function existed to be portable and was not: it copied the kernel's
composition, eliding only `source`, so it fixed path spelling and inherited the
processor dependence. It now hashes the full view as **canonical decimal text at
`PORTABLE_SIGNIFICANT_DIGITS = 12`**.

Measured across all five kernels on `gat/demo/model.ifc`:

| | distinct values |
|---|---|
| `World.digest()` | 4 |
| `portable_world_digest()` | **1** |

Decimal text rather than arithmetic rounding, because CPython's float formatting
is correctly rounded and platform-independent, it avoids the representation error
in `10.0 ** k`, and it avoids a banker's-rounding tie landing differently. It
also keeps this digest the same kind of object the module digest already is: a
hash of canonical text.

**Why twelve digits.** Rounding is not a homomorphism — two values a hair apart
round differently if they straddle a boundary — so the question is each value's
margin against its own wobble. Measured over every full-view value of both
shipped models, worst per-value ratio of margin to perturbation:

| significant digits | office model | beam model |
|---|---|---|
| 15 | 1.31 | 3.42 |
| 14 | 24.6 | 34.2 |
| 13 | 261 | 342 |
| **12** | **2620** | **3420** |
| 10 | 1.15e+05 | 3.42e+05 |
| 8 | 2.62e+07 | 3.42e+07 |
| 6 | **1.85** | 3.42e+09 |

Twelve keeps a 2620× margin on the model that stresses it, with no value within
one perturbation of a flip, and still keeps twelve digits of the covariance.

Read the 6-digit row: a *coarser* grid scored 1.85, worse than 12 and worse than
15. Coarser is not monotonically safer, because a coarser grid can place a
boundary right beside a value. The margin has to be measured, not reasoned about.
`tests/test_portable_identity.py` fails if either shipped model drifts within
100× of a boundary.

The trade is explicit: the portable digest is **coarser**. Two beliefs differing
in the 13th significant digit share it. For an identity that is the right
resolution — they are the same estimate by any engineering standard — but it
means the portable digest can never be used to claim bitwise restart identity.
`computational_equivalence` is the tool for that.

For reference, `configuration_digest`'s own margin at `QUANT = 1e-6`, over the
126 values it quantizes (one mean and one standard deviation per slot):

| | office | beam |
|---|---|---|
| closest approach to a rounding flip | 1.364e-09 | 4.216e-08 |
| worst cross-kernel perturbation | 1.455e-11 | 1.455e-11 |
| margin | **94×** | 2900× |

Comfortable, and a probability rather than a proof: if boundary positions were
uniform, about one model in 550 would land close enough to flip.

### What is not fixed, and why

`World.digest()` still hashes raw bytes. Any fix moves every digest on all four
frozen slices at once, which is the largest possible version bump, so it is a
decision to take deliberately rather than a repair to slip in. The open question
is no longer "what tolerance?" — it is whether `PORTABLE_SIGNIFICANT_DIGITS` is
the right resolution for the *kernel's* identity, given that the kernel's
sensitivity to path spelling is deliberate and its sensitivity to processor is
not.

The snapshot round-trip needs the same decision and would be fixed by calling the
function already there: `computational_equivalence` with a tolerance instead of
zero, recording which tolerance was applied. The raw belief can keep its exact
check, because that one is genuinely portable.

The sparse-belief exit test still needs its own number, and it is a different
number: `docs/sparse-belief-v1.md:41` wants a relative agreement bound between a
dense and a sparse path, not a representation quantum.

## What the tests assert

`tests/test_digest_portability.py` pins the structural facts a kernel sweep
cannot be run for in-process: which digests are composed from float bytes, that
the case digest and BCF GUID inherit the world digest, that the beam's stability
comes from its pushforward sparsity, that the decision numbers have twelve orders
of margin over eps, that the invariant registry uses relative tolerances, and
that `computational_equivalence`'s tolerances are still unused.

`tests/test_portable_identity.py` pins the module digest and the mean exactly
(both measured invariant across five kernels), recomposes `world.digest()` by
hand so the reasoning about which parts are portable cannot silently stop
holding, shows one ULP moving the local digest and **not** moving the portable
one, checks the 12-digit margin against the measured wobble, and checks the
record declares how coarse the portable digest is.
