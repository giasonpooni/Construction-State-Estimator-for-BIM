"""Declared effort table for satellite gates.

Satellite. Python is dry-run authority for python_uv only.
Live INVOKE for rust/cuda/sp1 belongs to rust/effort_gate.
Does not run SP1, CUDA, or Rust. Does not touch Beam-B1.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import math
from pathlib import Path
from typing import Mapping

from gat.adapters.external_commitment import canonical_digest

EFFORT_FORMAT = "satellite-effort-v1"
PYTHON_AUTHORITY = "python"
RUST_AUTHORITY = "rust-effort-gate"
KNOWN_SATELLITES = frozenset(
    {
        "python_uv",
        "rust_ingest",
        "cuda_jspt",
        "sp1_zkvm",
        "dense_sigma_rebuild",
    }
)
_DEFAULT_TABLE = (
    Path(__file__).resolve().parents[2] / "validation" / "satellite-effort-v1.json"
)


@dataclass(frozen=True)
class EffortDecision:
    satellite: str
    disposition: str
    cost_nats: float | None
    expected_information_nats: float | None
    hole: str | None
    reason: str
    allowed: bool
    authority: str

    def as_policy(self) -> dict[str, object]:
        return {
            "type": "policy",
            "satellite": self.satellite,
            "disposition": self.disposition,
            "cost_nats": self.cost_nats,
            "expected_information_nats": self.expected_information_nats,
            "hole": self.hole,
            "reason": self.reason,
            "allowed": self.allowed,
            "authority": self.authority,
            "world_digest_unchanged": True,
            "invoked": False,
        }


def _read_object(path: str | Path) -> dict[str, object]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return raw


def load_effort_table(path: str | Path | None = None) -> dict[str, object]:
    table = _read_object(path or _DEFAULT_TABLE)
    if table.get("format") != EFFORT_FORMAT:
        raise ValueError("effort table format must be satellite-effort-v1")
    satellites = table.get("satellites")
    if not isinstance(satellites, dict) or not satellites:
        raise ValueError("effort table must declare satellites")
    unknown = set(satellites) - KNOWN_SATELLITES
    if unknown:
        raise ValueError(f"unknown satellites in effort table: {sorted(unknown)}")
    return table


def _entry(table: Mapping[str, object], name: str) -> dict[str, object]:
    satellites = table.get("satellites")
    if not isinstance(satellites, dict):
        raise ValueError("effort table satellites must be an object")
    raw = satellites.get(name)
    if not isinstance(raw, dict):
        raise ValueError(f"unknown satellite {name}")
    return raw


def decide_satellite(
    table: Mapping[str, object],
    name: str,
    *,
    hole: str | None = None,
    expected_information_nats: float | None = None,
    caller_authority: str = PYTHON_AUTHORITY,
) -> EffortDecision:
    if name not in KNOWN_SATELLITES:
        return EffortDecision(
            satellite=name,
            disposition="REFUSE",
            cost_nats=None,
            expected_information_nats=expected_information_nats,
            hole=hole,
            reason="unknown satellite",
            allowed=False,
            authority=caller_authority,
        )
    entry = _entry(table, name)
    row_authority = str(entry.get("authority") or PYTHON_AUTHORITY)
    allowed = bool(entry.get("allowed"))
    cost = entry.get("cost_nats")
    cost_ok = isinstance(cost, (int, float)) and math.isfinite(float(cost)) and float(cost) >= 0.0
    cost_value = float(cost) if cost_ok else None
    if row_authority != caller_authority:
        return EffortDecision(
            satellite=name,
            disposition="REFUSE",
            cost_nats=cost_value,
            expected_information_nats=expected_information_nats,
            hole=hole,
            reason=f"authority is {row_authority}",
            allowed=allowed,
            authority=caller_authority,
        )
    if not cost_ok:
        return EffortDecision(
            satellite=name,
            disposition="REFUSE",
            cost_nats=None,
            expected_information_nats=expected_information_nats,
            hole=hole,
            reason="cost_nats missing or not finite",
            allowed=False,
            authority=caller_authority,
        )
    if not allowed:
        return EffortDecision(
            satellite=name,
            disposition="REFUSE",
            cost_nats=cost_value,
            expected_information_nats=expected_information_nats,
            hole=hole,
            reason="allowed is false",
            allowed=False,
            authority=caller_authority,
        )
    info_ok = (
        expected_information_nats is not None
        and math.isfinite(expected_information_nats)
        and expected_information_nats >= 0.0
    )
    if not hole or not info_ok:
        return EffortDecision(
            satellite=name,
            disposition="DEFER",
            cost_nats=cost_value,
            expected_information_nats=expected_information_nats,
            hole=hole,
            reason="need a named hole and finite expected information",
            allowed=True,
            authority=caller_authority,
        )
    assert cost_value is not None
    if expected_information_nats - cost_value <= 0.0:
        return EffortDecision(
            satellite=name,
            disposition="DEFER",
            cost_nats=cost_value,
            expected_information_nats=expected_information_nats,
            hole=hole,
            reason="I - c <= 0",
            allowed=True,
            authority=caller_authority,
        )
    return EffortDecision(
        satellite=name,
        disposition="INVOKE",
        cost_nats=cost_value,
        expected_information_nats=expected_information_nats,
        hole=hole,
        reason="declared information exceeds declared cost",
        allowed=True,
        authority=caller_authority,
    )


def effort_slice(
    table: Mapping[str, object],
    decisions: list[EffortDecision],
    *,
    source: str | None = None,
) -> dict[str, object]:
    payload = {
        "format": EFFORT_FORMAT,
        "claim_scope": table.get("claim_scope") or "gate-policy-only",
        "source": source,
        "table_digest": canonical_digest(
            {k: v for k, v in table.items() if k != "digest"}
        ),
        "decisions": [row.as_policy() for row in decisions],
        "note": "Python is dry-run. rust-effort-gate is live authority for rust-gated satellites.",
    }
    return payload
