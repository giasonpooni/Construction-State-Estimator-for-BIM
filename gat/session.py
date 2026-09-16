"""GatSession: the user-facing facade over the compile/transform/verify loop.

    session = GatSession.load_ifc("model.ifc")
    result = session.run(SetParameter(var, 3.4, design_sigma=0.01))
    session.export_ifc("out.ifc")

The session owns the current :class:`~gat.engine.executor.World`, the
human-readable execution trace, the authoritative hash-chained ledger, and
the source AST needed for export.  All numerical work happens in the engine;
the session sequences it and records evidence.
"""

from __future__ import annotations

from typing import Mapping

from gat.adapters.ifc.lower import lower_ifc
from gat.adapters.ifc.parser import IfcFile, parse_ifc, parse_ifc_file
from gat.adapters.ifc.writer import export_ifc
from gat.adapters.json_io import export_json
from gat.adapters.openusd import (
    DEFAULT_OPENUSD_READ_LIMITS,
    OpenUsdKeyPair,
    OpenUsdReadLimits,
    read_openusd,
    write_openusd,
)
from gat.causal import (
    ApprovalRecord,
    AssessmentRecord,
    ExternalActionRecord,
    PolicyRecord,
)
from gat.engine.executor import ExecutionResult, World, execute
from gat.engine.transform import Transformation
from gat.engine.verify import VerificationReport, run_invariants
from gat.errors import GatError, VerificationError
from gat.ids import EntityId, VarId
from gat.ledger import ExecutionLedger, LedgerEvent, write_ledger
from gat.state_snapshot import read_snapshot, write_snapshot
from gat.trace import ExecutionTrace


class GatSession:
    def __init__(self, world: World, source_file: IfcFile | None = None):
        self.world = world
        self.source_file = source_file
        self.trace = ExecutionTrace()
        self.imported_trace: list = []
        self.ledger = ExecutionLedger.genesis(world)
        self.carrier_signature_verified = False
        self.carrier_signing_key_id: str | None = None
        report = run_invariants(world)
        self.trace.add(
            "compile",
            world.module.meta.get("source", "<module>"),
            f"{len(world.module.entities)} entities, "
            f"{world.binding.n_raw} raw + {world.binding.n_full - world.binding.n_raw} derived vars",
            _verdict(report),
            world.digest(),
        )
        self.initial_report = report

    # -- constructors ------------------------------------------------------

    @classmethod
    def load_ifc(cls, path: str, scope=None) -> "GatSession":
        file = parse_ifc_file(path)
        del scope
        module = lower_ifc(file, source=path)
        return cls(World.compile(module), file)


def _verdict(report: VerificationReport) -> str:
    return "PASS" if report.passed else "FAIL"
