"""Attribute-position maps for the supported IFC entity subset.

The parser is schema-agnostic; this table is the only place that knows
which argument position means what, for the ~25 entity types the v0
adapter lowers.  Anything not listed here survives parsing as an opaque
instance and round-trips verbatim.
"""

from __future__ import annotations

#: type name -> {attribute name: argument position}
SUPPORTED_ENTITIES: dict[str, dict[str, int]] = {
    "IFCPROJECT": {"GlobalId": 0, "Name": 2, "UnitsInContext": 8},
    "IFCBUILDING": {"GlobalId": 0, "Name": 2, "ObjectPlacement": 5},
    "IFCBUILDINGSTOREY": {"GlobalId": 0, "Name": 2, "ObjectPlacement": 5},
    "IFCWALL": {"GlobalId": 0, "Name": 2, "ObjectPlacement": 5},
    "IFCWALLSTANDARDCASE": {"GlobalId": 0, "Name": 2, "ObjectPlacement": 5},
    "IFCSPACE": {"GlobalId": 0, "Name": 2, "ObjectPlacement": 5},
    "IFCOPENINGELEMENT": {"GlobalId": 0, "Name": 2, "ObjectPlacement": 5},
    "IFCDOOR": {"GlobalId": 0, "Name": 2, "ObjectPlacement": 5},
    "IFCBEAM": {"GlobalId": 0, "Name": 2, "ObjectPlacement": 5},
    "IFCBEAMSTANDARDCASE": {"GlobalId": 0, "Name": 2, "ObjectPlacement": 5},
    "IFCPRODUCTDEFINITIONSHAPE": {"Representations": 2},
    "IFCSHAPEREPRESENTATION": {
        "RepresentationIdentifier": 1,
        "RepresentationType": 2,
        "Items": 3,
    },
    "IFCPOLYLINE": {"Points": 0},
    "IFCARBITRARYCLOSEDPROFILEDEF": {"OuterCurve": 2},
    "IFCCOMPOSITECURVE": {"Segments": 0},
    "IFCCOMPOSITECURVESEGMENT": {"SameSense": 1, "ParentCurve": 2},
    "IFCTRIMMEDCURVE": {
        "BasisCurve": 0,
        "Trim1": 1,
        "Trim2": 2,
        "SenseAgreement": 3,
        "MasterRepresentation": 4,
    },
    "IFCCIRCLE": {"Position": 0, "Radius": 1},
    "IFCAXIS2PLACEMENT2D": {"Location": 0, "RefDirection": 1},
    "IFCEXTRUDEDAREASOLID": {
        "SweptArea": 0,
        "Position": 1,
        "ExtrudedDirection": 2,
        "Depth": 3,
    },
    "IFCCONVERSIONBASEDUNIT": {
        "UnitType": 1,
        "Name": 2,
        "ConversionFactor": 3,
    },
    "IFCMEASUREWITHUNIT": {"ValueComponent": 0, "UnitComponent": 1},
    "IFCRELAGGREGATES": {"GlobalId": 0, "RelatingObject": 4, "RelatedObjects": 5},
    "IFCRELCONTAINEDINSPATIALSTRUCTURE": {
        "GlobalId": 0,
        "RelatedElements": 4,
        "RelatingStructure": 5,
    },
    "IFCRELVOIDSELEMENT": {
        "GlobalId": 0,
        "RelatingBuildingElement": 4,
        "RelatedOpeningElement": 5,
    },
    "IFCRELFILLSELEMENT": {
        "GlobalId": 0,
        "RelatingOpeningElement": 4,
        "RelatedBuildingElement": 5,
    },
    # IFC4 puts two subtypes under IfcRelSpaceBoundary -- 1stLevel adds
    # ParentBoundary at position 9, 2ndLevel adds CorrespondingBoundary at
    # 10 -- and leaves positions 0..8 exactly as they are here. Real IFC4
    # exporters emit the subtypes, so the same layout is registered for all
    # three. See SUBTYPES_OF below for why this is not optional.
    "IFCRELSPACEBOUNDARY": {
        "GlobalId": 0,
        "RelatingSpace": 4,
        "RelatedBuildingElement": 5,
        "InternalOrExternalBoundary": 8,
    },
    "IFCRELSPACEBOUNDARY1STLEVEL": {
        "GlobalId": 0,
        "RelatingSpace": 4,
        "RelatedBuildingElement": 5,
        "InternalOrExternalBoundary": 8,
    },
    "IFCRELSPACEBOUNDARY2NDLEVEL": {
        "GlobalId": 0,
        "RelatingSpace": 4,
        "RelatedBuildingElement": 5,
        "InternalOrExternalBoundary": 8,
    },
    "IFCRELDEFINESBYPROPERTIES": {
        "GlobalId": 0,
        "RelatedObjects": 4,
        "RelatingPropertyDefinition": 5,
    },
    "IFCPROPERTYSET": {"GlobalId": 0, "Name": 2, "HasProperties": 4},
    "IFCPROPERTYSINGLEVALUE": {"Name": 0, "NominalValue": 2},
    "IFCELEMENTQUANTITY": {"GlobalId": 0, "Name": 2, "Quantities": 5},
    "IFCQUANTITYLENGTH": {"Name": 0, "Value": 3},
    "IFCQUANTITYAREA": {"Name": 0, "Value": 3},
    "IFCQUANTITYVOLUME": {"Name": 0, "Value": 3},
    "IFCLOCALPLACEMENT": {"PlacementRelTo": 0, "RelativePlacement": 1},
    "IFCAXIS2PLACEMENT3D": {"Location": 0, "Axis": 1, "RefDirection": 2},
    "IFCCARTESIANPOINT": {"Coordinates": 0},
    "IFCDIRECTION": {"DirectionRatios": 0},
    "IFCSIUNIT": {"UnitType": 1, "Prefix": 2, "Name": 3},
    "IFCUNITASSIGNMENT": {"Units": 0},
}

