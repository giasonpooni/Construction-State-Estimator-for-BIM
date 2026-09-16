"""Host cost model for the i32 kernels. Not an SP1 cycle counter."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from gat.satellites.fixedpoint_kernel import chain_jvp_i32, discrete_lyapunov_decrease_i32


@dataclass
class KernelCost:
    name: str
    muls: int
    adds: int
    ieee754: bool = False
    guest: str = "not-compiled"
    proof: str = "not-invoked"

    def as_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "i32_muls": self.muls,
            "i32_adds": self.adds,
            "ieee754": self.ieee754,
            "guest": self.guest,
            "proof": self.proof,
            "note": "Host op counts. SP1 cycles require the pinned ELF execute path.",
        }


def cost_chain_jvp() -> KernelCost:
    y = chain_jvp_i32([[2, 0], [0, 3]], [1, 1], [[1, 1], [0, 1]])
    if y != (5, 3):
        raise AssertionError("chain_jvp pin drifted")
    return KernelCost("chain_jvp_i32", muls=8, adds=4)


def cost_lyapunov() -> KernelCost:
    report = discrete_lyapunov_decrease_i32([[0, 1], [0, 0]], [[1, 0], [0, 1]], [2, 1])
    if report["V"] != 5 or report["V_next"] != 1 or not report["decreases"]:
        raise AssertionError("lyapunov pin drifted")
    return KernelCost("discrete_lyapunov_decrease_i32", muls=16, adds=8)


def beam_guest_status(repo_root: Path) -> Mapping[str, object]:
    elf_hint = repo_root / "sp1" / "beam" / "target" / "release" / "gat-sp1-beam"
    return {
        "guest_id": "beam-b1-f2-1",
        "arithmetic": "checked-integer",
        "binary_present": elf_hint.is_file(),
        "path": str(elf_hint),
        "cycles": None,
        "note": "Run cargo execute on the pinned guest to fill cycles. Do not invent a count.",
    }


def riscv_ot_declaration() -> dict[str, object]:
    return {
        "schema": "cse-riscv-ot-v1",
        "claim_scope": "record-integrity-only",
        "isa": "riscv",
        "role": "shared target for plant estimator and proving guest",
        "flashed": False,
        "plc_replacement": False,
        "note": "Ibex-class / plant core is a later board profile. Not this commit.",
    }


def cost_report(repo_root: Path | None = None) -> dict[str, object]:
    root = repo_root or Path(__file__).resolve().parents[2]
    return {
        "schema": "cse-kernel-cost-v1",
        "claim_scope": "computational-integrity-only",
        "ieee754_guest": False,
        "kernels": [cost_chain_jvp().as_dict(), cost_lyapunov().as_dict()],
        "beam_guest": beam_guest_status(root),
        "riscv_ot": riscv_ot_declaration(),
        "ranking": "fixed-point op count on this kernel, not rollup benches",
        "sheaf": "not opened",
    }
