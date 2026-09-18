"""A world identity that does not depend on how the file was named.

World.digest() hashes the printer dump, which emits every meta key including
"source" -- the path string the caller passed to load_ifc. So one file yields a
different world digest per spelling, which is why a pinned world_digest in
validation/ is only reproducible from the exact checkout and exact spelling
that produced it. portable_world_digest is the same composition with location
meta elided, so a claim can cross a repository.

These tests pin both halves: that the local digest really is location-bound
(so nobody mistakes it for portable), and that the portable one is not.

stdlib unittest only.
"""

from __future__ import annotations

import os
import unittest
from pathlib import Path

from gat.adapters.portable_identity import (
    IDENTITY_SCHEMA,
    LOCATION_META_KEYS,
    portable_meta,
    portable_module_digest,
    portable_world_digest,
    same_world,
    world_identity,
)
from gat.adapters.ifc.scope import IfcLoweringScope
from gat.engine.transform import ObserveQuantity
from gat.session import GatSession

_ROOT = Path(__file__).resolve().parents[1]
MODEL = _ROOT / "gat" / "demo" / "model.ifc"
BEAM = _ROOT / "gat" / "demo" / "beam_model.ifc"

# The same file, four ways of naming it. Relative forms are resolved against
# the repo root so the test does not depend on the runner's cwd.
def _spellings() -> list[str]:
    root = str(_ROOT)
    return [
        os.path.join(root, "gat", "demo", "model.ifc"),
        os.path.join(root, ".", "gat", "demo", "model.ifc"),
        os.path.join(root, "gat", "demo", "..", "demo", "model.ifc"),
        os.path.join(root, "gat", "", "demo", "model.ifc"),
    ]


class LocationBoundDigestTests(unittest.TestCase):
    """The existing digest is location-bound. That is a fact, not a bug here."""

    def test_one_file_gives_several_world_digests(self) -> None:
        digests = {GatSession.load_ifc(p).world.digest() for p in _spellings()}
        self.assertGreater(
            len(digests),
            1,
            "world.digest() is expected to be location-bound; if this ever "
            "collapses to one value the portable digest below is redundant",
        )

    def test_source_meta_is_the_spelling_that_was_passed(self) -> None:
        for path in _spellings():
            module = GatSession.load_ifc(path).world.module
            self.assertEqual(module.meta["source"], path)


class PortableDigestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.worlds = [GatSession.load_ifc(p).world for p in _spellings()]

    def test_every_spelling_gives_one_portable_digest(self) -> None:
        portable = {portable_world_digest(w) for w in self.worlds}
        self.assertEqual(len(portable), 1, "portable digest must not see the path")

    def test_same_world_holds_across_spellings(self) -> None:
        first = self.worlds[0]
        for other in self.worlds[1:]:
            self.assertTrue(same_world(first, other))

    def test_the_two_identities_are_not_the_same_number(self) -> None:
        world = self.worlds[0]
        self.assertNotEqual(world.digest(), portable_world_digest(world))

    def test_a_different_model_is_a_different_portable_world(self) -> None:
        beam = GatSession.load_ifc(str(BEAM)).world
        self.assertNotEqual(
            portable_world_digest(beam), portable_world_digest(self.worlds[0])
        )
        self.assertFalse(same_world(beam, self.worlds[0]))

    def test_belief_still_participates(self) -> None:
        # Eliding the path must not elide the state: an observation has to move
        # the portable digest, or it would not identify a world at all.
        session = GatSession.load_ifc(str(MODEL))
        before = portable_world_digest(session.world)
        session.run(
            ObserveQuantity.single(session.var("Office-A", "Volume"), 59.4, 0.05)
        )
        self.assertNotEqual(portable_world_digest(session.world), before)

    def test_scope_is_not_elided(self) -> None:
        # lowering_scope is what the world IS, not where it came from.
        scoped = GatSession.load_ifc(
            str(BEAM), scope=IfcLoweringScope(frozenset({"GATBEAMELEMENT00000100"}))
        ).world
        whole = GatSession.load_ifc(str(BEAM)).world
        self.assertNotEqual(
            portable_module_digest(scoped.module), portable_module_digest(whole.module)
        )

    def test_only_location_keys_are_elided(self) -> None:
        module = self.worlds[0].module
        elided = portable_meta(module.meta)
        self.assertEqual(set(elided), set(module.meta))
        for key, value in module.meta.items():
            if key in LOCATION_META_KEYS:
                self.assertNotEqual(elided[key], value)
            else:
                self.assertEqual(elided[key], value)
        self.assertEqual(LOCATION_META_KEYS, ("source",))


class WorldIdentityRecordTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.world = GatSession.load_ifc(str(MODEL)).world
        cls.record = world_identity(cls.world)

    def test_record_carries_both_identities_and_the_source(self) -> None:
        self.assertEqual(self.record["schema"], IDENTITY_SCHEMA)
        self.assertEqual(self.record["claim_scope"], "record-integrity-only")
        self.assertEqual(self.record["world_digest"], self.world.digest())
        self.assertEqual(
            self.record["portable_digest"], portable_world_digest(self.world)
        )
        self.assertEqual(self.record["source"], str(MODEL))
        self.assertEqual(self.record["location_meta_elided"], ["source"])

    def test_record_says_which_one_to_cite(self) -> None:
        self.assertIn("portable", self.record["rule"])

    def test_computing_the_identity_does_not_move_the_frozen_digest(self) -> None:
        # Additive means additive: the kernel's own digest for the relative
        # spelling CI uses must be exactly what it has always been.
        session = GatSession.load_ifc("gat/demo/model.ifc")
        world_identity(session.world)
        portable_world_digest(session.world)
        self.assertEqual(
            session.world.digest(),
            "020383e8c426afc5cb5385de429c5a6b4fd98416c060ee16122b3ea98a2c30f5",
        )


if __name__ == "__main__":
    unittest.main()
