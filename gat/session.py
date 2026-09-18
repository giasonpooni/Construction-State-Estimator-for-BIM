"""GatSession: facade over compile / execute / ledger."""

from __future__ import annotations

from dataclasses import asdict
from typing import Mapping

from gat.adapters.ifc.lower import lower_ifc
from gat.adapters.ifc.parser import IfcFile, parse_ifc, parse_ifc_file
from gat.adapters.ifc.scope import IfcLoweringScope
from gat.adapters.ifc.writer import export_ifc as write_ifc
from gat.adapters.openusd import (
    DEFAULT_OPENUSD_READ_LIMITS,
    OpenUsdKeyPair,
    OpenUsdReadLimits,
    read_openusd,
    write_openusd,
)
from gat.adapters.json_io import export_json as write_json
from gat.adapters.usd_io import export_usd as write_usd
from gat.adapters.usd_io import load_usd as read_usd
from gat.causal import (
    ApprovalRecord,
    AssessmentRecord,
    CausalRecord,
    ExternalActionRecord,
    PolicyRecord,
)
from gat.engine.executor import ExecutionResult, World, execute
from gat.engine.transform import Transformation
from gat.engine.verify import VerificationReport, run_invariants
from gat.errors import GatError, VerificationError
from gat.ids import EntityId, VarId
from gat.ledger import ExecutionLedger, write_ledger
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

    @classmethod
    def load_ifc(cls, path: str, scope: IfcLoweringScope | None = None) -> "GatSession":
        file = parse_ifc_file(path)
        module = lower_ifc(file, source=path, scope=scope)
        return cls(World.compile(module), file)

    @classmethod
    def from_text(
        cls,
        text: str,
        source: str = "<memory>",
        scope: IfcLoweringScope | None = None,
    ) -> "GatSession":
        """Lower IFC held in memory. The in-memory sibling of :meth:`load_ifc`."""
        file = parse_ifc(text)
        module = lower_ifc(file, source=source, scope=scope)
        return cls(World.compile(module), file)

    def entity_by_name(self, entity_name: str) -> EntityId:
        """Resolve a unique entity *name* to its canonical :class:`EntityId`.

        Callers key modules, build ``VarId``s, and construct engineering
        checks off the result, so the identity - not the ``Entity`` record -
        is the contract.  ``Entity`` carries mappings and is therefore
        unhashable; returning it here poisons every downstream dict lookup.
        Use ``self.world.module.entity(...)`` when the record itself is
        wanted.
        """
        matches = [
            entity
            for entity in self.world.module.entities.values()
            if entity.name == entity_name
        ]
        if len(matches) != 1:
            raise KeyError(
                f"expected one entity named {entity_name!r}, found {len(matches)}"
            )
        return matches[0].id

    def var(self, entity_name: str, quantity: str) -> VarId:
        return VarId(self.entity_by_name(entity_name), quantity)

    def run(
        self,
        transformation: Transformation,
        provenance: Mapping[str, object] | None = None,
        strict: bool = True,
    ) -> ExecutionResult:
        before = self.world
        try:
            result = execute(before, transformation, strict=strict)
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
        if not result.committed:
            # Non-strict: execute() returned the failure instead of raising it.
            # The ledger must record it as the same rejection a strict run
            # would have recorded, so replay is identical either way.
            self.ledger.record_rejection(
                before,
                transformation,
                VerificationError(result.report),
                provenance=provenance,
            )
            self.trace.add(
                "reject",
                transformation.describe(),
                "verification failed (non-strict)",
                "FAIL",
                before.digest(),
            )
            return result
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

    def export_ifc(self, path: str) -> tuple[int, int]:
        """Write the belief back into the source SPF as (patched, appended)."""
        if self.source_file is None:
            raise GatError("session has no source IFC file to export into")
        return write_ifc(self.source_file, self.world, path)

    def export_json(self, path: str) -> None:
        write_json(self.world, path)

    def export_ledger(self, path: str) -> str:
        return write_ledger(self.ledger, path)

    def record_assessment(
        self,
        record: AssessmentRecord,
        provenance: Mapping[str, object] | None = None,
    ):
        return self.record_causal(record, provenance=provenance)

    def record_policy(
        self,
        record: PolicyRecord,
        provenance: Mapping[str, object] | None = None,
    ):
        return self.record_causal(record, provenance=provenance)

    def record_approval(
        self,
        record: ApprovalRecord,
        provenance: Mapping[str, object] | None = None,
    ):
        return self.record_causal(record, provenance=provenance)

    def record_external_action(
        self,
        record: ExternalActionRecord,
        provenance: Mapping[str, object] | None = None,
    ):
        return self.record_causal(record, provenance=provenance)

    def record_causal(
        self,
        record: CausalRecord,
        provenance: Mapping[str, object] | None = None,
    ):
        # Every lifecycle rule lives in ExecutionLedger.record_causal, so the
        # typed wrappers above stay thin and cannot drift from it.
        return self.ledger.record_causal(self.world, record, provenance=provenance)

    def export_snapshot(self, path: str) -> str:
        # write first: the carrier holds the trace as it stands, and the
        # "export" event below is not part of what a reload replays.
        digest = write_snapshot(self.world, path, self.trace.events)
        self.trace.add("export", str(path), "state snapshot", "-", self.world.digest())
        return digest

    @classmethod
    def load_snapshot(cls, path: str) -> "GatSession":
        loaded = read_snapshot(path)
        session = cls(loaded.world)
        session.trace = ExecutionTrace(list(loaded.trace_events))
        session.trace.add(
            "resume",
            str(path),
            f"snapshot {loaded.snapshot_digest[:12]}",
            "-",
            loaded.world.digest(),
        )
        return session

    def export_usd(self, path: str) -> int:
        entities = write_usd(
            self.world, path, [asdict(event) for event in self.trace.events]
        )
        self.trace.add(
            "export", str(path), "usd state carrier", "-", self.world.digest()
        )
        return entities

    @classmethod
    def load_usd(cls, path: str) -> "GatSession":
        world, imported_trace = read_usd(path)
        session = cls(world)
        session.imported_trace = list(imported_trace)
        session.trace.add(
            "resume",
            str(path),
            f"{len(session.imported_trace)} imported trace events",
            "-",
            world.digest(),
        )
        return session

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
