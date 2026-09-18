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
  and every margin turn on quantities far above 1e-16. No disposition in the
  suite changes under any kernel: the whole suite passes under `NEHALEM`,
  `SANDYBRIDGE`, `HASWELL`, `SKYLAKEX` and `ZEN`. **The estimates are fine.
  The identity of the estimate is what is broken.**

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

All three require one number: how close two covariances must be to count as
the same estimate. That number does not exist in this repository yet, and no
axiom produces it. Until it does, the finding is recorded and the pins stay as
they are.

The snapshot round-trip needs the same number, and would be fixed by the same
choice: compare reconstructed beliefs to a declared tolerance rather than by
float64 byte equality, and say in the record which tolerance was applied. The
raw belief can keep its exact check, because that one is genuinely portable.

## What the tests assert now

`tests/test_portable_identity.py` pins the module digest and the mean exactly,
recomposes `world.digest()` by hand so the claim about which parts are portable
cannot silently stop holding, shows that one ULP in the covariance moves the
composite, and shows the digest is stable within one machine. It no longer pins
the composite, because that pin was a fact about this container's CPU.
