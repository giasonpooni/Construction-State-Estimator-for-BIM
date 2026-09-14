"""Design compliance under geometric uncertainty.

Every rule is a *margin*: a scalar that must be positive for the design to
comply.  The margin's mean and standard deviation are evaluated under the
full joint belief (delta method through the engine's Jacobian rows), and
the report gives the probability of satisfaction ``P = Phi(mu_m / sigma_m)``
plus a status:

    PASS      P >= pass_p       (default 0.9987 — 3 sigma)
    MARGINAL  fail_p < P < pass_p
    FAIL      P <= fail_p       (default 0.5)

A report is ``SATISFIED`` only when a rule applied and every rule passed.
One ``MARGINAL`` row leaves it ``UNRESOLVED``, and so does a world no rule
reached: "nothing was checked" is not "nothing is wrong".

Shipped rules (v0): dimensional clearances from the module's LessEqual
constraints, minimum room area, and minimum ceiling clear height.  Rules
share their margin definitions with the chance-constraint penalties in
:mod:`gat.geometry.objectives`, so what the optimizer pushes on is exactly
what compliance measures.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from gat.engine.executor import World
from gat.geometry.overlap import normal_cdf
from gat.ids import VarId
from gat.ir.core import LessEqual


@dataclass(frozen=True)
class ComplianceRow:
    rule: str
    subject: str
    margin_mean: float
    margin_sigma: float
    p_satisfied: float
    status: str

    def render(self) -> str:
        return (
            f"{self.status:<8} {self.rule:<24} {self.subject:<40} "
            f"margin {self.margin_mean:+.4f} +- {self.margin_sigma:.4f}  "
            f"P {self.p_satisfied:.4f}"
        )


@dataclass(frozen=True)
class ComplianceReport:
    rows: tuple[ComplianceRow, ...]

    @property
    def status(self) -> str:
        """``SATISFIED``, ``VIOLATED``, or ``UNRESOLVED``.

        The runtime's own vocabulary, for the two cases a boolean cannot
        carry.  A ``MARGINAL`` row is a margin this belief could not settle
        — at ``P = 0.5040`` it is a coin toss, not a pass.  A report with no
        rows settled nothing at all: ``all(())`` is ``True``, so an empty
        report used to read as compliance, and a model with no applicable
        rule exited clean.  Neither is a pass here.
        """
        if any(r.status == "FAIL" for r in self.rows):
            return "VIOLATED"
        if not self.rows or any(r.status != "PASS" for r in self.rows):
            return "UNRESOLVED"
        return "SATISFIED"

    @property
    def passed(self) -> bool:
        """True only when a rule applied and every one of them is PASS."""
        return self.status == "SATISFIED"

    @property
    def unresolved(self) -> tuple[ComplianceRow, ...]:
        """Rows that neither passed nor failed — what to measure next."""
        return tuple(r for r in self.rows if r.status == "MARGINAL")

    def render(self) -> str:
        counts: dict[str, int] = {}
        for r in self.rows:
            counts[r.status] = counts.get(r.status, 0) + 1
        head = "compliance: " + ", ".join(
            f"{counts.get(s, 0)} {s.lower()}" for s in ("PASS", "MARGINAL", "FAIL")
        )
        status = self.status
        if status == "SATISFIED":
            verdict = f"-> SATISFIED  {len(self.rows)} rules, all above the pass bar"
        elif status == "VIOLATED":
            failing = [r for r in self.rows if r.status == "FAIL"]
            verdict = f"-> VIOLATED   {len(failing)} rule(s) below the fail bar"
        elif not self.rows:
            verdict = (
                "-> UNRESOLVED no compliance rule applied to this world; "
                "nothing was established"
            )
        else:
            # Every row that is not a pass, not only the canonical MARGINAL:
            # status is an unvalidated str on a public dataclass, and render()
            # is the fail-path formatter -- the one function that must not
            # raise on its way to reporting a problem.
            unsettled = [r for r in self.rows if r.status != "PASS"]
            worst = min(unsettled, key=lambda r: r.p_satisfied)
            verdict = (
                f"-> UNRESOLVED {len(unsettled)} margin(s) the belief "
                f"cannot settle; weakest {worst.rule} at P {worst.p_satisfied:.4f}"
            )
        return "\n".join([head] + [r.render() for r in self.rows] + [verdict])


def _status(p: float, pass_p: float, fail_p: float) -> str:
    if p >= pass_p:
        return "PASS"
    if p <= fail_p:
        return "FAIL"
    return "MARGINAL"


def _margin_row(
    world: World,
    rule: str,
    subject: str,
    mean: float,
    variance: float,
    pass_p: float,
    fail_p: float,
) -> ComplianceRow:
    sigma = math.sqrt(max(variance, 0.0))
    if sigma > 1e-12:
        p = float(normal_cdf(mean / sigma))
    else:
        p = 1.0 if mean >= 0 else 0.0
    return ComplianceRow(rule, subject, mean, sigma, p, _status(p, pass_p, fail_p))


def check_compliance(
    world: World,
    min_room_area: float = 7.0,
    min_clear_height: float = 2.4,
    pass_p: float = 0.9987,
    fail_p: float = 0.5,
) -> ComplianceReport:
    rows: list[ComplianceRow] = []
    full = world.full

    # 1. Dimensional clearances from the module's typed constraints.
    for c in world.module.constraints:
        if not isinstance(c, LessEqual):
            continue
        mean = full.mean(c.rhs) - full.mean(c.lhs)
        var = full.var_of(c.rhs) + full.var_of(c.lhs) - 2.0 * full.cov(c.rhs, c.lhs)
        rows.append(
            _margin_row(
                world, "clearance", f"{c.lhs} <= {c.rhs}", mean, var, pass_p, fail_p
            )
        )

    # 2. Minimum room area / clear height per space.
    storeys = [e for e in world.module.entities if e.ifc_class == "IfcBuildingStorey"]
    ch_var = VarId(storeys[0], "ClearHeight") if storeys else None
    for eid in world.module.entities:
        if eid.ifc_class != "IfcSpace":
            continue
        area = VarId(eid, "FloorArea")
        rows.append(
            _margin_row(
                world,
                "min-room-area",
                f"{eid} >= {min_room_area} m2",
                full.mean(area) - min_room_area,
                full.var_of(area),
                pass_p,
                fail_p,
            )
        )
        if ch_var is not None:
            rows.append(
                _margin_row(
                    world,
                    "min-clear-height",
                    f"{eid} >= {min_clear_height} m",
                    full.mean(ch_var) - min_clear_height,
                    full.var_of(ch_var),
                    pass_p,
                    fail_p,
                )
            )

    return ComplianceReport(tuple(rows))
