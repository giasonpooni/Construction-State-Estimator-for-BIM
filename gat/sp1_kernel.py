"""Second host callback: i32 chain-JVP guest.

Until an SP1 executable proves this statement, host evaluation is not a proof.
Scope is computational-integrity-only. Does not stamp, observe, or authorize.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import subprocess
from typing import Mapping

from gat.satellites.fixedpoint_kernel import chain_jvp_i32

CLAIM_SCOPE = "computational-integrity-only"
CALLBACK_ID = "sp1-kernel-chain-jvp-v0"
REQUEST_FORMAT = "gat-sp1-kernel-request-v1"
RECEIPT_FORMAT = "gat-sp1-kernel-receipt-v1"
KERNEL = "chain_jvp_i32"
NUMERIC = "i32-checked"
PIN_J1 = ((2, 0), (0, 3))
PIN_DX = (1, 1)
PIN_J2 = ((1, 1), (0, 1))
PIN_Y = (5, 3)


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def statement_body() -> dict[str, object]:
    return {
        "callback_id": CALLBACK_ID,
        "claim_scope": CLAIM_SCOPE,
        "kernel": KERNEL,
        "numeric": NUMERIC,
        "J1": [list(row) for row in PIN_J1],
        "dx": list(PIN_DX),
        "J2": [list(row) for row in PIN_J2],
        "y": list(PIN_Y),
    }


def statement_digest() -> str:
    return hashlib.sha256(_canonical(statement_body())).hexdigest()


def evaluate_host() -> dict[str, object]:
    """Native i32 evaluation. Not a proof."""
    y = chain_jvp_i32(PIN_J1, PIN_DX, PIN_J2)
    if tuple(y) != PIN_Y:
        raise RuntimeError(f"host pin drifted: {y} != {PIN_Y}")
    return {
        "y": list(y),
        "matches_pin": True,
        "is_proof": False,
        "reason": "host evaluation of the twin is not a proof",
    }


@dataclass(frozen=True)
class KernelCallbackReport:
    document: dict[str, object]

    @property
    def is_proof(self) -> bool:
        return bool(self.document.get("is_proof"))

    def write(self, path: str | Path) -> Path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(self.document, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return target


def host_callback(
    executable: str | Path | None = None,
    *,
    prove: bool = False,
    proof_path: str | Path | None = None,
    timeout_seconds: float = 3600.0,
) -> KernelCallbackReport:
    """Compile-or-run callback. Proof only if the guest executable succeeds."""
    host = evaluate_host()
    digest = statement_digest()
    base: dict[str, object] = {
        "format": RECEIPT_FORMAT,
        "callback_id": CALLBACK_ID,
        "claim_scope": CLAIM_SCOPE,
        "statement_digest": digest,
        "statement": statement_body(),
        "host": host,
        "is_proof": False,
        "invoked": False,
        "executable": None if executable is None else str(Path(executable)),
    }
    if executable is None:
        base["status"] = "NOT_A_PROOF"
        return KernelCallbackReport(base)
    executable_path = Path(executable).resolve()
    if not executable_path.is_file():
        base["status"] = "NOT_A_PROOF"
        base["reason"] = f"missing guest executable {executable_path}"
        return KernelCallbackReport(base)
    command = [str(executable_path), "prove" if prove else "execute"]
    if prove:
        target = Path(proof_path or "out/kernel-chain-jvp.proof")
        target.parent.mkdir(parents=True, exist_ok=True)
        command.extend(["--proof", str(target.resolve())])
    completed = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
    )
    base["invoked"] = True
    base["stdout"] = completed.stdout[-2000:]
    base["stderr"] = completed.stderr[-2000:]
    base["returncode"] = completed.returncode
    if completed.returncode != 0:
        base["status"] = "NOT_A_PROOF"
        base["reason"] = "guest executable failed"
        return KernelCallbackReport(base)
    base["status"] = "PROOF_VERIFIED" if prove else "EXECUTED_NOT_PROVED"
    base["is_proof"] = bool(prove)
    return KernelCallbackReport(base)


def request_document() -> dict[str, object]:
    return {
        "format": REQUEST_FORMAT,
        "callback_id": CALLBACK_ID,
        "claim_scope": CLAIM_SCOPE,
        "statement_digest": statement_digest(),
        "statement": statement_body(),
    }
