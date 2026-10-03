"""Read-only BIM binding for optional sampled geodesic inspection studies.

CSE owns the entity/quantity and current world. The companion owns the path
calculation. A binding or successful replay never supplies as-built evidence.
No world, ledger, disposition or equipment command is mutated here.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from typing import Any

from gat.engine.executor import World
from gat.ids import EntityId
from gat.ir.core import Unit

REQUEST_SCHEMA = "surface-inspection-request-v1"
REPORT_SCHEMA = "surface-inspection-study-v1"
SCOPE = "sampled-first-order-planning-only"
MAX_BYTES = 4 * 1024 * 1024


def _bytes(value: Any) -> bytes:
    try:
        data = json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        ).encode("utf-8")
    except (TypeError, ValueError, RecursionError, UnicodeError) as exc:
        raise ValueError("Require finite UTF-8 JSON") from exc
    if len(data) > MAX_BYTES:
        raise ValueError("Inspection document is too large")
    return data


def _digest(value: Any) -> str:
    return hashlib.sha256(_bytes(value)).hexdigest()


def _text(value: Any) -> None:
    if type(value) is not str or not 1 <= len(value) <= 256 or any(ord(c) < 32 for c in value):
        raise ValueError("Require bounded nonempty identifiers")


def _sha(value: Any) -> None:
    if type(value) is not str or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise ValueError("Require a full SHA-256 mapping digest")


def _positive(value: Any) -> bool:
    if type(value) not in (int, float):
        return False
    try:
        return math.isfinite(value) and value > 0
    except OverflowError:
        return False


def _target(world: World, entity: EntityId, quantity: str) -> None:
    if not isinstance(world, World) or not isinstance(entity, EntityId):
        raise ValueError("Require the actual CSE world and typed entity identity")
    _text(quantity)
    _text(entity.ifc_class)
    _text(entity.global_id)
    if entity not in world.module.entities:
        raise ValueError("Entity identity is not in this BIM world")
    if quantity not in world.module.entity(entity).slots:
        raise ValueError("Quantity does not exist on this BIM entity")
    if world.module.slot(world.module.entity(entity).var(quantity)).unit is not Unit.M:
        raise ValueError("This inspection profile binds only length quantities in metres")


def prepare_request(
    world: World,
    entity: EntityId,
    *,
    quantity: str,
    spatial_frame_id: str,
    mapping_digest: str,
    records: dict[str, dict[str, Any]],
    tolerance: dict[str, float],
    limits: dict[str, float],
) -> dict[str, Any]:
    """Bind caller-declared paths to a known length quantity; do not infer a mesh.

    mapping_digest identifies a separately retained operator mapping declaration.
    It is not an assertion that path points have been registered to a real scan.
    """
    _target(world, entity, quantity)
    for text in (entity.global_id, entity.ifc_class, spatial_frame_id):
        _text(text)
    _sha(mapping_digest)
    if type(records) is not dict or not 1 <= len(records) <= 16:
        raise ValueError("Require 1..16 candidate records")
    for label, record in records.items():
        _text(label)
        if type(record) is not dict:
            raise ValueError("Require serialized candidate records")
    for value, keys in (
        (tolerance, {"lateral_m", "heading_rad"}),
        (limits, {"cross_track_m", "heading_rad", "path_length_m", "wronskian_drift"}),
    ):
        if type(value) is not dict or set(value) != keys:
            raise ValueError("Require explicit tolerance and limit fields")
        if any(not _positive(v) for v in value.values()):
            raise ValueError("Require finite positive tolerance and limit values")
    _bytes(records)  # bound the complete input, not just its commitment map
    request = {
        "schema": REQUEST_SCHEMA,
        "scope": SCOPE,
        "context": {
            "world_digest": world.digest(),
            "ifc_class": entity.ifc_class,
            "global_id": entity.global_id,
            "quantity": quantity,
            "spatial_frame_id": spatial_frame_id,
            "mapping_digest": mapping_digest,
        },
        "units": {"length": "m", "angle": "radian"},
        "tolerance": tolerance,
        "limits": limits,
        "candidates": {label: _digest(value) for label, value in sorted(records.items())},
    }
    return json.loads(_bytes({**request, "request_digest": _digest(request)}))


def inspect_report(
    world: World, expected_request: dict[str, Any], report: dict[str, Any]
) -> dict[str, Any]:
    """Check identity/integrity only, without importing or running the companion.

    A deliberately rehashed numerical lie is outside this function's claim.
    Use replay_report explicitly for fresh companion numerical verification.
    """
    expected_request, report = json.loads(_bytes([expected_request, report]))
    if type(expected_request) is not dict or type(report) is not dict:
        raise ValueError("Require request and report objects")
    context = expected_request.get("context", {})
    if type(context) is not dict or set(context) != {
        "world_digest",
        "ifc_class",
        "global_id",
        "quantity",
        "spatial_frame_id",
        "mapping_digest",
    }:
        raise ValueError("Incomplete BIM context")
    entity = EntityId(context["ifc_class"], context["global_id"])
    _target(world, entity, context["quantity"])
    if context["world_digest"] != world.digest():
        raise ValueError("Stale inspection request: BIM world changed")
    # Rebuild our own expected request. Merely rehashing an invalid request is
    # insufficient, and the exact original request must be supplied separately.
    rebuilt = prepare_request(
        world,
        entity,
        quantity=context["quantity"],
        spatial_frame_id=context["spatial_frame_id"],
        mapping_digest=context["mapping_digest"],
        records=report.get("records"),
        tolerance=expected_request.get("tolerance"),
        limits=expected_request.get("limits"),
    )
    if _bytes(rebuilt) != _bytes(expected_request):
        raise ValueError("Request or candidate commitments differ")
    required = {
        "schema",
        "scope",
        "request",
        "records",
        "results",
        "ranking",
        "runtime_version",
        "numpy_version",
        "may_authorize",
        "physical_validation",
        "cryptographic_verification",
        "report_digest",
    }
    if set(report) != required or report["schema"] != REPORT_SCHEMA or report["scope"] != SCOPE:
        raise ValueError("Unsupported inspection report")
    if report["may_authorize"] is not False or any(
        report[k] != "not_performed" for k in ("physical_validation", "cryptographic_verification")
    ):
        raise ValueError("Planning report cannot claim physical/proof/action authority")
    if _bytes(report["request"]) != _bytes(expected_request):
        raise ValueError("Report is not bound to the expected request")
    if report["report_digest"] != _digest(
        {k: v for k, v in report.items() if k != "report_digest"}
    ):
        raise ValueError("Report digest mismatch")
    for key in ("runtime_version", "numpy_version"):
        _text(report[key])
    ids = set(expected_request["candidates"])
    ranking = report["ranking"]
    if (
        type(ranking) is not list
        or len(ranking) != len(ids)
        or any(type(label) is not str for label in ranking)
        or set(ranking) != ids
    ):
        raise ValueError("Incomplete or duplicate candidate ranking")
    if type(report["results"]) is not list or len(report["results"]) != len(ids):
        raise ValueError("Incomplete candidate results")
    result_ids = []
    for result in report["results"]:
        fields = {
            "candidate_id",
            "record_digest",
            "native_source_id",
            "values",
            "utilization",
            "amplification_score",
            "within_sampled_limits",
            "failed_limits",
            "validity_admits_tolerance",
            "validity_reference",
        }
        if type(result) is not dict or set(result) != fields:
            raise ValueError("Malformed candidate result")
        for name in ("values", "utilization"):
            values = result[name]
            if type(values) is not dict or set(values) != set(expected_request["limits"]):
                raise ValueError("Malformed candidate metrics")
            for value in values.values():
                if (
                    type(value) not in (int, float)
                    or value < 0
                    or not (value == 0 or _positive(value))
                ):
                    raise ValueError("Require finite nonnegative candidate metrics")
        if not _positive(result["amplification_score"]):
            raise ValueError("Require finite positive amplification score")
        for name in ("within_sampled_limits", "validity_admits_tolerance"):
            if type(result[name]) is not bool:
                raise ValueError("Require explicit boolean planning states")
        reasons = result["failed_limits"]
        allowed = set(expected_request["limits"]) | {"truncated_chart"}
        if (
            type(reasons) is not list
            or any(type(r) is not str or r not in allowed for r in reasons)
            or len(set(reasons)) != len(reasons)
            or result["within_sampled_limits"] != (not reasons)
        ):
            raise ValueError("Contradictory planning state")
        _text(result["native_source_id"])
        _text(result["validity_reference"])
        label = result.get("candidate_id")
        if (
            type(label) is not str
            or label not in ids
            or result.get("record_digest") != expected_request["candidates"][label]
        ):
            raise ValueError("Candidate result binding differs")
        result_ids.append(label)
    if len(set(result_ids)) != len(ids):
        raise ValueError("Duplicate candidate results")
    return {
        "schema": "cse-inspection-binding-v1",
        "status": "bound_unverified_plan",
        "world_digest": world.digest(),
        "request_digest": expected_request["request_digest"],
        "report_digest": report["report_digest"],
        "entity": str(entity),
        "quantity": context["quantity"],
        "numerical_replay": "not_performed",
        "may_authorize": False,
        "as_built_evidence": False,
    }


def replay_report(
    world: World, expected_request: dict[str, Any], report: dict[str, Any]
) -> dict[str, Any]:
    """Explicit opt-in numerical replay, with no new state/admission authority."""
    captured = json.loads(_bytes([expected_request, report]))
    receipt = inspect_report(world, *captured)
    before = world.digest()
    try:
        from geodesic_testbed.inspection import verify
    except ImportError as exc:
        raise RuntimeError(
            "Install the reviewed CSG inspection provider for numerical replay"
        ) from exc
    verification = verify(captured[1], captured[0])
    if world.digest() != before:
        raise ValueError("BIM world changed during numerical replay")
    return {
        **receipt,
        "numerical_replay": verification["numerical_replay"],
        "status": "bound_replayed_plan",
        "verification": verification,
    }
