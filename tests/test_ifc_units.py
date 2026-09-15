"""End-to-end IFC source-unit normalization and export tests."""

from __future__ import annotations

import os
import re
import tempfile
import unittest

import numpy as np

import gat.demo
from gat.adapters.ifc.parser import EnumVal, RawInstance, Typed, parse_ifc
from gat.adapters.ifc.units import length_unit_context
from gat.adapters.ifc.writer import _serialize_instance, _serialize_value
from gat.engine.transform import SetParameter
from gat.errors import LoweringError
from gat.ir.core import Unit
from gat.session import GatSession


MODEL = os.path.join(os.path.dirname(gat.demo.__file__), "model.ifc")


def _typed_scaled(value: object, factor: float) -> object:
    if isinstance(value, Typed) and len(value.args) == 1:
        inner = value.args[0]
        if isinstance(inner, (int, float)) and not isinstance(inner, bool):
            return Typed(value.name, (float(inner) * factor,))
    return value


def _source_in_millimetres(text: str) -> str:
    """Re-express every demo length and length sigma in project millimetres."""
    file = parse_ifc(text)
    instances: dict[int, RawInstance] = {}
    length_sigma_names = {
        "ClearHeightSigma",
        "LengthSigma",
        "WidthSigma",
        "HeightSigma",
    }
    for step_id, inst in file.instances.items():
        args = list(inst.args)
        if (
            inst.type_name == "IFCSIUNIT"
            and len(args) > 3
            and isinstance(args[1], EnumVal)
            and args[1].name == "LENGTHUNIT"
        ):
            args[2] = EnumVal("MILLI")
        elif inst.type_name == "IFCQUANTITYLENGTH":
            args[3] = float(args[3]) * 1000.0
        elif inst.type_name == "IFCCARTESIANPOINT":
            args[0] = tuple(float(value) * 1000.0 for value in args[0])
        elif (
            inst.type_name == "IFCPROPERTYSINGLEVALUE"
            and args
            and args[0] in length_sigma_names
        ):
            args[2] = _typed_scaled(args[2], 1000.0)
        instances[step_id] = RawInstance(step_id, inst.type_name, tuple(args))

    lines = ["ISO-10303-21;", "HEADER;"]
    for key, header_args in file.header.items():
        lines.append(f"{key}({','.join(_serialize_value(v) for v in header_args)});")
    lines.extend(["ENDSEC;", "DATA;"])
    lines.extend(_serialize_instance(instances[step_id]) for step_id in sorted(instances))
    lines.extend(["ENDSEC;", "END-ISO-10303-21;"])
    return "\n".join(lines) + "\n"


class IfcUnitNormalizationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        with open(MODEL, "r", encoding="utf-8") as stream:
            cls.metre_text = stream.read()
        cls.millimetre_text = _source_in_millimetres(cls.metre_text)

    def test_unit_context_resolves_si_prefix(self) -> None:
        context = length_unit_context(parse_ifc(self.millimetre_text))
        self.assertEqual(context.scale_to_metres, 0.001)
        self.assertEqual(context.label, "MILLI METRE")
        self.assertTrue(context.normalization_required)
        self.assertEqual(context.to_metres(3400.0), 3.4)
        self.assertEqual(context.from_metres(3.4), 3400.0)

    def test_metre_and_millimetre_sources_compile_to_same_numeric_state(self) -> None:
        metre = GatSession.from_text(self.metre_text, source="metre.ifc")
        millimetre = GatSession.from_text(
            self.millimetre_text, source="millimetre.ifc"
        )
        self.assertEqual(metre.world.binding.raw_index.vars, millimetre.world.binding.raw_index.vars)
        np.testing.assert_allclose(
            metre.world.belief.mu, millimetre.world.belief.mu, atol=5e-15, rtol=0.0
        )
        np.testing.assert_allclose(
            metre.world.belief.sigma,
            millimetre.world.belief.sigma,
            atol=1e-18,
            rtol=0.0,
        )
        np.testing.assert_allclose(
            metre.world.full.mu, millimetre.world.full.mu, atol=1e-14, rtol=0.0
        )
        np.testing.assert_allclose(
            metre.world.full.sigma,
            millimetre.world.full.sigma,
            atol=2e-14,
            rtol=0.0,
        )
        for eid in metre.world.module.entities:
            self.assertEqual(
                metre.world.module.entities[eid].placement,
                millimetre.world.module.entities[eid].placement,
            )
        party_length = millimetre.world.module.slot(
            millimetre.var("Wall-Party", "Length")
        )
        self.assertEqual(party_length.prior_sigma, 0.004)
        self.assertTrue(millimetre.verify().passed)

    def test_millimetre_export_restores_source_means_and_sigmas(self) -> None:
        session = GatSession.from_text(self.millimetre_text, source="millimetre.ifc")
        clear_height = session.var("Level 1", "ClearHeight")
        session.run(SetParameter(clear_height, 3.4, design_sigma=0.01))
        with tempfile.TemporaryDirectory() as directory:
            output = os.path.join(directory, "millimetre-output.ifc")
            session.export_ifc(output)
            with open(output, "r", encoding="utf-8") as stream:
                exported = stream.read()
            reloaded = GatSession.load_ifc(output)

        height_match = re.search(
            r"#29=IFCQUANTITYLENGTH\('ClearHeight',\$,\$,([^)]+)\);",
            exported,
        )
        self.assertIsNotNone(height_match)
        self.assertEqual(float(height_match.group(1)), 3400.0)
        sigma_match = re.search(
            r"IFCPROPERTYSINGLEVALUE\('ClearHeightSigma','posterior standard deviation',"
            r"IFCREAL\(([^)]+)\),\$\)",
            exported,
        )
        self.assertIsNotNone(sigma_match)
        self.assertEqual(float(sigma_match.group(1)), 10.0)
        self.assertIn("IFCSIUNIT(*,.LENGTHUNIT.,.MILLI.,.METRE.)", exported)
        np.testing.assert_allclose(
            reloaded.world.belief.mu, session.world.belief.mu, atol=1e-12, rtol=0.0
        )
        np.testing.assert_allclose(
            reloaded.world.belief.sigma,
            session.world.belief.sigma,
            atol=1e-15,
            rtol=0.0,
        )

    def test_conversion_based_length_unit_remains_fail_closed(self) -> None:
        extra = "#998=IFCCONVERSIONBASEDUNIT($,.LENGTHUNIT.,'FOOT',$);\n"
        text = self.metre_text.replace("ENDSEC;\nEND-ISO", extra + "ENDSEC;\nEND-ISO")
        with self.assertRaisesRegex(LoweringError, "conversion-based length units"):
            GatSession.from_text(text)

    def test_unassigned_conversion_unit_does_not_override_project_context(self) -> None:
        project = (
            "#1=IFCPROJECT('GATPRJ0000000000000001',$,'GAT Demo Project',"
            "$,$,$,$,$,#997);"
        )
        text = self.metre_text.replace(
            "#1=IFCPROJECT('GATPRJ0000000000000001',$,'GAT Demo Project',$,$,$,$,$,$);",
            project,
        )
        extra = (
            "#997=IFCUNITASSIGNMENT((#2));\n"
            "#998=IFCCONVERSIONBASEDUNIT($,.LENGTHUNIT.,'FOOT',$);\n"
        )
        text = text.replace("ENDSEC;\nEND-ISO", extra + "ENDSEC;\nEND-ISO")
        session = GatSession.from_text(text)
        self.assertEqual(
            session.world.module.meta["ifc_length_scale_to_metres"], "1.0"
        )

    def test_conflicting_si_length_units_are_rejected(self) -> None:
        extra = "#998=IFCSIUNIT(*,.LENGTHUNIT.,.MILLI.,.METRE.);\n"
        text = self.metre_text.replace("ENDSEC;\nEND-ISO", extra + "ENDSEC;\nEND-ISO")
        with self.assertRaisesRegex(LoweringError, "ambiguous project length units"):
            GatSession.from_text(text)


