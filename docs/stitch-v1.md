# Stitch v1 — compose only where the axioms survive the join

```text
declare plant / IFC world
  -> JSPT   A = J(x*)      square, finite, within the certificate law
  -> PLSR   verdict on A   bound to that exact A, from the shipped vocabulary
  -> CSE    disposition    a certificate is support, never authorization
```

```console
gat stitch A.json receipt.json --cite disposition.json    # 0 composes, 2 type miss
```

An arrow exists only when the codomain of the previous object is the domain of
the next. Everything here is the refusal at that arrow, checked **before** any
stage runs. A miss is a refusal with a reason and exit 2, not an exception
swallowed into the next stage.

## What it refuses

| join | refusal |
|---|---|
| rectangular matrix | a sensitivity Jacobian is not a plant; form `A = J_f(x*)` first |
| `dim > 24` | exceeds `MAX_KRONECKER_DIM`, a declared law rather than a performance budget |
| digest mismatch | a verdict does not transfer between matrices |
| `VERIFIED` as a verdict | that is a proof status, not a stability claim |
| unshipped verdict name | a vocabulary that exists only in prose refuses nothing |
| `global_claim` with no vertex set | a certified sample is one point, not a proof over a parameter box |
| non-`certified` as `support_code` | only `certified` supports anything |
| `may_authorize: true` | authorization is a human `ApprovalRecord` |

## Two vocabularies, kept apart

This is the distinction the module exists for, and it is easy to get wrong —
I did, first time.

- `lyapunov.runtime.verdict` returns **lower case**: `certified`, `violated`,
  `outside-level`, `inconclusive`. This is the Lyapunov sample.
- `lyapunov.host_callback.ProofStatus` is **upper case**: `NOT_CHECKED`,
  `INVALID`, `VERIFIED`. This says whether a bound host verified an SP1 proof.

A `VERIFIED` proof attachment says the arithmetic was checked. It does not say
the plant decreases. Letting one stand in for the other would be the exact
failure this pipeline is built to prevent, so the two sets are asserted disjoint
and a proof status offered as a verdict is refused by name.

`LYAPUNOV_SAMPLE` and `SUFFICIENT_COMMON_QUADRATIC` have been discussed and are
not in the companion. They are refused. An axiom system whose terms exist only in
prose refuses nothing.

## What it is not

- **It imports no companion runtime.** The portfolio rule is "each repo keeps
  local I. none import another runtime", so this reads JSON and checks laws. The
  companion's frozen constants are mirrored and `tests/test_stitch.py` asserts
  they agree wherever the companion is importable — the same agreement-not-import
  pattern as the JSPT ownership pin.

  A mirror needs a version, because the agreement test cannot run where the
  companion is not checked out, which is every deployment. So every record
  carries `law_applied`: the two constants it used, the module they were read
  from, and `verified_equal_at` — the companion commit they were read at. That
  field is a verification pin, not an origin claim: it says "read here, found
  equal", not "this commit fixed the law". The distinction is not pedantry. The
  first pin written here named a commit that did not exist in the companion at
  all, and nothing caught it until the checkout was consulted; `tests/test_stitch.py`
  now checks the pin's shape so an unresolvable one fails at home instead of
  travelling in an artifact.
- **It computes nothing.** No Jacobian, no Lyapunov solve, no device. A stitcher
  that also computed would be the megascript this avoids. The linear bulk belongs
  inside one kernel with an oracle match test, the way the sparse-belief exit test
  is written — and if a device path can change a digest it is a new kernel
  version, not an optimization.
- **It decides nothing.** `composes: true` means the sequence types. The
  supervisor still decides, and the record says so in `not_claimed`.
