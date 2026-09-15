"""A world digest identifies a model, not a working directory.

Before `gat-world-v2` the module digest covered `meta["source"]` — the path
string the caller happened to pass — so the same bytes read as a relative
path, an absolute path, and a basename produced three different worlds.
That made pinned fixtures unreproducible, blocked ledger replay across
machines, and forced the viewer CLI to reconstruct the caller's path form
before it could bind a decision to a model.

Identity now rides on the source bytes. These tests pin that, and pin the
things it must NOT collapse: different bytes, and different lowering scopes
over the same bytes, still separate.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
import json
import unittest
from pathlib import Path

from dataclasses import replace

import gat.demo
from gat.adapters.ifc.parser import parse_ifc, parse_ifc_file
from gat.adapters.ifc.scope import IfcLoweringScope
from gat.engine.configuration import configuration_digest
from gat.engine.executor import World, execute
from gat.engine.transform import SetParameter
from gat.errors import SnapshotError, VerificationError
from gat.ir.core import LessEqual
from gat.ir.printer import PROVENANCE_META, print_module
from gat.ledger import LEDGER_RUNTIME_CONTRACT
from gat.state_snapshot import RUNTIME_CONTRACT as SNAPSHOT_RUNTIME_CONTRACT
from gat.state_snapshot import _content_digest, _decode_module
from gat.session import GatSession


def _loosen_tolerances(node: object, factor: float = 1e18) -> int:
    """Rewrite every ``tol`` in a decoded snapshot document, in place."""
    rewritten = 0
    if isinstance(node, dict):
        for key, value in list(node.items()):
            if key == "tol" and isinstance(value, (int, float)):
                node[key] = 1e9
                rewritten += 1
            else:
                rewritten += _loosen_tolerances(value, factor)
    elif isinstance(node, list):
        for item in node:
            rewritten += _loosen_tolerances(item, factor)
    return rewritten


BEAM_MODEL = Path(gat.demo.__file__).parent / "beam_model.ifc"
OFFICE = Path(gat.demo.__file__).parent / "model.ifc"
BEAM_SUBJECT = "GATBEAMELEMENT00000100"


class SourceDigestTests(unittest.TestCase):
    def test_parsed_file_carries_the_digest_of_its_bytes(self) -> None:
        raw = BEAM_MODEL.read_bytes()
        file = parse_ifc_file(str(BEAM_MODEL))
        self.assertEqual(file.content_sha256, hashlib.sha256(raw).hexdigest())

    def test_in_memory_text_still_gets_an_identity(self) -> None:
        text = BEAM_MODEL.read_text(encoding="utf-8")
        file = parse_ifc(text)
        self.assertEqual(
            file.content_sha256, hashlib.sha256(text.encode("utf-8")).hexdigest()
        )


class PathIndependenceTests(unittest.TestCase):
    def test_same_bytes_through_any_path_are_one_world(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            renamed = os.path.join(tmp, "nothing-like-the-original-name.ifc")
            shutil.copyfile(BEAM_MODEL, renamed)
            digests = {
                GatSession.load_ifc(form).world.digest()
                for form in (
                    os.path.relpath(BEAM_MODEL),
                    str(BEAM_MODEL.resolve()),
                    renamed,
                )
            }
        self.assertEqual(
            len(digests), 1, f"one model resolved to {len(digests)} identities"
        )

    def test_the_path_is_still_recorded_for_humans(self) -> None:
        session = GatSession.load_ifc(str(BEAM_MODEL))
        self.assertEqual(session.world.module.meta["source"], str(BEAM_MODEL))

    def test_provenance_keys_are_excluded_from_the_digest_text(self) -> None:
        dump = print_module(GatSession.load_ifc(str(BEAM_MODEL)).world.module)
        for key in PROVENANCE_META:
            self.assertNotIn(f"meta {key} = ", dump)
        self.assertIn("meta source_sha256 = ", dump)


class IdentityStillSeparatesTests(unittest.TestCase):
    """Path-independence must not become digest collapse."""

    def test_different_models_keep_different_digests(self) -> None:
        self.assertNotEqual(
            GatSession.load_ifc(str(BEAM_MODEL)).world.digest(),
            GatSession.load_ifc(str(OFFICE)).world.digest(),
        )

    def test_edited_bytes_change_the_digest(self) -> None:
        before = GatSession.load_ifc(str(BEAM_MODEL))
        with tempfile.TemporaryDirectory() as tmp:
            edited = os.path.join(tmp, "edited.ifc")
            text = BEAM_MODEL.read_text(encoding="utf-8")
            # One millimetre off the beam's span is a different building.
            span = "IFCQUANTITYLENGTH('Length',$,$,6.)"
            self.assertIn(span, text, "fixture changed; pick another literal")
            Path(edited).write_text(
                text.replace(span, "IFCQUANTITYLENGTH('Length',$,$,6.001)", 1),
                encoding="utf-8",
            )
            after = GatSession.load_ifc(edited)
        self.assertNotEqual(before.world.digest(), after.world.digest())

    def test_different_scopes_over_one_file_stay_distinct(self) -> None:
        scoped = GatSession.load_ifc(
            str(BEAM_MODEL), scope=IfcLoweringScope(frozenset({BEAM_SUBJECT}))
        )
        whole = GatSession.load_ifc(str(BEAM_MODEL))
        self.assertNotEqual(scoped.world.digest(), whole.world.digest())


class ToleranceIsIdentityTests(unittest.TestCase):
    """A constraint's ``tol`` is the whole quantitative content of CONS-01,
    CONS-02 and CONS-03, and it was outside every digest.

    ``print_module`` named a constraint's variables and its shape and
    stopped. So a world whose tolerances had been rewritten 1e-09 -> 1e9 --
    which is to say, a world where no bound can be violated -- printed the
    same bytes as the honest one and carried the same module, world and
    configuration digest. The snapshot envelope's own integrity digest is an
    unkeyed SHA-256 of the document, so it detects corruption, not an
    adversary: recompute it and the sabotaged state loads clean under the
    honest identity. A door driven a metre past its opening was then accepted
    where the honest world refuses it with CONS-02.
    """

    MODEL = os.path.join(os.path.dirname(gat.demo.__file__), "model.ifc")

    def _module(self):
        return GatSession.load_ifc(self.MODEL).world.module

    def test_the_digest_text_states_every_tolerance(self) -> None:
        module = self._module()
        text = print_module(module)
        constraints = [line for line in text.splitlines() if line.startswith("constraint ")]
        self.assertEqual(len(constraints), len(module.constraints))
        for line in constraints:
            self.assertIn(" tol=", line)

    def test_the_default_tolerance_is_stated_too(self) -> None:
        """Omitting it would be lossless today and would tie identity to a
        constant in ``gat.ir.core``: change that default and two modules
        written under the two values collide."""
        module = self._module()
        self.assertTrue(
            any(c.tol == 1e-9 for c in module.constraints),
            "fixture changed; no constraint carries the default any more",
        )
        self.assertIn("tol=1e-09", print_module(module))

    def test_rewriting_one_tolerance_changes_the_digest(self) -> None:
        module = self._module()
        before = module.digest()
        for index, constraint in enumerate(module.constraints):
            with self.subTest(constraint=type(constraint).__name__):
                loosened = replace(constraint, tol=1e9)
                mutated = replace(
                    module,
                    constraints=(
                        module.constraints[:index]
                        + (loosened,)
                        + module.constraints[index + 1 :]
                    ),
                )
                self.assertNotEqual(before, mutated.digest())
            if index >= 2:
                break

    def test_a_snapshot_with_rewritten_tolerances_is_refused(self) -> None:
        """Restamping the envelope's unkeyed digest is not enough any more:
        the module digest the document states about itself no longer matches
        the module it carries."""
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "snapshot.json")
            GatSession.load_ifc(self.MODEL).export_snapshot(path)
            with open(path, encoding="utf-8") as handle:
                document = json.load(handle)

            rewritten = _loosen_tolerances(document)
            self.assertGreater(rewritten, 0, "fixture carries no tolerances")
            envelope = {k: v for k, v in document.items() if k != "integrity"}
            document["integrity"] = {
                "algorithm": "sha256",
                "digest": _content_digest(envelope),
            }
            bad = os.path.join(tmp, "sabotaged.json")
            with open(bad, "w", encoding="utf-8") as handle:
                json.dump(document, handle)

            with self.assertRaisesRegex(SnapshotError, "module digest"):
                GatSession.load_snapshot(bad)

    def test_restamping_every_digest_yields_a_different_world(self) -> None:
        """An attacker can of course write a consistent document -- but it is
        then a different world, and nothing bound to the honest digest (an
        evidence receipt's ``result_world_digest``, a ledger event, a
        signature over the digest) covers it."""
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "snapshot.json")
            honest = GatSession.load_ifc(self.MODEL)
            honest.export_snapshot(path)
            with open(path, encoding="utf-8") as handle:
                document = json.load(handle)

            _loosen_tolerances(document)
            module = _decode_module(document["payload"]["module"])
            world = World.compile(module)
            document["payload"]["source_module_digest"] = module.digest()
            document["payload"]["source_world_digest"] = world.digest()
            document["payload"]["source_configuration_digest"] = (
                configuration_digest(world)
            )
            envelope = {k: v for k, v in document.items() if k != "integrity"}
            document["integrity"] = {
                "algorithm": "sha256",
                "digest": _content_digest(envelope),
            }
            bad = os.path.join(tmp, "restamped.json")
            with open(bad, "w", encoding="utf-8") as handle:
                json.dump(document, handle)

            loaded = GatSession.load_snapshot(bad)
            self.assertEqual(loaded.world.module.constraints[0].tol, 1e9)
            self.assertNotEqual(loaded.world.digest(), honest.world.digest())

    def test_the_loosened_world_is_the_one_that_would_have_accepted(self) -> None:
        """The reason any of this matters. Honest: CONS-02 refuses the change.
        Loosened: it goes through and the report says nothing failed.

        Run against the compiled worlds rather than through ``GatSession``,
        because the session route no longer reaches this state at all -- its
        ledger genesis is bound to the honest module digest, so mutating the
        tolerances underneath it is refused with "ledger head does not
        describe the session's prior world". That refusal is itself the fix
        working; this test is about what was on the other side of it.
        """
        honest = GatSession.load_ifc(self.MODEL).world
        bound = next(
            c for c in honest.module.constraints if isinstance(c, LessEqual)
        )
        target = bound.lhs
        mean = float(honest.full.mu[honest.binding.full_index.row(target)])
        change = SetParameter(target, mean + 1.0, 0.001)

        with self.assertRaises(VerificationError) as caught:
            execute(honest, change, strict=True)
        self.assertIn("CONS-02", str(caught.exception))

        loosened = World.compile(
            replace(
                honest.module,
                constraints=tuple(
                    replace(c, tol=1e9) if isinstance(c, LessEqual) else c
                    for c in honest.module.constraints
                ),
            )
        )
        result = execute(loosened, change, strict=True)
        self.assertTrue(result.report.passed)
        self.assertEqual(result.report.counts()[2], 0)


class MetaRoundTripTests(unittest.TestCase):
    def test_meta_values_are_text_so_a_snapshot_round_trips(self) -> None:
        session = GatSession.load_ifc(
            str(BEAM_MODEL), scope=IfcLoweringScope(frozenset({BEAM_SUBJECT}))
        )
        for key, value in session.world.module.meta.items():
            with self.subTest(key=key):
                self.assertIsInstance(value, str)

        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "snapshot.json")
            session.export_snapshot(path)
            resumed = GatSession.load_snapshot(path)

        self.assertEqual(
            dict(resumed.world.module.meta), dict(session.world.module.meta)
        )
        self.assertEqual(resumed.world.digest(), session.world.digest())


class RuntimeContractTests(unittest.TestCase):
    def test_the_contract_records_the_identity_change(self) -> None:
        """An older ledger's digests are not reproducible here, so the tag
        moved: v2 for path-independence, v3 for putting each constraint's
        ``tol`` inside the module digest."""
        self.assertEqual(LEDGER_RUNTIME_CONTRACT, "gat-world-v3")

    def test_the_snapshot_names_the_same_contract_as_the_ledger(self) -> None:
        """They describe one thing -- what a world digest here means -- and
        the snapshot's copy sat at ``gat-world-v1`` through the whole
        path-independence change. A snapshot written under the superseded
        rules cleared this guard and failed later at the digest comparison,
        reported as a corrupt document rather than an obsolete one."""
        self.assertEqual(SNAPSHOT_RUNTIME_CONTRACT, LEDGER_RUNTIME_CONTRACT)




class CarrierRoundTripTests(unittest.TestCase):
    """What each carrier preserves, and what an artifact discloses.

    Probed rather than assumed: the state-carrying formats return the world
    bit-identically and repeatedly, IFC does not (it is a design exchange and
    does not carry the belief), and the artifacts name the exporter's paths.
    That last one is a trade documented in docs/world-identity-v2.md; it is
    pinned here so it cannot change silently in either direction.
    """

    MODEL = os.path.join(os.path.dirname(gat.demo.__file__), "model.ifc")

    def _session(self):
        return GatSession.load_ifc(self.MODEL)

    def test_the_state_carriers_return_the_same_world(self):
        session = self._session()
        origin = session.world.digest()
        with tempfile.TemporaryDirectory() as directory:
            snapshot = os.path.join(directory, "state.gat.json")
            session.export_snapshot(snapshot)
            self.assertEqual(
                GatSession.load_snapshot(snapshot).world.digest(), origin
            )

            stage = os.path.join(directory, "state.usda")
            session.export_usd(stage)
            self.assertEqual(GatSession.load_usd(stage).world.digest(), origin)

    def test_ten_consecutive_round_trips_do_not_drift(self):
        """One round trip proves the encoder inverts once. Drift would show
        as a slow walk, so the chain is what is checked."""
        session = self._session()
        origin = session.world.digest()
        with tempfile.TemporaryDirectory() as directory:
            for index in range(10):
                path = os.path.join(directory, f"chain{index}.gat.json")
                session.export_snapshot(path)
                session = GatSession.load_snapshot(path)
                self.assertEqual(session.world.digest(), origin, f"drifted at {index}")

    def test_ifc_is_a_design_exchange_and_does_not_round_trip_identity(self):
        """Not a defect: IFC carries the model, not the belief. Asserted so
        nobody reads the snapshot guarantee as covering this one."""
        session = self._session()
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "out.ifc")
            session.export_ifc(path)
            self.assertNotEqual(
                GatSession.load_ifc(path).world.digest(), session.world.digest()
            )

    def test_an_export_is_itself_a_recorded_act(self):
        """Two exports of one state are not byte-identical, because the first
        one happened: it appends an export event the second then carries."""
        session = self._session()
        with tempfile.TemporaryDirectory() as directory:
            first = os.path.join(directory, "a.gat.json")
            second = os.path.join(directory, "b.gat.json")
            before = len(session.trace.events)
            session.export_snapshot(first)
            session.export_snapshot(second)
            self.assertEqual(len(session.trace.events), before + 2)
            with open(first, "rb") as a, open(second, "rb") as b:
                self.assertNotEqual(a.read(), b.read())

    def test_an_exported_artifact_names_the_exporters_paths(self):
        """Identity is path-independent; provenance deliberately is not. See
        'What that provenance discloses' in docs/world-identity-v2.md -- an
        operator handing this file over is handing over these strings."""
        with tempfile.TemporaryDirectory() as directory:
            marked = os.path.join(directory, "a_recognisable_name.ifc")
            shutil.copy(self.MODEL, marked)
            session = GatSession.load_ifc(marked)
            self.assertEqual(session.world.digest(), self._session().world.digest())

            snapshot = os.path.join(directory, "state.gat.json")
            session.export_snapshot(snapshot)
            with open(snapshot, encoding="utf-8") as handle:
                document = json.load(handle)
            self.assertEqual(document["payload"]["module"]["meta"]["source"], marked)


if __name__ == "__main__":
    unittest.main()
