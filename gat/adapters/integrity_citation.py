"""Integrity citations for team packets.

A citation is a digest pointer. It is not a proof, not an Observe, and not
a USD customData blob of proof bytes.
"""

from __future__ import annotations

from typing import Mapping

from gat.proof_manifest import PROOF_CLAIM_SCOPE
from gat.sp1_kernel import CALLBACK_ID, CLAIM_SCOPE, statement_digest

CITATION_SCHEMA = "cse-integrity-citation-v1"


def kernel_citation(*, locator: str = "kernel_sp1_receipt.json", is_proof: bool = False) -> dict[str, object]:
    if CLAIM_SCOPE != PROOF_CLAIM_SCOPE:
        raise RuntimeError("kernel claim scope drifted from the manifest contract")
    return {
        "schema": CITATION_SCHEMA,
        "kind": CALLBACK_ID,
        "claim_scope": CLAIM_SCOPE,
        "statement_digest": statement_digest(),
        "locator": locator,
        "is_proof": bool(is_proof),
        "in_usd_bytes": False,
        "conditions_belief": False,
        "may_authorize": False,
    }


def validate_citation(document: Mapping[str, object]) -> dict[str, object]:
    if document.get("schema") != CITATION_SCHEMA:
        raise ValueError("citation schema must be cse-integrity-citation-v1")
    digest = document.get("statement_digest")
    if not isinstance(digest, str) or len(digest) != 64:
        raise ValueError("statement_digest must be a 64-char hex digest")
    if document.get("claim_scope") != CLAIM_SCOPE:
        raise ValueError("citation must stay computational-integrity-only")
    if document.get("in_usd_bytes") is True:
        raise ValueError("proof bytes must not live in USD")
    if document.get("conditions_belief") is True:
        raise ValueError("a citation must not condition belief")
    if document.get("may_authorize") is True:
        raise ValueError("a citation must not authorize")
    return dict(document)
