"""GatSession: facade over compile / execute / ledger.

    session = GatSession.load_ifc("model.ifc")
    result = session.run(SetParameter(var, 3.4, design_sigma=0.01))

The kernel is World + execute + ExecutionLedger. This object sequences
them and owns the current world, trace, and ledger head.
"""

from __future__ import annotations

from typing import Mapping

from gat.adapters.ifc.lower import lower_ifc
from gat.adapters.ifc.parser import IfcFile, parse_ifc_file
from gat.adapters.openusd import (
    DEFAULT_OPENUSD_READ_LIMITS,
    OpenUsdKeyPair,
    OpenUsdReadLimits,
    read_openusd,
    write_openusd,
)
from gat.engine.executor import ExecutionResult, World, execute
from gat.engine.transform import Transformation
from gat.engine.verify import VerificationReport, run_invariants
from gat.errors import GatError
from gat.ids import VarId
from gat.ledger import ExecutionLedger
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

    @classmethod
    def load_ifc(cls, path: str, scope=None) -> "GatSession":
        file = parse_ifc_file(path)
        del scope
        module = lower_ifc(file, source=path)
        return cls(World.compile(module), file)

    def var(self, entity_name: str, quantity: str) -> VarId:
        """Resolve one variable by entity display name plus quantity."""
        matches = [
            entity
            for entity in self.world.module.entities.values()
            if entity.name == entity_name
        ]
        if len(matches) != 1:
            raise KeyError(
                f"expected one entity named {entity_name!r}, found {len(matches)}"
            )
        return matches[0].var(quantity)

    def run(
        self,
        transformation: Transformation,
        provenance: Mapping[str, object] | None = None,
    ) -> ExecutionResult:
        """Apply one transformation under execute + ledger."""
        before = self.world
        try:
            result = execute(before, transformation)
        except GatError as error:
            self.ledger.record_rejection(
                before, transformation, error, provenance=provenance
            )
            self.trace.add(
                "reject",
                transformation.describe(),
                str(error),
                "FAIL",
                before.digest(),
            )
            raise
        self.ledger.record_transition(before, result, provenance=provenance)
        self.world = result.world
        self.trace.add(
            "transform" if not _is_observation(transformation) else "observe",
            transformation.describe(),
            f"committed={result.committed}",
            _verdict(result.report),
            result.world.digest(),
        )
        return result

    def verify(self) -> VerificationReport:
        return run_invariants(self.world)

    def export_openusd(
        self,
        path: str,
        *,
        signing_key: OpenUsdKeyPair | None = None,
        include_geometry: bool = True,
    ) -> str:
        digest = write_openusd(
            self.world,
            path,
            self.trace.events,
            include_geometry=include_geometry,
            signing_key=signing_key,
            ledger=self.ledger,
        )
        self.trace.add("export", str(path), "openusd carrier", "-", self.world.digest())
        return digest

    @classmethod
    def load_openusd(
        cls,
        path: str,
        *,
        limits: OpenUsdReadLimits = DEFAULT_OPENUSD_READ_LIMITS,
        trusted_public_keys: Mapping[str, bytes] | None = None,
        require_signature: bool = False,
    ) -> "GatSession":
        loaded = read_openusd(
            path,
            limits=limits,
            trusted_public_keys=trusted_public_keys,
            require_signature=require_signature,
        )
        session = cls(loaded.world)
        if loaded.ledger is not None:
            session.ledger = loaded.ledger
        session.imported_trace = list(loaded.trace_events)
        session.carrier_signature_verified = loaded.signature.verified
        session.carrier_signing_key_id = loaded.signature.key_id
        detail = "signature verified" if loaded.signature.verified else "carrier loaded"
        session.trace.add(
            "resume",
            str(path),
            detail,
            "-",
            loaded.world.digest(),
        )
        return session


def _is_observation(transformation: Transformation) -> bool:
    name = type(transformation).__name__.lower()
    return "observe" in name


def _verdict(report: VerificationReport) -> str:
    return "PASS" if report.passed else "FAIL"
