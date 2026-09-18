"""A scope may name an engineering element that has no GAT contract.

Unscoped, an unannotated beam stays opaque -- that is what keeps an ordinary
exported beam out of the architectural path, and tests/test_beam_assurance.py
pins it. Named by an explicit scope it joins the world, but at its declared
dimensions only: no GAT_Structural pset means no AISC capacity slots and none
of the restatement constraints that depend on them.

validation/clinic-w460x60-scoped-world-v1.json pins that behaviour on a public
model ("Scoped lowering created a Length-only world"). That file was read by
nothing, so the behaviour was free to regress, and had. The corpus-gated test
at the bottom holds it to the pin again; everything above it runs without the
corpus so CI guards the lowering rule itself.

stdlib unittest only.
"""

from __future__ import annotations

import json
import os
import unittest
from pathlib import Path

from gat.adapters.ifc.lower import _declared_fallback
from gat.adapters.ifc.parser import parse_ifc_file
from gat.adapters.ifc.reader import properties_of, pset_single_number
from gat.adapters.ifc.scope import IfcLoweringScope
from gat.adapters.portable_identity import portable_world_digest
from gat.errors import LoweringError
from gat.session import GatSession

_ROOT = Path(__file__).resolve().parents[1]
BEAM_MODEL = _ROOT / "gat" / "demo" / "beam_model.ifc"
BEAM_ID = "GATBEAMELEMENT00000100"
PIN = _ROOT / "validation" / "clinic-w460x60-scoped-world-v1.json"
CORPUS = os.environ.get("GAT_IFC_VALIDATION_ROOT")


def _unannotated() -> str:
    text = BEAM_MODEL.read_text(encoding="utf-8")
    return text.replace("'GAT_Structural'", "'External_Structural_Data'")


class ScopedOpaqueAdmissionTests(unittest.TestCase):
    def test_unscoped_it_stays_opaque(self) -> None:
        # The existing contract, restated here so the pair reads together.
        session = GatSession.from_text(_unannotated(), "unannotated-beam.ifc")
        self.assertFalse(
            any(e.id.ifc_class == "IfcBeam" for e in session.world.module.entities.values())
        )

    def test_named_by_a_scope_it_lowers_without_capacity_slots(self) -> None:
        session = GatSession.from_text(
            _unannotated(),
            "unannotated-beam.ifc",
            scope=IfcLoweringScope(frozenset({BEAM_ID})),
        )
        entities = session.world.module.entities
        self.assertEqual(len(entities), 1)
        entity = next(iter(entities.values()))
        self.assertEqual(entity.id.ifc_class, "IfcBeam")
        self.assertEqual(entity.id.global_id, BEAM_ID)
        # Declared dimension only.
        self.assertIn("Length", entity.slots)
        for capacity in (
            "YieldStrengthMPa",
            "PlasticSectionModulusMajorM3",
            "NominalMomentCapacity",
            "DesignMomentCapacity",
        ):
            self.assertNotIn(capacity, entity.slots)
        # No contract means no AISC attributes and no capacity restatements.
        # The physical NonNegative on Length stays: that is not a contract
        # claim, it is what a length is.
        self.assertNotIn("resistance_factor", entity.attrs)
        constraints = session.world.module.constraints
        self.assertEqual(
            [type(c).__name__ for c in constraints],
            ["NonNegative"],
        )
        self.assertEqual(constraints[0].var.quantity, "Length")
        self.assertTrue(session.verify().passed)

    def test_the_annotated_beam_still_gets_its_contract_under_a_scope(self) -> None:
        session = GatSession.load_ifc(
            str(BEAM_MODEL), scope=IfcLoweringScope(frozenset({BEAM_ID}))
        )
        entity = next(iter(session.world.module.entities.values()))
        self.assertIn("YieldStrengthMPa", entity.slots)
        self.assertIn("DesignMomentCapacity", entity.slots)
        self.assertIn("resistance_factor", entity.attrs)
        kinds = {type(c).__name__ for c in session.world.module.constraints}
        self.assertIn("ExprEquals", kinds, "capacity restatements must be present")

    def test_a_scope_naming_nothing_in_the_file_still_fails_closed(self) -> None:
        with self.assertRaisesRegex(LoweringError, "absent"):
            GatSession.from_text(
                _unannotated(),
                "unannotated-beam.ifc",
                scope=IfcLoweringScope(frozenset({"not-a-real-global-id"})),
            )