class DimensionalScalingTests(unittest.TestCase):
    """Change only the declared unit and every quantity must move by the
    right POWER of the scale.

    The existing metre-vs-millimetre test rescales the literals too, so both
    files describe the same building and must agree. That is the right
    invariant and it cannot see a dimensional error: an area derived from two
    normalized lengths comes out the same either way even if the adapter
    treated it as a length. Changing the declaration alone separates them --
    a length must move by s, an area by s**2, a volume by s**3, and a currency
    must not move at all.
    """

    MODEL = os.path.join(os.path.dirname(gat.demo.__file__), "model.ifc")

    POWERS = {Unit.M: 1, Unit.M2: 2, Unit.M3: 3}

    def _redeclared(self, prefix: str) -> GatSession:
        with open(self.MODEL, encoding="utf-8") as handle:
            text = handle.read()
        swapped = text.replace(
            "IFCSIUNIT(*,.LENGTHUNIT.,$,.METRE.)",
            f"IFCSIUNIT(*,.LENGTHUNIT.,{prefix},.METRE.)",
        )
        self.assertNotEqual(swapped, text, "the metre declaration moved")
        return GatSession.from_text(swapped, source="redeclared.ifc")

    def test_every_quantity_scales_by_the_power_of_its_unit(self) -> None:
        base = GatSession.load_ifc(self.MODEL)
        for prefix, scale in ((".MILLI.", 1e-3), (".KILO.", 1e3)):
            session = self._redeclared(prefix)
            with self.subTest(prefix=prefix):
                checked = 0
                for eid, entity in session.world.module.entities.items():
                    reference = base.world.module.entities[eid]
                    for quantity, slot in entity.slots.items():
                        was = reference.slots[quantity].prior_mu
                        power = self.POWERS.get(slot.unit, 0)
                        expected = was * scale**power
                        self.assertAlmostEqual(
                            slot.prior_mu,
                            expected,
                            delta=max(abs(expected) * 1e-9, 1e-15),
                            msg=f"{eid.global_id}.{quantity} [{slot.unit.value}]",
                        )
                        checked += 1
                self.assertGreater(checked, 20, "the sweep must cover the model")

    def test_a_currency_quantity_does_not_move_with_the_length_unit(self) -> None:
        """The guard that would catch a blanket rescale: at least one slot
        must be dimensionless, or the test above proves nothing about power 0."""
        base = GatSession.load_ifc(self.MODEL)
        dimensionless = [
            (eid, q)
            for eid, entity in base.world.module.entities.items()
            for q, slot in entity.slots.items()
            if slot.unit not in self.POWERS
        ]
        self.assertTrue(dimensionless, "model has no dimensionless quantity")
        session = self._redeclared(".MILLI.")
        for eid, quantity in dimensionless:
            self.assertEqual(
                session.world.module.entities[eid].slots[quantity].prior_mu,
                base.world.module.entities[eid].slots[quantity].prior_mu,
            )


if __name__ == "__main__":
    unittest.main()