#: The building-element classes the adapter lowers to IR entities,
#: normalized to their canonical IFC class spelling.
PRODUCT_CLASSES: dict[str, str] = {
    "IFCBUILDINGSTOREY": "IfcBuildingStorey",
    "IFCWALL": "IfcWall",
    "IFCWALLSTANDARDCASE": "IfcWall",  # normalized: a wall is a wall
    "IFCSPACE": "IfcSpace",
    "IFCOPENINGELEMENT": "IfcOpeningElement",
    "IFCDOOR": "IfcDoor",
}

# Engineering elements become authoritative only when an explicit CSE
# contract property set is present. Keeping these outside PRODUCT_CLASSES
# prevents ordinary real-world IFC beams from becoming mandatory inputs to
# the v0 architectural lowering path.
ANNOTATED_PRODUCT_CLASSES: dict[str, tuple[str, str]] = {
    "IFCBEAM": ("IfcBeam", "GAT_Structural"),
    "IFCBEAMSTANDARDCASE": ("IfcBeam", "GAT_Structural"),
}


#: IFC types this adapter consumes, mapped to the subtypes it treats as the
#: same thing. ``IfcFile.by_type`` is an exact uppercase string compare with
#: no schema knowledge, so a subtype that is not listed here is not found --
#: and, for a relationship, is not found *silently*.
#:
#: Measured on ``gat/demo/model.ifc``: renaming its eight
#: ``IFCRELSPACEBOUNDARY`` instances to either legal IFC4 subtype made
#: ``GatSession.load_ifc`` succeed with no error while dropping all eight
#: BOUNDS edges and all four ``external`` flags -- Wall-East, Wall-North,
#: Wall-South and Wall-West each became an interior wall. That flag is read
#: at ``gat/geometry/stateio.py:152-155`` and feeds the geometry feature
#: vector, so a real IFC4 exporter using 2nd-level boundaries would have
#: turned every exterior wall in the building into an interior one and
#: refused nothing.
#:
#: ``IFCWALLSTANDARDCASE`` was already normalized in ``PRODUCT_CLASSES``
#: ("a wall is a wall"), so the adapter knew this hazard for *elements* and
#: had simply never carried it to *relationships*.
SUBTYPES_OF: dict[str, tuple[str, ...]] = {
    "IFCRELSPACEBOUNDARY": (
        "IFCRELSPACEBOUNDARY1STLEVEL",
        "IFCRELSPACEBOUNDARY2NDLEVEL",
    ),
    "IFCWALL": ("IFCWALLSTANDARDCASE",),
    "IFCBEAM": ("IFCBEAMSTANDARDCASE",),
}


def type_family(supertype: str) -> tuple[str, ...]:
    """``supertype`` and every subtype this adapter treats as equivalent."""
    upper = supertype.upper()
    return (upper,) + SUBTYPES_OF.get(upper, ())


def unknown_subtypes(present: "frozenset[str] | set[str]") -> tuple[str, ...]:
    """Type names that look like an unhandled subtype of a consumed type.

    The fail-closed half of :data:`SUBTYPES_OF`. Listing the subtypes that
    exist today fixes today's files; it does nothing for a schema revision
    that adds another one, and the failure mode is silence. So a file
    carrying a type whose name extends one this adapter consumes, and which
    is not in the family, is refused by name rather than read as if the
    instances were absent.
    """
    known = {name for key in SUBTYPES_OF for name in type_family(key)}
    out = []
    for name in sorted(present):
        if name in known:
            continue
        for supertype in SUBTYPES_OF:
            if name.startswith(supertype) and name != supertype:
                out.append(name)
                break
    return tuple(out)
