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

import gat.demo
from gat.adapters.ifc.parser import parse_ifc, parse_ifc_file
from gat.adapters.ifc.scope import IfcLoweringScope
from gat.ir.printer import PROVENANCE_META, print_module
from gat.ledger import LEDGER_RUNTIME_CONTRACT
from gat.session import GatSession


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
        """A v1 ledger's digests are not reproducible here, so the tag moved."""
        self.assertEqual(LEDGER_RUNTIME_CONTRACT, "gat-world-v2")




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
