"""Identity-bound IFC beam geometry derivation."""

from __future__ import annotations

import hashlib
import unittest

from gat.adapters.ifc.beam_geometry import (
    BEAM_GEOMETRY_METHOD,
    BeamGeometryStatus,
    derive_all_beam_geometry,
    derive_beam_geometry,
)
from gat.adapters.ifc.parser import parse_ifc


RECTANGULAR_BEAM = """ISO-10303-21;
HEADER;
FILE_DESCRIPTION(('beam geometry test'),'2;1');
FILE_NAME('beam.ifc','2026-09-01T00:00:00',(),(),'', '', '');
FILE_SCHEMA(('IFC4'));
ENDSEC;
DATA;
#1=IFCPROJECT('PROJECT-GID',$,'Project',$,$,$,$,$,#10);
#10=IFCUNITASSIGNMENT((#11,#12));
#11=IFCSIUNIT(*,.LENGTHUNIT.,$,.METRE.);
#12=IFCSIUNIT(*,.PLANEANGLEUNIT.,$,.RADIAN.);
#100=IFCBEAM('RECT-BEAM-GID',$,'Rect Beam',$,$,$,#101,$);
#101=IFCPRODUCTDEFINITIONSHAPE($,$,(#102,#103));
#102=IFCSHAPEREPRESENTATION($,'Axis','Curve2D',(#104));
#103=IFCSHAPEREPRESENTATION($,'Body','SweptSolid',(#107));
#104=IFCPOLYLINE((#105,#106));
#105=IFCCARTESIANPOINT((0.,0.));
#106=IFCCARTESIANPOINT((3.,4.));
#107=IFCEXTRUDEDAREASOLID(#108,$,#109,5.);
#108=IFCARBITRARYCLOSEDPROFILEDEF(.AREA.,$,#110);
#109=IFCDIRECTION((0.,0.,1.));
#110=IFCPOLYLINE((#111,#112,#113,#114,#111));
#111=IFCCARTESIANPOINT((-0.1,-0.2));
#112=IFCCARTESIANPOINT((0.1,-0.2));
#113=IFCCARTESIANPOINT((0.1,0.2));
#114=IFCCARTESIANPOINT((-0.1,0.2));
ENDSEC;
END-ISO-10303-21;
"""


class BeamGeometryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.source = RECTANGULAR_BEAM.encode("utf-8")
        self.digest = hashlib.sha256(self.source).hexdigest()
        self.file = parse_ifc(RECTANGULAR_BEAM)
        self.beam = self.file.by_type("IFCBEAM")[0]

    def test_axis_and_rectangle_section_properties_match_closed_form(self) -> None:
        result = derive_beam_geometry(
            self.file,
            self.beam,
            source_ifc_sha256=self.digest,
        )

        self.assertEqual(result.status, BeamGeometryStatus.COMPLETE)
        self.assertAlmostEqual(result.axis_length.value, 5.0)
        self.assertAlmostEqual(result.cross_section_area.value, 0.08)
        self.assertAlmostEqual(result.section_modulus_major.value, 0.2 * 0.4**2 / 6.0)
        self.assertAlmostEqual(result.section_modulus_minor.value, 0.4 * 0.2**2 / 6.0)
        document = result.to_dict()
        self.assertEqual(document["method"], BEAM_GEOMETRY_METHOD)
        self.assertEqual(document["subject"]["global_id"], "RECT-BEAM-GID")
        self.assertEqual(document["provenance"]["source_ifc_sha256"], self.digest)
        self.assertGreater(len(document["provenance"]["source_refs"]), 4)
        self.assertIn(
            "no as-built",
            document["provenance"]["uncertainty_scope"],
        )

    def test_unsupported_body_is_explicit_length_only_not_bounding_box(self) -> None:
        text = RECTANGULAR_BEAM.replace("'SweptSolid'", "'SurfaceModel'")
        source = text.encode("utf-8")
        file = parse_ifc(text)
        result = derive_beam_geometry(
            file,
            file.by_type("IFCBEAM")[0],
            source_ifc_sha256=hashlib.sha256(source).hexdigest(),
        )

        self.assertEqual(result.status, BeamGeometryStatus.LENGTH_ONLY)
        self.assertAlmostEqual(result.axis_length.value, 5.0)
        self.assertIsNone(result.section_modulus_major)
        self.assertIn("SurfaceModel", result.issues[0])

    def test_all_beam_derivation_is_ordered_and_digest_deterministic(self) -> None:
        first = derive_all_beam_geometry(
            self.file,
            source_ifc_sha256=self.digest,
        )
        second = derive_all_beam_geometry(
            self.file,
            source_ifc_sha256=self.digest,
        )

        self.assertEqual(len(first), 1)
        self.assertEqual(first[0].digest(), second[0].digest())

    def test_malformed_beam_isolated_without_hiding_valid_results(self) -> None:
        text = RECTANGULAR_BEAM.replace(
            "ENDSEC;\nEND-ISO-10303-21;",
            (
                "#200=IFCBEAM('BLOCKED-BEAM-GID',$,'Blocked Beam',$,$,$,$,$);\n"
                "ENDSEC;\nEND-ISO-10303-21;"
            ),
        )
        source = text.encode("utf-8")
        results = derive_all_beam_geometry(
            parse_ifc(text),
            source_ifc_sha256=hashlib.sha256(source).hexdigest(),
        )

        self.assertEqual(
            [result.status for result in results],
            [BeamGeometryStatus.COMPLETE, BeamGeometryStatus.BLOCKED],
        )
        self.assertEqual(results[0].beam_global_id, "RECT-BEAM-GID")
        self.assertEqual(results[1].beam_global_id, "BLOCKED-BEAM-GID")
        self.assertIn("Representation", results[1].issues[0])


