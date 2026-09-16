"""Declared calibration for a named quantity.

Satellite. Not a traceable certificate. Unknown keys are refused.
A measurement cannot enter the ledger without a bound calibration digest.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import math
from pathlib import Path
from typing import Mapping

from gat.adapters.external_commitment import canonical_digest


CALIBRATION_SCHEMA = "cse-calibration-v1"
MEASUREMENT_SCHEMA = "cse-measurement-v1"
CLAIM_SCOPE = "record-integrity-only"
ALLOWED_STATUS = frozenset({"prototype", "declared", "traceable"})
_CAL_KEYS = frozenset(
    {
        "schema",
        "claim_scope",
        "calibration_id",
        "status",
        "subject",
        "indicated_unit",
        "canonical_unit",
        "model",
        "sigma",
        "sigma_unit",
        "sigma_reason",
        "source_reason",
        "not_traceable",
        "digest",
    }
)
_MEAS_KEYS = frozenset(
    {
        "schema",
        "claim_scope",
        "observation_id",
        "calibration_id",
        "indicated",
        "raw",
        "sigma",
        "sigma_unit",
        "sigma_reason",
        "digest",
    }
)


def _refuse_unknown(document: Mapping[str, object], allowed: frozenset[str], label: str) -> None:
    extra = sorted(set(document) - allowed)
    if extra:
        raise ValueError(f"{label} has unknown keys: {extra}")


def _nonempty(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")
    return value.strip()


def _positive(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a positive number")
    number = float(value)
    if not math.isfinite(number) or number <= 0.0:
        raise ValueError(f"{label} must be a positive finite number")
    return number


def _finite(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a number")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{label} must be finite")
    return number


@dataclass(frozen=True)
class Calibration:
    calibration_id: str
    status: str
    ifc_class: str
    global_id: str
    quantity: str
    indicated_unit: str
    canonical_unit: str
    scale: float
    offset: float
    sigma: float
    sigma_unit: str
    sigma_reason: str
    source_reason: str
    not_traceable: bool
    digest: str

    def apply(self, indicated: float) -> float:
        return self.scale * indicated + self.offset

    def to_document(self) -> dict[str, object]:
        payload = {
            "schema": CALIBRATION_SCHEMA,
            "claim_scope": CLAIM_SCOPE,
            "calibration_id": self.calibration_id,
            "status": self.status,
            "subject": {
                "ifc_class": self.ifc_class,
                "global_id": self.global_id,
                "quantity": self.quantity,
            },
            "indicated_unit": self.indicated_unit,
            "canonical_unit": self.canonical_unit,
            "model": {"form": "affine", "scale": self.scale, "offset": self.offset},
            "sigma": self.sigma,
            "sigma_unit": self.sigma_unit,
            "sigma_reason": self.sigma_reason,
            "source_reason": self.source_reason,
            "not_traceable": self.not_traceable,
        }
        return {**payload, "digest": self.digest}


def load_calibration(document: Mapping[str, object]) -> Calibration:
    _refuse_unknown(document, _CAL_KEYS, "calibration")
    if document.get("schema") != CALIBRATION_SCHEMA:
        raise ValueError(f"unsupported calibration schema {document.get('schema')!r}")
    if document.get("claim_scope") != CLAIM_SCOPE:
        raise ValueError("calibration claim_scope must be record-integrity-only")
    status = _nonempty(document.get("status"), "status")
    if status not in ALLOWED_STATUS:
        raise ValueError("calibration status must be prototype, declared, or traceable")
    subject = document.get("subject")
    if not isinstance(subject, Mapping):
        raise ValueError("calibration subject must be an object")
    extra_subject = sorted(set(subject) - {"ifc_class", "global_id", "quantity"})
    if extra_subject:
        raise ValueError(f"calibration subject has unknown keys: {extra_subject}")
    model = document.get("model")
    if not isinstance(model, Mapping):
        raise ValueError("calibration model must be an object")
    extra_model = sorted(set(model) - {"form", "scale", "offset"})
    if extra_model:
        raise ValueError(f"calibration model has unknown keys: {extra_model}")
    if model.get("form") != "affine":
        raise ValueError("only affine calibration is accepted in v1")
    not_traceable = document.get("not_traceable")
    if not isinstance(not_traceable, bool):
        raise ValueError("not_traceable must be a boolean")
    if status == "traceable" and not_traceable:
        raise ValueError("traceable calibration cannot set not_traceable true")
    if status == "prototype" and not not_traceable:
        raise ValueError("prototype calibration must set not_traceable true")
    cal_id = _nonempty(document.get("calibration_id"), "calibration_id")
    ifc_class = _nonempty(subject.get("ifc_class"), "subject.ifc_class")
    global_id = _nonempty(subject.get("global_id"), "subject.global_id")
    quantity = _nonempty(subject.get("quantity"), "subject.quantity")
    indicated_unit = _nonempty(document.get("indicated_unit"), "indicated_unit")
    canonical_unit = _nonempty(document.get("canonical_unit"), "canonical_unit")
    scale = _finite(model.get("scale"), "model.scale")
    offset = _finite(model.get("offset"), "model.offset")
    sigma = _positive(document.get("sigma"), "sigma")
    sigma_unit = _nonempty(document.get("sigma_unit"), "sigma_unit")
    sigma_reason = _nonempty(document.get("sigma_reason"), "sigma_reason")
    source_reason = _nonempty(document.get("source_reason"), "source_reason")
    payload = {
        "schema": CALIBRATION_SCHEMA,
        "claim_scope": CLAIM_SCOPE,
        "calibration_id": cal_id,
        "status": status,
        "subject": {
            "ifc_class": ifc_class,
            "global_id": global_id,
            "quantity": quantity,
        },
        "indicated_unit": indicated_unit,
        "canonical_unit": canonical_unit,
        "model": {"form": "affine", "scale": scale, "offset": offset},
        "sigma": sigma,
        "sigma_unit": sigma_unit,
        "sigma_reason": sigma_reason,
        "source_reason": source_reason,
        "not_traceable": not_traceable,
    }
    digest = canonical_digest(payload)
    declared = document.get("digest")
    if declared is not None and declared != digest:
        raise ValueError("calibration digest does not match payload")
    return Calibration(
        cal_id,
        status,
        ifc_class,
        global_id,
        quantity,
        indicated_unit,
        canonical_unit,
        scale,
        offset,
        sigma,
        sigma_unit,
        sigma_reason,
        source_reason,
        not_traceable,
        digest,
    )


def load_calibration_file(path: str | Path) -> Calibration:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("calibration file must be a JSON object")
    return load_calibration(raw)


@dataclass(frozen=True)
class Measurement:
    observation_id: str
    calibration_id: str
    indicated: float
    sigma: float
    sigma_unit: str
    sigma_reason: str
    digest: str


def load_measurement(document: Mapping[str, object]) -> Measurement:
    _refuse_unknown(document, _MEAS_KEYS, "measurement")
    if document.get("schema") != MEASUREMENT_SCHEMA:
        raise ValueError(f"unsupported measurement schema {document.get('schema')!r}")
    if document.get("claim_scope") != CLAIM_SCOPE:
        raise ValueError("measurement claim_scope must be record-integrity-only")
    indicated = document.get("indicated")
    if indicated is None:
        indicated = document.get("raw")
    observation_id = _nonempty(document.get("observation_id"), "observation_id")
    calibration_id = _nonempty(document.get("calibration_id"), "calibration_id")
    indicated_n = _finite(indicated, "indicated")
    sigma = _positive(document.get("sigma"), "sigma")
    sigma_unit = _nonempty(document.get("sigma_unit"), "sigma_unit")
    sigma_reason = _nonempty(document.get("sigma_reason"), "sigma_reason")
    payload = {
        "schema": MEASUREMENT_SCHEMA,
        "claim_scope": CLAIM_SCOPE,
        "observation_id": observation_id,
        "calibration_id": calibration_id,
        "indicated": indicated_n,
        "sigma": sigma,
        "sigma_unit": sigma_unit,
        "sigma_reason": sigma_reason,
    }
    digest = canonical_digest(payload)
    declared = document.get("digest")
    if declared is not None and declared != digest:
        raise ValueError("measurement digest does not match payload")
    return Measurement(
        observation_id,
        calibration_id,
        indicated_n,
        sigma,
        sigma_unit,
        sigma_reason,
        digest,
    )


def load_measurement_file(path: str | Path) -> Measurement:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("measurement file must be a JSON object")
    return load_measurement(raw)


def bind_measurement(calibration: Calibration, measurement: Measurement) -> float:
    if measurement.calibration_id != calibration.calibration_id:
        raise ValueError("measurement calibration_id does not match calibration")
    if measurement.sigma_unit != calibration.canonical_unit:
        raise ValueError("measurement sigma_unit must match calibration canonical_unit")
    return calibration.apply(measurement.indicated)