class DeclaredFallbackGateTests(unittest.TestCase):
    """The pset fallback is narrow on purpose."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.file = parse_ifc_file(str(BEAM_MODEL))
        beam = next(iter(cls.file.by_type("IFCBEAM")))
        cls.defs = properties_of(cls.file, {beam.step_id}).get(beam.step_id, [])
        cls.scope = IfcLoweringScope(frozenset({BEAM_ID}))

    def _call(self, canonical, quantity, opaque, scope):
        return _declared_fallback(self.file, self.defs, canonical, quantity, opaque, scope)

    def test_never_applies_to_a_contract_bearing_product(self) -> None:
        self.assertIsNone(self._call("IfcBeam", "Length", False, self.scope))

    def test_never_applies_without_a_scope(self) -> None:
        self.assertIsNone(self._call("IfcBeam", "Length", True, None))

    def test_refused_when_the_scope_disallows_it(self) -> None:
        strict = IfcLoweringScope(frozenset({BEAM_ID}), allow_derived_beam_length=False)
        self.assertIsNone(self._call("IfcBeam", "Length", True, strict))

    def test_does_not_leak_to_other_classes_or_quantities(self) -> None:
        self.assertIsNone(self._call("IfcWall", "Length", True, self.scope))
        self.assertIsNone(self._call("IfcBeam", "Width", True, self.scope))

    def test_returns_none_when_the_standard_pset_is_absent(self) -> None:
        # The shipped fixture declares no Pset_BeamCommon, so this must fail
        # closed rather than invent a span.
        self.assertIsNone(self._call("IfcBeam", "Length", True, self.scope))

    def test_targeted_pset_read_finds_a_named_number(self) -> None:
        got = pset_single_number(self.file, self.defs, "GAT_Structural", "YieldStrengthMPa")
        self.assertIsNotNone(got)
        value, step = got
        self.assertGreater(value, 0.0)
        self.assertIsInstance(step, int)
        self.assertIsNone(
            pset_single_number(self.file, self.defs, "GAT_Structural", "NotThere")
        )
        self.assertIsNone(
            pset_single_number(self.file, self.defs, "NoSuchPset", "YieldStrengthMPa")
        )


@unittest.skipUnless(CORPUS, "public IFC corpus not fetched")
class ClinicScopedWorldPinTests(unittest.TestCase):
    """Hold the public-model behaviour to validation/clinic-w460x60-scoped-world-v1.json."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.pin = json.loads(PIN.read_text(encoding="utf-8"))
        cls.path = Path(CORPUS) / "buildingSMART-Clinic-Structural.ifc"
        cls.session = GatSession.load_ifc(
            str(cls.path),
            scope=IfcLoweringScope(frozenset({cls.pin["beam_global_id"]})),
        )

    def test_scoped_lowering_creates_a_length_only_world(self) -> None:
        world = self.session.world
        entity = next(iter(world.module.entities.values()))
        self.assertEqual(entity.id.global_id, self.pin["beam_global_id"])
        self.assertEqual(sorted(entity.slots), ["Length"])
        self.assertEqual(world.binding.n_raw, self.pin["raw_variables"])
        self.assertEqual(
            "YieldStrengthMPa" in entity.slots, self.pin["has_yield_strength"]
        )
        self.assertTrue(self.session.verify().passed)

    def test_length_comes_from_the_standard_span_property(self) -> None:
        # Pset_BeamCommon.Span, not a quantity set and not a mesh.
        entity = next(iter(self.session.world.module.entities.values()))
        self.assertAlmostEqual(entity.slots["Length"].prior_mu, 7.1388, places=4)
        self.assertGreater(entity.slots["Length"].prior_sigma, 0.0)

    def test_portable_digest_is_reproducible_where_the_pinned_one_is_not(self) -> None:
        # The pin's world_digest is path-bound (docs/world-identity-v1.md), so
        # it cannot be re-derived from a different checkout. The portable digest
        # can, and two spellings of the same file must agree on it.
        other = GatSession.load_ifc(
            os.path.join(str(self.path.parent), ".", self.path.name),
            scope=IfcLoweringScope(frozenset({self.pin["beam_global_id"]})),
        ).world
        self.assertEqual(
            portable_world_digest(other), portable_world_digest(self.session.world)
        )
        self.assertNotEqual(other.digest(), self.session.world.digest())


if __name__ == "__main__":
    unittest.main()
