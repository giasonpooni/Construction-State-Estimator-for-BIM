"""Optional IfcOpenShell adapter — second loader, not the authority.

The hand-written ``gat.adapters.ifc`` path remains fail-closed and
authoritative. This module inventories identities and QTO names so the
two loaders can be differential-tested. It does not tessellate, does not
invent section properties, and never upgrades geometry authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from gat.adapters.ifc.parser import parse_ifc_file
from gat.adapters.ifc.reader import attr, global_id, name_of, properties_of, quantities_of
from gat.adapters.ifc.schema import PRODUCT_CLASSES

COMPARE_CLASSES = (
    "IfcBuildingStorey",
    "IfcWall",
    "IfcSpace",
    "IfcOpeningElement",
    "IfcDoor",
    "IfcBeam",
)

_IOS_TYPE = {
    "IfcBuildingStorey": "IfcBuildingStorey",
    "IfcWall": "IfcWall",
    "IfcSpace": "IfcSpace",
    "IfcOpeningElement": "IfcOpeningElement",
    "IfcDoor": "IfcDoor",
    "IfcBeam": "IfcBeam",
}


class IfcOpenShellAdapterError(RuntimeError):
    """Raised when the optional adapter cannot be used honestly."""


def ifcopenshell_available() -> bool:
    try:
        import ifcopenshell  # noqa: F401
    except ImportError:
        return False
    return True


@dataclass(frozen=True)
class ProductIdentity:
    ifc_class: str
    global_id: str
    name: str
    quantity_names: tuple[str, ...]
    representation_types: tuple[str, ...]

    @property
    def key(self) -> tuple[str, str]:
        return (self.ifc_class, self.global_id)


@dataclass(frozen=True)
class IfcOpenShellInventory:
    path: str
    schema: str
    product_count: int
    beam_global_ids: tuple[str, ...]
    space_global_ids: tuple[str, ...]
    opening_global_ids: tuple[str, ...]
    products: tuple[ProductIdentity, ...]
    omitted: tuple[str, ...]
    geometry_authority: str = "INSUFFICIENT"


@dataclass(frozen=True)
class IdentityDiff:
    only_cse: tuple[tuple[str, str], ...]
    only_ifcopenshell: tuple[tuple[str, str], ...]
    quantity_mismatches: tuple[tuple[str, str, tuple[str, ...], tuple[str, ...]], ...]

    @property
    def ok(self) -> bool:
        return not (self.only_cse or self.only_ifcopenshell or self.quantity_mismatches)


def _quantity_names_cse(file, inst) -> tuple[str, ...]:
    defs = properties_of(file, {inst.step_id}).get(inst.step_id, [])
    names = tuple(sorted(quantities_of(file, defs)))
    return names


def inventory_identities_cse(path: str | Path) -> IfcOpenShellInventory:
    """Identity inventory from the authoritative SPF path. No mesh."""
    path = str(path)
    file = parse_ifc_file(path)
    products: list[ProductIdentity] = []
    omitted: list[str] = []
    for type_name, canonical in PRODUCT_CLASSES.items():
        for inst in file.by_type(type_name):
            try:
                gid = global_id(inst)
            except Exception as exc:
                omitted.append(f"{canonical} #{inst.step_id}: {exc}")
                continue
            products.append(
                ProductIdentity(
                    ifc_class=canonical,
                    global_id=gid,
                    name=name_of(inst),
                    quantity_names=_quantity_names_cse(file, inst),
                    representation_types=(),
                )
            )
    for inst in file.by_type("IFCBEAM"):
        try:
            gid = global_id(inst)
        except Exception as exc:
            omitted.append(f"IfcBeam #{inst.step_id}: {exc}")
            continue
        products.append(
            ProductIdentity(
                ifc_class="IfcBeam",
                global_id=gid,
                name=name_of(inst),
                quantity_names=_quantity_names_cse(file, inst),
                representation_types=(),
            )
        )
    products.sort(key=lambda row: row.key)
    return IfcOpenShellInventory(
        path=path,
        schema=file.schema,
        product_count=len(products),
        beam_global_ids=tuple(row.global_id for row in products if row.ifc_class == "IfcBeam"),
        space_global_ids=tuple(row.global_id for row in products if row.ifc_class == "IfcSpace"),
        opening_global_ids=tuple(
            row.global_id for row in products if row.ifc_class == "IfcOpeningElement"
        ),
        products=tuple(products),
        omitted=tuple(omitted),
        geometry_authority="INSUFFICIENT",
    )


def _representation_types(element) -> tuple[str, ...]:
    shape = getattr(element, "Representation", None)
    if shape is None:
        return ()
    types: list[str] = []
    for representation in getattr(shape, "Representations", ()) or ():
        label = getattr(representation, "RepresentationType", None)
        if isinstance(label, str) and label:
            types.append(label)
    return tuple(types)


def _quantity_names_ios(element) -> tuple[str, ...]:
    try:
        from ifcopenshell.util.element import get_psets
    except ImportError:
        return ()
    qtos = get_psets(element, qtos_only=True) or {}
    names: set[str] = set()
    for payload in qtos.values():
        if not isinstance(payload, dict):
            continue
        for key in payload:
            if key == "id":
                continue
            names.add(str(key))
    return tuple(sorted(names))


def inventory_with_ifcopenshell(path: str | Path) -> IfcOpenShellInventory:
    """Open a file for identity inventory only. Never invent section properties."""
    if not ifcopenshell_available():
        raise IfcOpenShellAdapterError(
            "ifcopenshell is not installed; pip install '.[ifcopenshell]'"
        )
    import ifcopenshell

    path = str(path)
    model = ifcopenshell.open(path)
    products: list[ProductIdentity] = []
    omitted: list[str] = []
    seen: set[int] = set()
    for canonical in COMPARE_CLASSES:
        ios_type = _IOS_TYPE[canonical]
        for element in model.by_type(ios_type):
            if element.id() in seen:
                continue
            seen.add(element.id())
            gid = getattr(element, "GlobalId", None)
            if not isinstance(gid, str) or not gid:
                omitted.append(f"{canonical} #{element.id()}: missing GlobalId")
                continue
            is_subtype_wall = canonical == "IfcWall" and element.is_a("IfcWall")
            ifc_class = "IfcWall" if is_subtype_wall else element.is_a()
            if canonical != "IfcWall":
                ifc_class = canonical
            products.append(
                ProductIdentity(
                    ifc_class=canonical if canonical != "IfcWall" else "IfcWall",
                    global_id=gid,
                    name=str(getattr(element, "Name", None) or ""),
                    quantity_names=_quantity_names_ios(element),
                    representation_types=_representation_types(element),
                )
            )
    products.sort(key=lambda row: row.key)
    all_products = model.by_type("IfcProduct")
    return IfcOpenShellInventory(
        path=path,
        schema=str(model.schema),
        product_count=len(all_products),
        beam_global_ids=tuple(row.global_id for row in products if row.ifc_class == "IfcBeam"),
        space_global_ids=tuple(row.global_id for row in products if row.ifc_class == "IfcSpace"),
        opening_global_ids=tuple(
            row.global_id for row in products if row.ifc_class == "IfcOpeningElement"
        ),
        products=tuple(products),
        omitted=tuple(omitted),
        geometry_authority="INSUFFICIENT",
    )


def diff_identity_inventories(
    cse: IfcOpenShellInventory, ios: IfcOpenShellInventory
) -> IdentityDiff:
    cse_map = {row.key: row for row in cse.products}
    ios_map = {row.key: row for row in ios.products}
    only_cse = tuple(sorted(set(cse_map) - set(ios_map)))
    only_ios = tuple(sorted(set(ios_map) - set(cse_map)))
    mismatches: list[tuple[str, str, tuple[str, ...], tuple[str, ...]]] = []
    for key in sorted(set(cse_map) & set(ios_map)):
        left = cse_map[key].quantity_names
        right = ios_map[key].quantity_names
        if left != right:
            mismatches.append((key[0], key[1], left, right))
    return IdentityDiff(
        only_cse=only_cse,
        only_ifcopenshell=only_ios,
        quantity_mismatches=tuple(mismatches),
    )
