"""The IfcOpenShell adapter is optional, fail-closed, and inventory-only."""

from __future__ import annotations

import os
import unittest

from gat.adapters.ifcopenshell_adapter import (
    IfcOpenShellAdapterError,
    diff_identity_inventories,
    ifcopenshell_available,
    inventory_identities_cse,
    inventory_with_ifcopenshell,
)

DEMO = os.path.join(os.path.dirname(__file__), "..", "gat", "demo", "model.ifc")
BEAM = os.path.join(os.path.dirname(__file__), "..", "gat", "demo", "beam_model.ifc")


class IfcOpenShellAdapterTests(unittest.TestCase):
    def test_missing_runtime_fails_closed(self) -> None:
        if ifcopenshell_available():
            self.skipTest("ifcopenshell is installed in this environment")
        with self.assertRaisesRegex(IfcOpenShellAdapterError, "not installed"):
            inventory_with_ifcopenshell(DEMO)

    def test_cse_inventory_sees_spaces_and_openings(self) -> None:
        inventory = inventory_identities_cse(DEMO)
        self.assertEqual(inventory.geometry_authority, "INSUFFICIENT")
        self.assertEqual(len(inventory.space_global_ids), 2)
        self.assertEqual(len(inventory.opening_global_ids), 1)
        classes = {row.ifc_class for row in inventory.products}
        self.assertTrue({"IfcSpace", "IfcOpeningElement", "IfcWall", "IfcDoor"} <= classes)
        office = [row for row in inventory.products if row.name == "Office-A"]
        self.assertEqual(len(office), 1)
        self.assertEqual(office[0].global_id, "GATSPC0000000000000300")
        self.assertEqual(office[0].quantity_names, ("Length", "Width"))

    def test_installed_runtime_does_not_claim_solid_authority(self) -> None:
        if not ifcopenshell_available():
            self.skipTest("ifcopenshell extra is not installed")
        inventory = inventory_with_ifcopenshell(BEAM)
        self.assertGreaterEqual(inventory.product_count, 1)
        self.assertEqual(inventory.geometry_authority, "INSUFFICIENT")

    def test_representation_labels_are_not_geometry_authority(self) -> None:
        if not ifcopenshell_available():
            self.skipTest("ifcopenshell extra is not installed")
        for path in (DEMO, BEAM):
            ios = inventory_with_ifcopenshell(path)
            self.assertEqual(ios.geometry_authority, "INSUFFICIENT")
            for row in ios.products:
                self.assertIsInstance(row.representation_types, tuple)
                for label in row.representation_types:
                    self.assertIsInstance(label, str)
                    self.assertNotEqual(label.upper(), "SWEPT_SOLID")
            # Shipped demos have quantities and placements, not bodies.
            self.assertFalse(
                any(row.representation_types for row in ios.products),
                msg=f"{path} unexpectedly grew a RepresentationType",
            )

    def test_demo_identities_match_when_ifcopenshell_is_present(self) -> None:
        if not ifcopenshell_available():
            self.skipTest("ifcopenshell extra is not installed")
        cse = inventory_identities_cse(DEMO)
        ios = inventory_with_ifcopenshell(DEMO)
        self.assertEqual(ios.geometry_authority, "INSUFFICIENT")
        self.assertEqual(set(cse.space_global_ids), set(ios.space_global_ids))
        self.assertEqual(set(cse.opening_global_ids), set(ios.opening_global_ids))
        diff = diff_identity_inventories(cse, ios)
        self.assertTrue(
            diff.ok,
            msg=f"only_cse={diff.only_cse} only_ios={diff.only_ifcopenshell} "
            f"qty={diff.quantity_mismatches}",
        )

    def test_beam_model_identities_match_when_ifcopenshell_is_present(self) -> None:
        if not ifcopenshell_available():
            self.skipTest("ifcopenshell extra is not installed")
        cse = inventory_identities_cse(BEAM)
        ios = inventory_with_ifcopenshell(BEAM)
        self.assertEqual(ios.geometry_authority, "INSUFFICIENT")
        diff = diff_identity_inventories(cse, ios)
        self.assertTrue(
            diff.ok,
            msg=f"only_cse={diff.only_cse} only_ios={diff.only_ifcopenshell} "
            f"qty={diff.quantity_mismatches}",
        )
        self.assertFalse(any(row.representation_types for row in cse.products))


if __name__ == "__main__":
    unittest.main()