def _axis_only_beam(representation_type: str, points: list[tuple[float, ...]]) -> str:
    """An IFC4 beam whose only representation is an Axis polyline."""
    coords = "".join(
        f"#{110 + i}=IFCCARTESIANPOINT(({','.join(f'{v:.1f}' for v in point)}));\n"
        for i, point in enumerate(points)
    )
    plist = ",".join(f"#{110 + i}" for i in range(len(points)))
    return f"""ISO-10303-21;
HEADER;
FILE_DESCRIPTION(('axis scope test'),'2;1');
FILE_NAME('axis.ifc','2026-09-01T00:00:00',(),(),'', '', '');
FILE_SCHEMA(('IFC4'));
ENDSEC;
DATA;
#1=IFCPROJECT('P00000000000000000001',$,'P',$,$,$,$,$,$);
#2=IFCSIUNIT(*,.LENGTHUNIT.,$,.METRE.);
#100=IFCBEAM('BEAM0000000000000000001',$,'B1',$,$,#120,#101,$,$);
#101=IFCPRODUCTDEFINITIONSHAPE($,$,(#102));
#102=IFCSHAPEREPRESENTATION($,'Axis','{representation_type}',(#104));
#104=IFCPOLYLINE(({plist}));
{coords}#120=IFCLOCALPLACEMENT($,#121);
#121=IFCAXIS2PLACEMENT3D(#122,$,$);
#122=IFCCARTESIANPOINT((0.,0.,0.));
ENDSEC;
END-ISO-10303-21;
"""


