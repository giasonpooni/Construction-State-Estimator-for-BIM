"""Consume a declared ``u_c`` from an RCI uncertainty budget. Compute none.

The seam between a metrology package and an estimator, kept narrow on purpose.

    RCI      owns uncertainty-budget-v1: Type A and Type B components, the GUM
             law of propagation, Welch-Satterthwaite, coverage factors, and a
             Monte Carlo cross-check.
    CSE      sees one number. ``u_c`` arrives as ``noise_sigma`` and nothing
             else crosses.

So CSE does not become a metrology package, and RCI does not become an
estimator. Nothing here recomputes a budget, re-weights a component, or forms
an interval -- if this module ever needs to, the seam is in the wrong place.

**No import.** The portfolio rule is "each repo keeps local I; none import
another runtime". This reads JSON and mirrors the schema name, the same
agreement-not-import pattern as the JSPT ownership pin and the PLSR constants in
``gat/harness/stitch.py``. ``BUDGET_SCHEMA`` is asserted equal to
``instrument_chain.uncertainty_budget.SCHEMA`` by
``tests/test_budget_cite.py`` wherever RCI is importable, and every record
written here names the schema it applied so a reader can detect skew without
having RCI at all.

**What it refuses.**

* A budget whose ``traceability`` is anything but ``none_claimed``. CSE cannot
  verify a traceability chain, so accepting a record that asserts one would
  launder the claim -- the estimator would be repeating a statement about
  national standards that nothing in this repository checked. A traceable
  budget is not *worse*; it is simply not admissible through a seam this thin.
* A cite whose digest does not match the budget it names. A cite carries ``u_c``
  so a reader need not re-derive it, which means a cite could disagree with its
  own budget. It may not.
* A unit that is not the target slot's unit. A ``u_c`` in millimetres is not a
  sigma on a metre-valued quantity, and converting it here would be CSE
  inventing a unit conversion the budget did not declare.
* A measurand that is not the quantity the bind names. This is the rule from
  ``docs/cse-point-bind-v1.md``: an observation reaches the kernel only after a
  bind names the quantity, so a budget for ``Width`` cannot condition
  ``Height``.
* A bind with no ``quantity``. Naming the entity is not naming the slot.
* A non-positive or non-finite ``u_c``. Zero would claim an exact measurement.

What it does not claim: an admitted budget is still not field evidence, and a
cite does not close ``evidence.as_built``. It sets the noise on one observation.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Mapping

from gat.adapters.external_commitment import canonical_digest
from gat.engine.transform import ObserveQuantity
from gat.errors import GatError
from gat.ids import VarId
from gat.harness.point_bind import bind_point

#: Mirrored from instrument_chain.uncertainty_budget.SCHEMA. Not imported.
BUDGET_SCHEMA = "uncertainty-budget-v1"

#: Mirrored from the same module. RCI's Budget defaults to this and CSE admits
#: only this: see the module docstring on why a traceable budget is refused
#: rather than promoted.
ADMISSIBLE_TRACEABILITY = "none_claimed"

CITE_SCHEMA = "cse-budget-cite-v1"
CLAIM_SCOPE = "record-integrity-only"

#: The RCI commit whose uncertainty_budget was read for these values. A
#: verification pin, not an origin claim -- the same discipline as
#: gat/harness/stitch.py's MIRRORED_AT.
MIRRORED_SOURCE = "giasonpooni/Retrofitted-Computational-Instrumentation"
MIRRORED_MODULE = "instrument_chain.uncertainty_budget"


class BudgetCiteError(GatError):
    """A budget cannot be admitted as a noise term. Nothing is observed."""


@dataclass(frozen=True)
class AdmittedBudget:
    """One declared combined standard uncertainty, admitted as a noise term."""

    measurand: str
    unit: str
    u_c: float
    traceability: str
    budget_digest: str
    component_count: int

    def as_dict(self) -> dict[str, object]:
        return {
            "schema": CITE_SCHEMA,
            "claim_scope": CLAIM_SCOPE,
            "measurand": self.measurand,
            "unit": self.unit,
            "u_c": self.u_c,
            "traceability": self.traceability,
            "budget_digest": self.budget_digest,
            "component_count": self.component_count,
            "law_applied": {
                "budget_schema": BUDGET_SCHEMA,
                "mirrored_module": MIRRORED_MODULE,
                "mirrored_from": MIRRORED_SOURCE,
                "note": (
                    "u_c was read, not recomputed. CSE combines no components "
                    "and forms no interval."
                ),
            },
            "not_claimed": [
                "an admitted budget is not field evidence",
                "a budget cite does not close evidence.as_built",
                "u_c is a noise term on one observation, not a property of the world",
                "CSE did not verify traceability and admits only none_claimed",
            ],
        }


def budget_digest(document: Mapping[str, object]) -> str:
    """Canonical digest of a budget record, over the fields that define it.

    Deliberately excludes the derived reporting fields -- ``k``, ``U``, ``p``,
    ``contributions``, ``dof_eff`` -- so a budget reported at 95% and the same
    budget reported at 99% have one identity. Two budgets with the same
    components and the same combination *are* the same budget.
    """
    payload = {
        "schema": document.get("schema"),
        "measurand": document.get("measurand"),
        "unit": document.get("unit"),
        "components": document.get("components"),
        "correlations": document.get("correlations"),
        "combination": document.get("combination"),
        "u_c": document.get("u_c"),
        "traceability": document.get("traceability"),
    }
    try:
        return canonical_digest(payload)
    except ValueError as exc:
        # canonical_digest sets allow_nan=False, so a NaN or infinity anywhere in
        # the document -- including buried in a component, which the field checks
        # above never look at -- surfaced as "Out of range float values are not
        # JSON compliant" from the JSON encoder. True, and useless: it names
        # neither the budget nor the component.
        raise BudgetCiteError(
            "budget contains a non-finite number and cannot be digested; every "
            "component value must be finite. A NaN in a component is not a wide "
            f"uncertainty, it is an absent one ({exc})"
        ) from exc


def read_budget(document: Mapping[str, object]) -> AdmittedBudget:
    """Admit a ``uncertainty-budget-v1`` record, or refuse with a reason."""
    if not isinstance(document, Mapping):
        raise BudgetCiteError("budget must be a JSON object")
    schema = document.get("schema")
    if schema != BUDGET_SCHEMA:
        raise BudgetCiteError(
            f"budget schema must be {BUDGET_SCHEMA!r}, got {schema!r}; CSE reads "
            "RCI's record and computes no budget of its own"
        )
    traceability = document.get("traceability")
    if traceability != ADMISSIBLE_TRACEABILITY:
        raise BudgetCiteError(
            f"budget declares traceability {traceability!r}; CSE admits only "
            f"{ADMISSIBLE_TRACEABILITY!r} because it cannot verify a traceability "
            "chain, and repeating an unverified one would launder it"
        )
    measurand = document.get("measurand")
    if not isinstance(measurand, str) or not measurand.strip():
        raise BudgetCiteError("budget needs a non-empty measurand")
    unit = document.get("unit")
    if not isinstance(unit, str) or not unit.strip():
        raise BudgetCiteError(
            "budget needs a declared unit; a bare number is not a sigma on a "
            "quantity"
        )
    u_c = document.get("u_c")
    if isinstance(u_c, bool) or not isinstance(u_c, (int, float)):
        raise BudgetCiteError("budget u_c must be a number")
    u_c = float(u_c)
    if math.isnan(u_c):
        raise BudgetCiteError(
            "budget u_c is NaN; that is an absent uncertainty, not a wide one, and "
            "an absent one cannot be a noise term"
        )
    if math.isinf(u_c):
        raise BudgetCiteError(
            "budget u_c is infinite; an unbounded uncertainty is a refusal to "
            "state one, and conditioning on it would leave the prior unchanged "
            "while recording that evidence arrived"
        )
    if u_c <= 0.0:
        raise BudgetCiteError(
            f"budget u_c must be positive, got {u_c!r}; zero would claim an exact "
            "measurement, which no instrument delivers"
        )
    components = document.get("components")
    if not isinstance(components, list) or not components:
        raise BudgetCiteError(
            "budget declares no components; RCI refuses an empty budget and so "
            "does this"
        )
    return AdmittedBudget(
        measurand=measurand.strip(),
        unit=unit.strip(),
        u_c=u_c,
        traceability=traceability,
        budget_digest=budget_digest(document),
        component_count=len(components),
    )


def check_cite(cite: Mapping[str, object], budget: Mapping[str, object]) -> AdmittedBudget:
    """Verify a cite against the budget it names.

    A cite carries ``u_c`` so a reader need not re-derive it. That convenience is
    also a way for a cite to disagree with its own budget, so both the digest and
    the value are checked.
    """
    admitted = read_budget(budget)
    declared = cite.get("budget_digest")
    if declared != admitted.budget_digest:
        raise BudgetCiteError(
            f"cite names budget_digest {declared!r} but the budget supplied "
            f"digests to {admitted.budget_digest!r}"
        )
    if "u_c" in cite:
        cited = cite.get("u_c")
        if isinstance(cited, bool) or not isinstance(cited, (int, float)):
            raise BudgetCiteError("cited u_c must be a number")
        if float(cited) != admitted.u_c:
            raise BudgetCiteError(
                f"cite reports u_c {cited!r} but its budget combines to "
                f"{admitted.u_c!r}"
            )
    return admitted


def observe_from_budget(
    var: VarId,
    value: float,
    budget: Mapping[str, object],
    *,
    bind: Mapping[str, object],
    slot_unit: str,
    cite: Mapping[str, object] | None = None,
) -> tuple[ObserveQuantity, dict[str, object]]:
    """Turn a declared ``u_c`` into one observation, or refuse.

    Returns the transform and the record of what was admitted. The transform is
    an ordinary :class:`ObserveQuantity`; nothing about it is special, which is
    the point -- the kernel sees a float.

    ``bind`` is a complete ``cse-point-bind-v1`` record. An observation reaches the
    kernel only after a bind names the quantity, so the bind is required here
    rather than checked by a caller who might forget.
    """
    admitted = check_cite(cite, budget) if cite is not None else read_budget(budget)

    if not isinstance(bind, Mapping):
        raise BudgetCiteError("bind must be a cse-point-bind-v1 record")
    try:
        validated_bind = bind_point(bind)
    except ValueError as exc:
        raise BudgetCiteError(f"invalid observation bind: {exc}") from exc
    for field in ("point_id", "global_id", "ifc_class"):
        if field in bind and bind[field] != getattr(validated_bind, field):
            raise BudgetCiteError(f"bind header {field} disagrees with its payload")
    if (validated_bind.global_id != var.entity.global_id or
            validated_bind.ifc_class != var.entity.ifc_class):
        raise BudgetCiteError(
            "the bind names another entity; its Ifc class and GlobalId must "
            "match the observation target"
        )
    quantity = validated_bind.quantity
    if not isinstance(quantity, str) or not quantity.strip():
        raise BudgetCiteError(
            "the bind names no quantity, so there is no slot for this budget to "
            "condition; naming the entity is not naming the quantity "
            "(docs/cse-point-bind-v1.md)"
        )
    quantity = quantity.strip()
    if quantity != admitted.measurand:
        raise BudgetCiteError(
            f"the bind names quantity {quantity!r} and the budget measures "
            f"{admitted.measurand!r}; a budget for one quantity does not "
            "condition another"
        )
    if quantity != var.quantity:
        raise BudgetCiteError(
            f"the bind names quantity {quantity!r} but the observation targets "
            f"{var.quantity!r}"
        )
    if admitted.unit != slot_unit:
        raise BudgetCiteError(
            f"budget unit {admitted.unit!r} is not the slot's unit "
            f"{slot_unit!r}; CSE does not convert a declared uncertainty"
        )

    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise BudgetCiteError("observed value must be a number")
    value = float(value)
    if not math.isfinite(value):
        raise BudgetCiteError("observed value must be finite")

    record = admitted.as_dict()
    record["observed"] = {
        "var": str(var),
        "value": value,
        "noise_sigma": admitted.u_c,
        "bind_point_id": validated_bind.point_id,
        "bind_global_id": validated_bind.global_id,
        "bind_ifc_class": validated_bind.ifc_class,
        "bind_digest": validated_bind.digest,
    }
    return ObserveQuantity.single(var, value, admitted.u_c), record
