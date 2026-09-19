"""Lowering invariants as metamorphic relations, over generated variants.

The suite already asserts that configuration_digest survives one hand-built
variant with hard-coded step ids. The relation is more general than that, and
stating it generally says something the single case cannot: which group each
digest quotients by.

    transformation        world.digest()     configuration_digest
    reorder STEP lines    invariant          invariant
    renumber step ids     invariant          invariant
    relabel GlobalIds     changes            invariant
    rename entities       changes            invariant

Two nested quotients, and each line is a fact about the design. world.digest()
already quotients by file-level artifacts: STEP line order is not semantic
because references are by id, and step ids do not reach the digest at all
because the printer omits slot source_ref -- a step id is provenance into the
source file, not state. configuration_digest quotients further, by identity and
naming, which is what makes it the configuration rather than the lowering.

Under all four the numeric state is preserved to within one unit in the last
place; ReassociationBoundTests below pins that bound and says why it is not
exact.

Deterministic by construction -- a fixed list of seeds, random.Random per seed,
no clock and no entropy -- so a failure is reproducible from its seed.

stdlib unittest only.
"""

from __future__ import annotations

import random
import re
import unittest
from pathlib import Path

import numpy as np

from gat.engine.configuration import configuration_digest
from gat.session import GatSession

_ROOT = Path(__file__).resolve().parents[1]
MODEL = _ROOT / "gat" / "demo" / "model.ifc"

#: Enough variants to exercise the relation without making the suite slow.
SEEDS = (1, 2, 3, 5, 8, 13, 21, 34)

#: A relabelling permutes EntityId sort order, which is the order a rollup
#: ScaledSum accumulates in, so float addition reassociates. Four eps of
#: headroom over the measured single-ULP worst case.
MEAN_REASSOCIATION_RTOL = 4.0 * float(np.finfo(np.float64).eps)

_GLOBAL_ID = re.compile(r"'(GAT[A-Z]{3}\d{16})'")


def _text() -> str:
    return MODEL.read_text(encoding="utf-8")


def reorder(text: str, rng: random.Random) -> str:
    """Shuffle the DATA section. STEP references are by id, so order is not
    semantic -- and nothing else in the suite says so."""
    head, _, rest = text.partition("DATA;")
    body, _, tail = rest.rpartition("ENDSEC;")
    lines = [line for line in body.strip().splitlines() if line.strip()]
    shuffled = lines[:]
    rng.shuffle(shuffled)
    return head + "DATA;\n" + "\n".join(shuffled) + "\nENDSEC;" + tail


def renumber(text: str, rng: random.Random) -> str:
    """Shift every step id by a constant. Collision-free for any offset."""
    offset = rng.randrange(1000, 90000)
    return re.sub(r"#(\d+)", lambda m: f"#{int(m.group(1)) + offset}", text)


def relabel(text: str, rng: random.Random) -> str:
    """Replace every GlobalId with a fresh unique one of the same shape."""
    ids = sorted(set(_GLOBAL_ID.findall(text)))
    order = list(range(len(ids)))
    rng.shuffle(order)
    for gid, index in zip(ids, order):
        text = text.replace(f"'{gid}'", f"'Z{index:021d}'")
    return text


def rename(text: str, rng: random.Random, names: tuple[str, ...]) -> str:
    """Rename every lowered entity. Quantity and pset names are untouched."""
    for index, name in enumerate(names):
        token = f"'{name}'"
        if token in text:
            text = text.replace(token, f"'Renamed-{rng.randrange(10**6)}-{index}'")
    return text


class MetamorphicLoweringTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.base = GatSession.from_text(_text(), source="base")
        cls.base_config = configuration_digest(cls.base.world)
        cls.base_world = cls.base.world.digest()
        cls.names = tuple(
            sorted(entity.name for entity in cls.base.world.module.entities.values())
        )
        # The relabel/rename transformations are only meaningful if there is
        # something to relabel. The demo lowers ten products; IfcProject and
        # IfcBuilding are not lowered, so this is the whole set.
        assert len(cls.names) == 10, cls.names

    def _assert_same_physics(self, variant: GatSession, label: str) -> None:
        base = self.base.world
        other = variant.world
        self.assertEqual(
            len(other.module.entities), len(base.module.entities), label
        )
        self.assertEqual(other.binding.n_raw, base.binding.n_raw, label)
        self.assertEqual(other.binding.n_full, base.binding.n_full, label)
        # Not bitwise: a rollup ScaledSum accumulates in EntityId sort order,
        # so relabelling reassociates the addition. Measured worst case over
        # every variant here is 0.96 * eps, i.e. one unit in the last place.
        # Asserting a few eps keeps that honest and would still catch a real
        # numeric change, which would be orders of magnitude larger.
        self.assertTrue(
            np.allclose(
                np.sort(other.full.mu),
                np.sort(base.full.mu),
                rtol=MEAN_REASSOCIATION_RTOL,
                atol=0.0,
            ),
            f"{label}: full-view mean moved beyond float reassociation",
        )
        self.assertTrue(variant.verify().passed, f"{label}: invariants failed")

    def test_reorder_changes_nothing_at_all(self) -> None:
        for seed in SEEDS:
            with self.subTest(seed=seed):
                rng = random.Random(seed)
                session = GatSession.from_text(reorder(_text(), rng), source="base")
                self.assertEqual(session.world.digest(), self.base_world)
                self.assertEqual(configuration_digest(session.world), self.base_config)
                self._assert_same_physics(session, f"reorder/{seed}")

    def test_renumber_moves_provenance_but_not_either_digest(self) -> None:
        for seed in SEEDS:
            with self.subTest(seed=seed):
                rng = random.Random(seed)
                session = GatSession.from_text(renumber(_text(), rng), source="base")
                self.assertEqual(configuration_digest(session.world), self.base_config)
                # Step ids do reach the module, as slot source_ref, but the
                # printer omits them: a step id is provenance into the source
                # file, not state. So even the concrete lowering is unchanged.
                self.assertEqual(session.world.digest(), self.base_world)
                self.assertNotEqual(
                    [slot.source_ref for slot in session.world.module.all_slots()],
                    [slot.source_ref for slot in self.base.world.module.all_slots()],
                    "renumbering must actually have moved the source refs",
                )
                self._assert_same_physics(session, f"renumber/{seed}")

    def test_relabel_is_quotiented_by_the_configuration_digest(self) -> None:
        for seed in SEEDS:
            with self.subTest(seed=seed):
                rng = random.Random(seed)
                session = GatSession.from_text(relabel(_text(), rng), source="base")
                self.assertEqual(configuration_digest(session.world), self.base_config)
                self.assertNotEqual(session.world.digest(), self.base_world)
                self._assert_same_physics(session, f"relabel/{seed}")
                # every GlobalId really did change
                for eid in session.world.module.entities:
                    self.assertTrue(eid.global_id.startswith("Z"), eid)

    def test_rename_is_quotiented_by_the_configuration_digest(self) -> None:
        for seed in SEEDS:
            with self.subTest(seed=seed):
                rng = random.Random(seed)
                session = GatSession.from_text(
                    rename(_text(), rng, self.names), source="base"
                )
                self.assertEqual(configuration_digest(session.world), self.base_config)
                self.assertNotEqual(session.world.digest(), self.base_world)
                self._assert_same_physics(session, f"rename/{seed}")

    def test_the_whole_quotient_at_once(self) -> None:
        for seed in SEEDS:
            with self.subTest(seed=seed):
                rng = random.Random(seed)
                text = reorder(_text(), rng)
                text = renumber(text, rng)
                text = relabel(text, rng)
                text = rename(text, rng, self.names)
                session = GatSession.from_text(text, source="base")
                self.assertEqual(configuration_digest(session.world), self.base_config)
                self.assertNotEqual(session.world.digest(), self.base_world)
                self._assert_same_physics(session, f"composed/{seed}")

    def test_a_transformation_that_is_physics_does_move_the_quotient(self) -> None:
        # Control: if configuration_digest were invariant under everything it
        # would be measuring nothing. Changing a declared length must move it.
        text = _text().replace("IFCQUANTITYLENGTH('Length',$,$,9.2", "IFCQUANTITYLENGTH('Length',$,$,9.3", 1)
        self.assertNotEqual(text, _text(), "the control edit did not apply")
        session = GatSession.from_text(text, source="base")
        self.assertNotEqual(configuration_digest(session.world), self.base_config)


class ReassociationBoundTests(unittest.TestCase):
    """The one place these transformations are not exact, bounded and named.

    TotalWallCost is a ScaledSum over the storey's walls, accumulated in
    EntityId sort order. Relabelling permutes that order, so the sum
    reassociates and the result can differ in its last bit. The quotient
    (configuration_digest) is unaffected because it is structural, not a
    function of the propagated mean.

    Pinning the bound matters: at one ULP this is float arithmetic, and
    anything larger would be a real change of state wearing the same disguise.
    Making it exact would need a naming-independent accumulation order or
    compensated summation, either of which moves the demo model's world digest
    -- a version bump, not a repair.
    """

    def test_reassociation_stays_within_one_ulp(self) -> None:
        base = GatSession.from_text(_text(), source="base").world
        names = tuple(sorted(e.name for e in base.module.entities.values()))
        worst = 0.0
        for seed in SEEDS:
            for label, transform in (
                ("reorder", lambda t, r: reorder(t, r)),
                ("renumber", lambda t, r: renumber(t, r)),
                ("relabel", lambda t, r: relabel(t, r)),
                ("rename", lambda t, r: rename(t, r, names)),
            ):
                world = GatSession.from_text(
                    transform(_text(), random.Random(seed)), source="base"
                ).world
                left = np.sort(world.full.mu)
                right = np.sort(base.full.mu)
                relative = np.abs(left - right) / np.maximum(np.abs(right), 1e-300)
                worst = max(worst, float(np.max(relative)))
        eps = float(np.finfo(np.float64).eps)
        self.assertGreater(worst, 0.0, "expected reassociation to be observable")
        self.assertLess(worst, 2.0 * eps, f"worst relative drift {worst} exceeds 2 eps")


if __name__ == "__main__":
    unittest.main()
