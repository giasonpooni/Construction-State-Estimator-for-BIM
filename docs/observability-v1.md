# Observability v1 — which coordinates the evidence reaches

```text
Lambda = Sigma_post^-1 - Sigma_prior^-1        information the evidence added
rank(Lambda)                                   independent directions constrained
Lambda[i,i] == 0                               coordinate i has no channel
```

The runtime conditions on observations and then reports `UNRESOLVED` or
`REQUEST_EVIDENCE`. What it never published is the rank story behind that: which
coordinates of the world carry information from evidence, which are still only
their declared prior, and therefore which checks cannot close however the
acceptance policy is written.

`gat/harness/observability.py` is a satellite. It reads a world and reports. It
computes no disposition, writes no belief, and moves no digest.

## Identifiability, not observability

There is no `A` here — the world does not march forward, so this is not
observability of a time-evolving system. It is identifiability of a static
linear-Gaussian state from the channels available.

And every raw coordinate has a strictly positive prior, so the posterior is
always proper: nothing is "unobservable" in the improper sense, and claiming
otherwise would be the wrong kind of alarm. The honest question is narrower.
`Lambda` is the information the evidence added. It is PSD when conditioning only
adds information, and for a PSD matrix a zero diagonal entry implies the whole
row is zero — so `Lambda[i,i] == 0` is an exact statement that coordinate `i`
received nothing, not a threshold guess. The per-coordinate floor is scaled by
each coordinate's own prior precision, because a millimetre prior and a metre
prior are not comparable in absolute precision.

## What it says about the flagship case

The pinned opening-fit disposition is `REQUEST_EVIDENCE` with both checks
`SATISFIED`, and the pin gives the reason in prose: "satisfied checks lack
verified evidence for this exact world." Measured:

```
raw coordinates : 24
informed_rank   : 0
informed        : none
```

Every check rests on a declared prior. That is the mechanical content of the
prose, and `tests/test_observability.py` asserts it against the pin.

After observing the opening width at sigma 1.6 mm:

```
informed_rank   : 1
informed        : GATOPN0000000000000200.Width   (variance reduction 0.907)
```

`Opening-1.Width` can now close on evidence; `Door-1.Width` still cannot, and
`TotalWallCost` still has seventeen uninformed dependencies out of eighteen.

## Turning a verdict into an address

```python
evidence_ticket(world, subjects)   # per subject: depends_on, uninformed, can_close_on_evidence
blocking_coordinates(world, var)   # the coordinates var rests on that nothing measured
rank_gain(world, var, variance)    # directions a direct observation would add
```

`rank_gain` is the question active inference should be asking: does this
measurement reach somewhere the evidence has not. Re-measuring an already
informed coordinate returns 0.

## Expected information is not decision relevance

`plan_coverage(world, plans, subjects)` asks the complementary question to
`plan_observations`. A candidate on `Wall-Party.Length` scores a perfectly
respectable 0.347 nats of epistemic value about the state — and reaches none of
the coordinates an opening-fit decision rests on:

```
needed    : Opening-1.Width, Door-1.Width
reached   : (none)
covers_every_gap: False
```

A plan that scores well and covers nothing is a plan to learn something the
decision does not rest on. Active inference ranks by expected free energy; this
says whether the ranking is pointed at the gap.

## What this does not do

It does not make anything acceptable. A coordinate becoming informed says a
channel reached it, not that the channel was traceable: `usable_as_field_evidence`
and geometry authority are separate gates and stay where they are. An informed
rank of one on a demo fixture is still a demo fixture.
