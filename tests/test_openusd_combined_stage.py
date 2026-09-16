"""Combined USD assembly: display layer cannot become the estimator."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from gat.adapters.openusd import openusd_available, read_openusd, write_openusd
from gat.adapters.openusd_compose import (
    ASSEMBLY_KIND,
    write_combined_stage,
    write_display_layer,
)
from gat.errors import OpenUsdError
from gat.session import GatSession
from gat.state_snapshot import computational_equivalence

MODEL = os.path.join(os.path.dirname(__file__), "..", "gat", "demo", "model.ifc")
BIND = os.path.join(os.path.dirname(__file__), "..", "validation", "cse-point-bind-v1.json")


class CombinedUsdStageWithoutRuntimeTests(unittest.TestCase):
    def test_missing_usd_core_fails_closed(self) -> None:
        if openusd_available():
            self.skipTest("usd-core is installed in this environment")
        with self.assertRaisesRegex(OpenUsdError, "usd-core is not installed"):
            write_display_layer("sitelook.usda")
        with self.assertRaisesRegex(OpenUsdError, "usd-core is not installed"):
            write_combined_stage(
                carrier_path="missing.usdc",
                assembly_path="world.usda",
            )


@unittest.skipUnless(openusd_available(), "optional usd-core runtime is not installed")
class CombinedUsdStageTests(unittest.TestCase):
    def setUp(self) -> None:
        from pxr import Usd

        self.Usd = Usd
        self.session = GatSession.load_ifc(MODEL)

    def test_assembly_references_carrier_and_does_not_author_binds(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            carrier = Path(raw) / "cse.usdc"
            digest = write_openusd(self.session.world, carrier, ledger=self.session.ledger)
            combined = write_combined_stage(
                carrier_path=carrier,
                assembly_path=Path(raw) / "world.usda",
                display_path=Path(raw) / "sitelook.usda",
                bind_path=BIND,
            )
            stage = self.Usd.Stage.Open(str(combined.assembly_path))
            world = stage.GetDefaultPrim()
            self.assertEqual(world.GetName(), "World")
            self.assertEqual(world.GetAttribute("gat:assemblyKind").Get(), ASSEMBLY_KIND)
            self.assertFalse(world.GetAttribute("gat:bindsInUsd").Get())
            self.assertEqual(world.GetAttribute("gat:restartPath").Get(), "cse.usdc")
            self.assertTrue(stage.GetPrimAtPath("/World/GAT"))
            self.assertTrue(stage.GetPrimAtPath("/World/SiteLook"))
            self.assertFalse(stage.GetPrimAtPath("/World/Binds"))
            restored = read_openusd(combined.carrier_path)
            self.assertEqual(restored.snapshot_digest, digest)
            self.assertTrue(
                computational_equivalence(self.session.world, restored.world).passed
            )
            with self.assertRaises(OpenUsdError):
                read_openusd(combined.assembly_path)

    def test_sitelook_edit_does_not_change_carrier_restart(self) -> None:
        from pxr import Sdf

        with tempfile.TemporaryDirectory() as raw:
            carrier = Path(raw) / "cse.usdc"
            write_openusd(self.session.world, carrier, ledger=self.session.ledger)
            display = write_display_layer(Path(raw) / "sitelook.usda")
            combined = write_combined_stage(
                carrier_path=carrier,
                assembly_path=Path(raw) / "world.usda",
                display_path=display,
            )
            before = read_openusd(carrier).world.digest()
            look = self.Usd.Stage.Open(str(combined.display_path))
            root = look.GetDefaultPrim()
            root.CreateAttribute("review:note", Sdf.ValueTypeNames.String, custom=True).Set(
                "paint only"
            )
            look.GetRootLayer().Save()
            after = read_openusd(carrier).world.digest()
            self.assertEqual(before, after)

    def test_carrier_belief_edit_without_new_digest_still_fails(self) -> None:
        from gat.errors import SnapshotError

        with tempfile.TemporaryDirectory() as raw:
            carrier = Path(raw) / "cse.usda"
            write_openusd(self.session.world, carrier, ledger=self.session.ledger)
            write_combined_stage(
                carrier_path=carrier,
                assembly_path=Path(raw) / "world.usda",
            )
            stage = self.Usd.Stage.Open(str(carrier))
            values = list(stage.GetPrimAtPath("/GAT/State/Belief").GetAttribute("gat:rawMean").Get())
            values[0] += 0.1
            stage.GetPrimAtPath("/GAT/State/Belief").GetAttribute("gat:rawMean").Set(values)
            stage.GetRootLayer().Save()
            with self.assertRaisesRegex(SnapshotError, "integrity digest mismatch"):
                read_openusd(carrier)


if __name__ == "__main__":
    unittest.main()
