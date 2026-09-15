"""Apply geometry authority after the numerical acceptance policy.

This wrapper is the public evaluate path. Gaussianized clearance without
openings subtracted cannot close an as-built case. A verified scan receipt
upgrades that check to SCAN_GMM.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from gat.workflows.acceptance import (
    AcceptanceCheck,
    AcceptanceCheckKind,
    AcceptanceDisposition,
    AcceptanceOutcome,
    AcceptancePolicy,
    EvidenceReceipt,
    EvidenceRequest,
)
from gat.workflows.acceptance import (
    evaluate_acceptance_case as evaluate_acceptance_case_ungated,
)
from gat.engine.verify import (  # noqa: F401  (VerificationReport: annotation)
    DEFAULT_INVARIANT_CONFIDENCE,
    VerificationReport,
)
from gat.workflows.geometry_authority import (
    GeometryAuthority,
    geometry_sufficient,
)


def check_geometry_authority(check: AcceptanceCheck) -> GeometryAuthority:
    raw = check.details.get("geometry_authority")
    if raw is not None:
        return GeometryAuthority(str(raw))
    if check.kind is AcceptanceCheckKind.CLEARANCE:
        return GeometryAuthority.GAUSSIAN_PROXY
    if check.kind is AcceptanceCheckKind.CAPACITY:
        # A capacity verdict has no safe default support. Dimensional
        # quantities do not establish a section modulus, so an undeclared
        # capacity check is insufficient rather than QUANTITY_ONLY.
        return GeometryAuthority.INSUFFICIENT
    return GeometryAuthority.QUANTITY_ONLY


def annotate_check(check: AcceptanceCheck) -> dict[str, object]:
    from gat.workflows.acceptance import acceptance_check_dict

    payload = acceptance_check_dict(check)
    payload["geometry_authority"] = check_geometry_authority(check).value
    return payload


@dataclass(frozen=True)
class GatedAcceptanceOutcome:
    """AcceptanceOutcome plus geometry-authority fields on the contract."""

    base: AcceptanceOutcome
    disposition: AcceptanceDisposition
    reasons: tuple[str, ...]
    evidence_requests: tuple[EvidenceRequest, ...]
    insufficient_geometry_check_ids: tuple[str, ...]
    #: Constraints that hold at the mean but not across enough of the
    #: posterior to rely on, as ``(subject, p_holds)``. Empty when no
    #: verification report was supplied.
    variant_constraints: tuple[tuple[str, float], ...] = ()
    #: Invariants this world outright fails, as ``(invariant_id, subject)``.
    #: A world that fails its own invariants cannot authorize anything.
    failed_invariants: tuple[tuple[str, str], ...] = ()

    def __getattr__(self, name: str) -> object:
        return getattr(self.base, name)

    @property
    def may_authorize(self) -> bool:
        return self.disposition is AcceptanceDisposition.ACCEPT

    def to_dict(self) -> dict[str, object]:
        payload = self.base.to_dict()
        payload["disposition"] = self.disposition.value
        payload["may_authorize"] = self.may_authorize
        payload["reasons"] = list(self.reasons)
        payload["insufficient_geometry_check_ids"] = list(
            self.insufficient_geometry_check_ids
        )
        payload["variant_constraints"] = [
            {"subject": subject, "p_holds": p_holds}
            for subject, p_holds in self.variant_constraints
        ]
        payload["failed_invariants"] = [
            {"invariant_id": invariant_id, "subject": subject}
            for invariant_id, subject in self.failed_invariants
        ]
        payload["evidence_requests"] = [
            {
                "check_id": request.check_id,
                "action": request.action,
                "target": request.target,
                "reason": request.reason,
                "priority": request.priority,
            }
            for request in self.evidence_requests
        ]
        payload["checks"] = [annotate_check(check) for check in self.base.case.checks]
        return payload


def evaluate_acceptance_case(
    case,
    receipts: Iterable[EvidenceReceipt] = (),
    requests: Iterable[EvidenceRequest] = (),
    policy: AcceptancePolicy = AcceptancePolicy(),
    verification: "VerificationReport | None" = None,
) -> GatedAcceptanceOutcome:
    """Apply the case policy, the geometry gate, and the invariant gate.

    ``verification`` is the report for the world the checks were scored on.
    Supply it and a constraint that is merely *variant* -- true of the mean,
    but not of enough of the posterior -- blocks authorization and becomes an
    evidence request. Omit it and the invariant gate simply does not run,
    which is the pre-existing behaviour.
    """
    receipts = tuple(receipts)
    outcome = evaluate_acceptance_case_ungated(case, receipts, requests, policy)
    scan_covered: set[str] = set()
    for receipt in receipts:
        if (
            receipt.verification_passed
            and receipt.evidence_kind == "calibrated-scan-clearance-likelihood"
        ):
            scan_covered.update(receipt.check_ids)

    require_geometry = getattr(policy, "require_sufficient_geometry_for_accept", True)
    insufficient = (
        tuple(
            check.check_id
            for check in case.checks
            if not geometry_sufficient(
                check.kind.value,
                check_geometry_authority(check),
                scan_covered=check.check_id in scan_covered,
            )
        )
        if require_geometry
        else ()
    )

    require_invariants = getattr(
        policy, "require_invariant_constraints_for_accept", True
    )
    variant: tuple[tuple[str, float], ...] = ()
    failed: tuple[tuple[str, str], ...] = ()
    stale_report = ""
    if verification is not None:
        failed = tuple(
            (result.invariant_id, result.subject) for result in verification.failures
        )
        # Classify against the confidence *this policy* declared, not against
        # whatever the caller happened to hand ``run_invariants``. Reading the
        # warnings as-is took the report's own threshold, so a policy asking
        # for 0.999 silently accepted a constraint holding at 0.98 while
        # recording the stricter number.
        confidence = getattr(
            policy, "invariant_confidence", DEFAULT_INVARIANT_CONFIDENCE
        )
        report_confidence = getattr(
            verification, "confidence", DEFAULT_INVARIANT_CONFIDENCE
        )
        if confidence > report_confidence + 1e-12:
            # Narrowing a report is sound; widening it is not. Below its own
            # threshold a passing probabilistic invariant is one aggregate row
            # carrying the tightest p_holds, so the constraints between the
            # two thresholds are not in this report to be found. Say so.
            stale_report = (
                f"verification was classified at {report_confidence:.6f} but "
                f"this policy requires {confidence:.6f}; re-run the invariants "
                "at the policy's confidence -- a report cannot be tightened "
                "after the fact"
            )
        else:
            stale_report = ""
            variant = tuple(
                (result.subject, result.p_holds)
                for result in verification.warnings
                if result.p_holds is not None and result.p_holds < confidence
            )

    disposition = outcome.disposition
    reasons = list(outcome.reasons)
    generated = list(outcome.evidence_requests)

    if stale_report and disposition is AcceptanceDisposition.ACCEPT:
        disposition = AcceptanceDisposition.REQUEST_EVIDENCE
        reasons.append(stale_report)

    if failed:
        # A world that fails its own invariants cannot be accepted, and asking
        # for evidence would misdescribe the problem: this is not a gap in what
        # was measured. Until this branch existed the gate read only
        # ``warnings``, so a constraint VIOLATED at the mean reached ACCEPT
        # while one merely variant at P = 0.97 did not -- strictly stronger on
        # the weaker evidence.
        disposition = AcceptanceDisposition.REJECT
        reasons.append(
            f"{len(failed)} invariant(s) fail on this world: "
            + ", ".join(sorted({invariant_id for invariant_id, _ in failed}))
        )

    if variant and require_invariants and disposition is AcceptanceDisposition.ACCEPT:
        disposition = AcceptanceDisposition.REQUEST_EVIDENCE
        worst = min(p for _, p in variant)
        reasons.append(
            f"{len(variant)} constraint(s) hold at the mean but not across the "
            f"posterior; the weakest holds with P = {worst:.6f}"
        )
    if variant and disposition is not AcceptanceDisposition.REJECT:
        known = {request.check_id for request in generated}
        # Weakest first, and one request each. A single shared request id
        # deduplicated every constraint after the first, so a case with three
        # variant constraints asked about one of them -- in report order, so
        # usually not the one that needed measuring most.
        for index, (subject, p_holds) in enumerate(
            sorted(variant, key=lambda item: (item[1], item[0]))
        ):
            # A variant constraint is not owned by any one check, so the
            # request is raised against the case itself.
            request_id = f"{case.case_id}:variant:{index}"
            if request_id in known:
                continue
            generated.append(
                EvidenceRequest(
                    request_id,
                    "MEASURE_VARIANT_CONSTRAINT",
                    subject,
                    (
                        "this constraint holds at the mean but only with "
                        f"P = {p_holds:.6f}; measure its variables to make it "
                        "invariant or to refute it"
                    ),
                    priority=1.0 - p_holds,
                )
            )
            known.add(request_id)

    if insufficient and disposition is AcceptanceDisposition.ACCEPT:
        disposition = AcceptanceDisposition.REQUEST_EVIDENCE
        reasons.append(
            "one or more checks lack geometric authority to close the case"
        )
    if insufficient and disposition is not AcceptanceDisposition.REJECT:
        known = {request.check_id for request in generated}
        for check in case.checks:
            if check.check_id in insufficient and check.check_id not in known:
                generated.append(
                    EvidenceRequest(
                        check.check_id,
                        "ACQUIRE_CALIBRATED_EVIDENCE",
                        check.subject,
                        (
                            "geometry authority is insufficient for this check; "
                            f"current support is {check_geometry_authority(check).value}"
                        ),
                    )
                )

    # Both gates may have appended; order the whole set once, highest
    # priority first, so the caller sees a single ranked ask.
    generated.sort(key=lambda item: (-item.priority, item.check_id, item.action))

    return GatedAcceptanceOutcome(
        base=outcome,
        disposition=disposition,
        reasons=tuple(reasons),
        evidence_requests=tuple(generated),
        insufficient_geometry_check_ids=insufficient,
        variant_constraints=variant,
        failed_invariants=failed,
    )


# -- why the base module's name is rebound ---------------------------------
#
# `acceptance.evaluate_acceptance_case` applies the numerical policy and
# nothing else: it scores verdicts and evidence coverage, and it neither
# knows nor asks whether a check had the geometric authority to close the
# case. On its own that is a correct layer and a dangerous export -- the two
# functions share a name, and `from gat.workflows.acceptance import
# evaluate_acceptance_case` reads exactly like the safe one.
#
# So the base name is rebound to the gated evaluator, and the numerical layer
# stays reachable under the explicit name `evaluate_acceptance_case_ungated`,
# which is captured above before this line runs. Importing
# `gat.workflows.acceptance` at all executes `gat/workflows/__init__.py`
# first, which imports this module, so the rebinding is in place before any
# caller can see the original.
#
# It is a safety net for callers who reach past the package, not a mechanism
# anything should rely on: a caller that wants the gate should ask for it by
# name, from `gat.workflows`. `gat.headless` does exactly that, because a
# boundary taking untrusted JSON must not need an import side effect to be
# safe. `tests.test_geometry_authority` holds both halves -- that every public
# path is gated, and that the boundary stays gated with this line undone.
#
# Note the return type changes with the name: callers of the rebound name get
# a `GatedAcceptanceOutcome`, which carries `AcceptanceOutcome`'s fields plus
# the geometry and invariant findings.
import gat.workflows.acceptance as _acceptance_module

_acceptance_module.evaluate_acceptance_case = evaluate_acceptance_case  # type: ignore[misc]
