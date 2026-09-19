"""A world identity that depends on neither the file's name nor the processor.

World.digest() hashes the printer dump, which emits every meta key including
"source" -- the path string the caller passed to load_ifc -- and then the
full-view mean and covariance as raw float64 bytes. So one file yields a
different world digest per spelling AND per CPU, because BLAS sums the
covariance in a kernel-dependent order. A pinned world_digest in validation/ is
reproducible only from the exact checkout, the exact spelling, and the same
processor.

portable_world_digest removes both dependencies: "source" is elided from the
module, and the full view is hashed as canonical decimal text at
PORTABLE_SIGNIFICANT_DIGITS instead of as machine words. Measured across five
forced OpenBLAS kernels, World.digest() takes four distinct values on
gat/demo/model.ifc and portable_world_digest takes one.

These tests pin every half: that the local digest really is location-bound and
belief-bound (so nobody mistakes it for portable), that the portable one is
neither, that the quantization is coarse enough to absorb the measured
cross-kernel wobble with a margin, and that the coarseness is declared in the
record rather than implied.

stdlib unittest only.
"""

from __future__ import annotations

import hashlib
import os
import sys
import unittest
from pathlib import Path

import numpy

from gat.adapters.portable_identity import (
    IDENTITY_SCHEMA,
    LOCATION_META_KEYS,
    portable_meta,
    portable_module_digest,
    PORTABLE_SIGNIFICANT_DIGITS,
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

    def test_computing_the_identity_does_not_move_the_module_digest_or_the_mean(
        self,
    ) -> None:
        """Pin the two parts of World.digest() that are facts about the model.

        This test used to pin the composite world digest to
        020383e8..., and CI proved that wrong. World.digest() is sha256 over
        three things -- the module digest, then full.mu and full.sigma as raw
        float64 bytes -- and the third is not reproducible across machines.
        Measured here by forcing OpenBLAS kernels with OPENBLAS_CORETYPE:

            SKYLAKEX     020383e8...   (this container, and the old pin)
            HASWELL      6df20d41...   (what CI reported)
            ZEN          6df20d41...
            SANDYBRIDGE  b18ff0a9...
            NEHALEM      c4a8d1b7...

        Four digests, one file, one numpy, one Python. The cause is last-bit
        reassociation in the BLAS that builds the full-view covariance:
        SKYLAKEX against HASWELL differs in 2 of 3969 entries, by at most
        1.920e-16 relative, which is 0.86 eps. Numerically nothing; to sha256,
        a different world.

        So the module digest and the mean are pinned exactly -- both were
        bit-identical under all five kernels -- and the covariance is not. See
        docs/digest-portability-v1.md.
        """
        session = GatSession.load_ifc("gat/demo/model.ifc")
        world_identity(session.world)
        portable_world_digest(session.world)
        world = session.world
        context = (
            f"source={world.module.meta.get('source')!r} "
            f"numpy={numpy.__version__} python={sys.version.split()[0]}"
        )
        self.assertEqual(
            world.module.digest(),
            "cec15f081dfe1c9f6032ed492d2e0e238ab69566eda6be3db51f00552ab2e225",
            context,
        )
        self.assertEqual(
            hashlib.sha256(world.full.mu.tobytes()).hexdigest(),
            "cf76cfddbb404f5955630410fc64035ec41fef688da40f60c3fc15cae7f06f0f",
            context,
        )
        self.assertEqual(world.full.mu.shape, (63,))
        self.assertEqual(world.full.sigma.shape, (63, 63))

    def test_the_world_digest_is_that_composition_and_nothing_else(self) -> None:
        # Recomposing it by hand is what licenses the claim above: if the
        # composition ever grows a fourth input, the reasoning about which parts
        # are portable stops holding and this fails.
        world = GatSession.load_ifc("gat/demo/model.ifc").world
        recomposed = hashlib.sha256()
        recomposed.update(world.module.digest().encode())
        recomposed.update(world.full.mu.tobytes())
        recomposed.update(world.full.sigma.tobytes())
        self.assertEqual(world.digest(), recomposed.hexdigest())

    def test_one_ulp_in_the_covariance_moves_the_whole_world_digest(self) -> None:
        # The mechanism, stated so it cannot be mistaken for flakiness. This
        # holds on every machine, which is exactly why the composite cannot be
        # pinned on any of them.
        world = GatSession.load_ifc("gat/demo/model.ifc").world
        nudged = world.full.sigma.copy()
        self.assertNotEqual(nudged[0, 0], 0.0, "need a nonzero entry to nudge")
        nudged[0, 0] = numpy.nextafter(nudged[0, 0], numpy.inf)

        relative = abs(nudged[0, 0] - world.full.sigma[0, 0]) / abs(
            world.full.sigma[0, 0]
        )
        self.assertLess(relative, numpy.finfo(numpy.float64).eps)

        after = hashlib.sha256()
        after.update(world.module.digest().encode())
        after.update(world.full.mu.tobytes())
        after.update(nudged.tobytes())
        self.assertNotEqual(world.digest(), after.hexdigest())

    def test_a_one_ulp_nudge_does_NOT_move_the_portable_digest(self) -> None:
        """The whole point, stated against the local digest's behaviour.

        test_one_ulp_in_the_covariance_moves_the_whole_world_digest shows a single
        ULP flipping World.digest(). The portable digest must absorb exactly that,
        or eliding `source` was the only thing it ever did.
        """
        world = GatSession.load_ifc("gat/demo/model.ifc").world
        before = portable_world_digest(world)

        nudged = world.full.sigma.copy()
        self.assertNotEqual(nudged[0, 0], 0.0)
        for _ in range(3):
            nudged[0, 0] = numpy.nextafter(nudged[0, 0], numpy.inf)
        relative = abs(nudged[0, 0] - world.full.sigma[0, 0]) / abs(
            world.full.sigma[0, 0]
        )
        self.assertLess(relative, 1e-15)

        moved = world.with_belief(world.belief)
        # with_belief alone moves neither digest, so it is a clean baseline.
        self.assertEqual(moved.digest(), world.digest())
        self.assertEqual(portable_world_digest(moved), before)

        object.__setattr__(moved.full, "sigma", nudged)
        # Guard against a vacuous pass: the nudge must have reached the array the
        # digests are computed from, and must have moved the local digest.
        self.assertEqual(moved.full.sigma[0, 0], nudged[0, 0])
        self.assertNotEqual(moved.digest(), world.digest())

        # The payoff: the portable digest absorbed what the local one could not.
        self.assertEqual(portable_world_digest(moved), before)

    def test_the_quantization_margin_survives_the_measured_wobble(self) -> None:
        """Twelve digits was chosen from a measurement. Keep the measurement.

        The worst cross-kernel relative difference observed was 1.920e-16. A
        rounding flip needs a value within its own wobble of a boundary, so the
        margin is per-value. Measured over every full-view value of both shipped
        models, the worst ratio was 2620 for the office model and 3420 for the
        beam. This fails if a model ever drifts close enough to make the digit
        count unsafe -- which is the only thing that could silently un-portable
        this digest.
        """
        worst_relative_error = 1.920e-16
        digits = PORTABLE_SIGNIFICANT_DIGITS
        for model in ("gat/demo/model.ifc", "gat/demo/beam_model.ifc"):
            world = GatSession.load_ifc(model).world
            values = numpy.concatenate(
                [
                    numpy.asarray(world.full.mu, dtype=float).ravel(),
                    numpy.asarray(world.full.sigma, dtype=float).ravel(),
                ]
            )
            magnitude = numpy.abs(values)
            magnitude = magnitude[magnitude != 0.0]
            decade = numpy.floor(numpy.log10(magnitude))
            factor = 10.0 ** (digits - 1 - decade)
            scaled = magnitude * factor
            to_boundary = numpy.abs(0.5 - numpy.abs(scaled - numpy.round(scaled)))
            margin = to_boundary / factor
            ratio = margin / (magnitude * worst_relative_error)
            with self.subTest(model=model):
                self.assertGreater(
                    float(ratio.min()),
                    100.0,
                    f"{model} now has a full-view value only {ratio.min():.3g}x "
                    "its own cross-kernel wobble from a rounding boundary; "
                    f"{digits} significant digits is no longer a safe quantum",
                )

    def test_the_record_declares_how_coarse_the_portable_digest_is(self) -> None:
        # A coarser identity that does not say how coarse is worse than a precise
        # one, because a reader cannot tell what "equal" bought them.
        world = GatSession.load_ifc("gat/demo/model.ifc").world
        record = world_identity(world)
        self.assertEqual(
            record["portable_significant_digits"], PORTABLE_SIGNIFICANT_DIGITS
        )
        self.assertIn("significant digits", record["rule"])
        self.assertIn("any", record["rule"])

    def test_the_portable_digest_hashes_text_not_machine_words(self) -> None:
        # Decimal text, so the hashed object is the same kind the module digest
        # already is, and no 10**k rounding or banker's-tie can differ by build.
        from gat.adapters.portable_identity import _canonical_number

        self.assertEqual(_canonical_number(1.0), "1.00000000000e+00")
        self.assertEqual(len(_canonical_number(1.0).split("e")[0].replace(".", "").lstrip("-")), 12)
        # A ULP apart, one string.
        value = 4.55e4
        self.assertEqual(
            _canonical_number(value),
            _canonical_number(numpy.nextafter(value, numpy.inf)),
        )

    def test_the_digest_is_stable_within_one_machine(self) -> None:
        # What the freeze can actually rely on: replay on the same machine. Two
        # independent lowerings of the same file agree bit for bit.
        first = GatSession.load_ifc("gat/demo/model.ifc").world
        second = GatSession.load_ifc("gat/demo/model.ifc").world
        self.assertEqual(first.digest(), second.digest())
        self.assertEqual(
            first.full.sigma.tobytes(),
            second.full.sigma.tobytes(),
            "same machine, same bytes -- if this fails the problem is not BLAS",
        )


if __name__ == "__main__":
    unittest.main()
