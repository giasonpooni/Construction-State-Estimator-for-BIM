# Uncertainty budget cite

Canonical implementation: RCI `instrument_chain.uncertainty_budget`, schema
`uncertainty-budget-v1`. CSE consumes a declared `u_c` from that record as one
observation's `noise_sigma`. It computes no GUM budget of its own and does not
change `traceability` from `none_claimed`.

## The seam

```
RCI   Budget -> to_record()            components, GUM LPU, Welch-Satterthwaite,
                                       coverage factor, Monte Carlo cross-check
      budget_cite.attach_cite(...)     adds budget_cite: digest + u_c + unit
        |
        |  JSON. nothing is imported.
        v
CSE   budget_cite.observe_from_budget  admits u_c, gated by the bind
      ObserveQuantity.single(var, value, u_c)
```

`gat/adapters/budget_cite.py` on the CSE side, `instrument_chain/budget_cite.py`
on the RCI side. Neither imports the other. `BUDGET_SCHEMA` and
`ADMISSIBLE_TRACEABILITY` are mirrored and asserted equal to RCI's wherever RCI
is importable, the same agreement-not-import pattern as the JSPT ownership pin and
the PLSR constants in `gat/harness/stitch.py`.

**One number crosses.** Not components, not `k`, not `U`, not an interval. If this
seam ever needs more, it is in the wrong place.

## The cite

A cite carries the budget's digest *and* its `u_c`, so a reader need not re-derive
the combination. That convenience is also how a cite could contradict the budget
it names, so CSE checks both: the digest must match the budget supplied alongside
it, and the cited `u_c` must equal what that budget combines to.

The digest covers what *defines* a budget — schema, measurand, unit, components,
correlations, combination, `u_c`, traceability — and deliberately excludes `k`,
`U`, `p`, `dof_eff` and `contributions`. Those are reporting choices. The same
budget reported at 95% and at 99% has one identity, so a cite written at one
coverage still verifies against a record serialised at another.

## What CSE refuses

| refusal | why |
|---|---|
| `traceability` other than `none_claimed` | CSE cannot verify a chain; repeating an unverified one launders it. A traceable budget is not worse — it is not admissible through a seam this thin. |
| a cite whose digest misses its budget | a cite may not disagree with what it points at |
| a cited `u_c` its budget does not combine to | same, for the value |
| a unit that is not the slot's unit | a `u_c` in millimetres is not a sigma on a metre-valued slot, and converting here would invent a conversion the budget never declared |
| a measurand the bind does not name | `docs/cse-point-bind-v1.md`: an observation reaches the kernel only after a bind names the quantity |
| a bind with no `quantity` | naming the entity is not naming the slot |
| `u_c` of zero | claims an exact measurement |
| `u_c` NaN | an *absent* uncertainty, not a wide one |
| `u_c` infinite | a refusal to state one; conditioning on it leaves the prior unchanged while recording that evidence arrived |
| a non-finite number anywhere in the budget | including buried in a component, where no field check looks |

That last row was found by a test rather than by reading. `canonical_digest` sets
`allow_nan=False`, so a NaN inside a component surfaced as *"Out of range float
values are not JSON compliant"* from the JSON encoder — true, and it named neither
the budget nor the component. Both repositories now refuse it by name, and RCI
validates before digesting rather than after for the same reason.

## What an admitted budget still is not

- Not field evidence. A cite does not close `evidence.as_built`.
- Not traceable. `none_claimed` is what was admitted and what the record repeats.
- Not a property of the world. `u_c` is the noise on one observation.

A quantization-dominated bench stays a finding in RCI. It does not become a CSE
prior.

## Verified

`tests/test_budget_cite.py`, 26 tests. The posterior is checked against the
closed-form Gaussian update — `σ_post = (1/σ_prior² + 1/u_c²)^(-1/2)` to 12
places — so nothing of the budget survives into the belief except its `u_c`. Four
tests run only where RCI is importable, and those are the ones that matter: the
schema name, the default traceability, a cite emitted by the real RCI and admitted
by CSE, and **that the two repositories' independent `canonical_digest`
implementations agree** on key order, unicode, negative zero and extreme floats. A
cite's digest is computed in one repository and verified in the other; if those
ever diverged, every cite would fail verification for a reason no message would
explain.
