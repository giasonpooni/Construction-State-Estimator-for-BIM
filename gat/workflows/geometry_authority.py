"""Geometry authority codes for CSE checks.

These codes are part of the public decision contract. Clearance scored from
Gaussianized boxes with openings unsubtracted is GAUSSIAN_PROXY and cannot
close an as-built case by itself. Scan receipts upgrade a check to SCAN_GMM.

A capacity check has a third kind of support, distinct from both measured
geometry and dimensional quantities: a section property *asserted* in an IFC
property set under an explicit contract. It is neither measured nor derived
from the model's own geometry, so on its own it is DECLARED_PROPERTY and
cannot close a case. When the model does carry a swept solid and that solid
brackets the declaration (see
:mod:`gat.engineering.section_corroboration`), the check becomes
DECLARED_CORROBORATED and may close a capacity case -- the same shape of
upgrade a scan receipt performs for clearance.
"""

from __future__ import annotations

from enum import StrEnum


class GeometryAuthority(StrEnum):
    SWEPT_SOLID = "SWEPT_SOLID"
    LENGTH_ONLY = "LENGTH_ONLY"
    SCAN_GMM = "SCAN_GMM"
    QUANTITY_ONLY = "QUANTITY_ONLY"
    GAUSSIAN_PROXY = "GAUSSIAN_PROXY"
    #: A section property asserted in an IFC property set. Not measured, and
    #: not cross-checked against the model's geometry. Closes nothing.
    DECLARED_PROPERTY = "DECLARED_PROPERTY"
    #: The same declaration, bracketed by the model's own swept solid.
    DECLARED_CORROBORATED = "DECLARED_CORROBORATED"
    INSUFFICIENT = "INSUFFICIENT"


_CLEARANCE_OK = frozenset({GeometryAuthority.SWEPT_SOLID, GeometryAuthority.SCAN_GMM})
_QUANTITY_OK = frozenset(
    {
        GeometryAuthority.QUANTITY_ONLY,
        GeometryAuthority.SWEPT_SOLID,
        GeometryAuthority.SCAN_GMM,
        GeometryAuthority.DECLARED_CORROBORATED,
    }
)


def authority_from_beam_status(status: str) -> GeometryAuthority:
    """Authority from the beam's *geometry* alone.

    This says nothing about a declared section property; for a capacity check
    whose section modulus comes from GAT_Structural, use
    :func:`gat.engineering.section_corroboration.corroborate_beam_section`,
    which takes this status into account and reports whether the geometry
    corroborates the declaration.
    """
    if status == "COMPLETE":
        return GeometryAuthority.SWEPT_SOLID
    if status == "LENGTH_ONLY":
        return GeometryAuthority.LENGTH_ONLY
    return GeometryAuthority.INSUFFICIENT


def geometry_sufficient(
    kind: str,
    authority: GeometryAuthority,
    *,
    scan_covered: bool = False,
) -> bool:
    if scan_covered:
        authority = GeometryAuthority.SCAN_GMM
    if kind == "CLEARANCE":
        return authority in _CLEARANCE_OK
    return authority in _QUANTITY_OK