class AxisRepresentationScopeTests(unittest.TestCase):
    """A 3D Axis polyline was silently projected onto XY.

    ``_axis_length`` selected its representation on
    ``RepresentationIdentifier == "Axis"`` alone and never read
    ``RepresentationType``. ``_polyline_points`` then asks ``_point`` for two
    dimensions, and ``_point`` slices ``coordinates[:dimensions]`` without
    complaint, so a ``Curve3D`` polyline lost its z and the span came back as
    its XY projection. Measured on this fixture, before the check existed:

        Axis polyline            true span   reported   short by   status
        (0,0,0) -> (6,0,8)          10.0        6.0       4.0 m    LENGTH_ONLY
        (0,0,0) -> (3,4,12)         13.0        5.0       8.0 m    LENGTH_ONLY

    -- 62% short on the cranked member, with ``issues=()``. Span is the lever
    arm in the bending check, so a short span understates the required
    moment and the member reads stronger than it is.

    ``_body_profile`` has always read ``RepresentationType`` and refused a
    non-``SweptSolid``. The Axis path simply omitted the same check; the
    module docstring promises unsupported representations are "never
    silently replaced".
    """

    #: Refused rather than extended to 3D on purpose: Curve2D is what
    #: docs/beam-assurance-reference-chain.md declares this provider reads,
    #: and a sloping or cranked member is not a longer straight one. AISC
    #: 360-22 F2 is scoped to doubly-symmetric compact I-shapes bent about
    #: the major axis, so admitting those geometries is a validation
    #: question rather than a length calculation.
    OUT_OF_SCOPE = (
        ([(0.0, 0.0, 0.0), (6.0, 0.0, 8.0)], 10.0, "sloping, 6-8-10"),
        ([(0.0, 0.0, 0.0), (3.0, 4.0, 12.0)], 13.0, "cranked"),
        ([(0.0, 0.0, 0.0), (0.0, 0.0, 5.0)], 5.0, "vertical, XY-degenerate"),
    )

    def _geometry(self, representation_type, points):
        ifc = parse_ifc(_axis_only_beam(representation_type, points))
        beam = ifc.by_type("IFCBEAM")[0]
        return derive_beam_geometry(ifc, beam, source_ifc_sha256="0" * 64)

    def test_a_curve2d_axis_still_reads_its_span(self) -> None:
        geometry = self._geometry("Curve2D", [(0.0, 0.0), (6.0, 0.0)])
        self.assertEqual(geometry.status, BeamGeometryStatus.LENGTH_ONLY)
        self.assertIsNotNone(geometry.axis_length)
        self.assertAlmostEqual(geometry.axis_length.value, 6.0, places=12)

    def test_a_three_dimensional_axis_is_blocked_not_projected(self) -> None:
        for points, true_span, label in self.OUT_OF_SCOPE:
            with self.subTest(case=label):
                geometry = self._geometry("Curve3D", points)
                self.assertEqual(geometry.status, BeamGeometryStatus.BLOCKED)
                self.assertIsNone(geometry.axis_length)
                self.assertTrue(geometry.issues, "a block must say why")

    def test_the_refusal_names_the_representation_and_the_reason(self) -> None:
        geometry = self._geometry("Curve3D", [(0.0, 0.0, 0.0), (6.0, 0.0, 8.0)])
        joined = " ".join(str(issue) for issue in geometry.issues)
        self.assertIn("Curve3D", joined)
        self.assertIn("shorter", joined)

    def test_an_undeclared_representation_type_is_refused_too(self) -> None:
        """``$`` is not a promise that the curve is planar."""
        ifc = parse_ifc(
            _axis_only_beam("Curve2D", [(0.0, 0.0), (6.0, 0.0)]).replace(
                "'Axis','Curve2D'", "'Axis',$"
            )
        )
        beam = ifc.by_type("IFCBEAM")[0]
        geometry = derive_beam_geometry(ifc, beam, source_ifc_sha256="0" * 64)
        self.assertEqual(geometry.status, BeamGeometryStatus.BLOCKED)

    def test_the_shipped_demo_beam_is_unaffected(self) -> None:
        """gat/demo/beam_model.ifc declares Curve2D; the whole reference
        chain rests on it still reading."""
        import os

        import gat.demo

        path = os.path.join(os.path.dirname(gat.demo.__file__), "beam_model.ifc")
        with open(path, "rb") as handle:
            raw = handle.read()
        ifc = parse_ifc(raw.decode("utf-8"))
        beam = ifc.by_type("IFCBEAM")[0]
        geometry = derive_beam_geometry(
            ifc, beam, source_ifc_sha256=hashlib.sha256(raw).hexdigest()
        )
        self.assertEqual(geometry.status, BeamGeometryStatus.COMPLETE)
        self.assertIsNotNone(geometry.axis_length)



if __name__ == "__main__":
    unittest.main()
