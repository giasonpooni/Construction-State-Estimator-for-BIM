"""Compose a viewer assembly around the OpenUSD carrier.

Satellite. Path C (restart) stays a standalone CSE carrier. Path A
(display) is a sibling payload. Point binds stay JSON files — they are
never authored as USD prims.

    /World
      GAT       reference to cse.usdc:/GAT
      SiteLook  payload/reference to display USD
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from gat.adapters.openusd import openusd_available
from gat.errors import OpenUsdError

ASSEMBLY_KIND = "cse-combined-usd-stage-v1"


@dataclass(frozen=True)
class CombinedUsdStage:
    assembly_path: Path
    carrier_path: Path
    display_path: Path
    bind_path: Path | None


def _asset_ref(from_file: Path, target: Path) -> str:
    target = target.resolve()
    try:
        return str(target.relative_to(from_file.parent.resolve()))
    except ValueError:
        return str(target)


def write_display_layer(path: str | Path) -> Path:
    """Write a disposable Path A stand-in. Not IfcConvert. Not authority."""
    if not openusd_available():
        raise OpenUsdError("usd-core is not installed; pip install '.[openusd]'" )
    from pxr import Gf, Sdf, Usd, UsdGeom

    output = Path(path)
    if output.exists():
        output.unlink()
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Usd.Stage.CreateNew(str(output))
    UsdGeom.SetStageMetersPerUnit(stage, 1.0)
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
    root = UsdGeom.Xform.Define(stage, "/SiteLook").GetPrim()
    stage.SetDefaultPrim(root)
    root.CreateAttribute("gat:displayOnly", Sdf.ValueTypeNames.Bool, custom=True).Set(True)
    root.CreateAttribute("gat:authoritative", Sdf.ValueTypeNames.Bool, custom=True).Set(False)
    cube = UsdGeom.Cube.Define(stage, "/SiteLook/Marker")
    cube.GetSizeAttr().Set(1.0)
    UsdGeom.XformCommonAPI(cube).SetTranslate(Gf.Vec3d(0.0, 0.0, 0.5))
    if not stage.GetRootLayer().Save():
        raise OpenUsdError(f"could not write display layer {output}")
    return output.resolve()


def write_combined_stage(
    *,
    carrier_path: str | Path,
    assembly_path: str | Path,
    display_path: str | Path | None = None,
    bind_path: str | Path | None = None,
) -> CombinedUsdStage:
    """Write /World assembly. Restart remains load_openusd(carrier_path)."""
    if not openusd_available():
        raise OpenUsdError("usd-core is not installed; pip install '.[openusd]'" )
    from pxr import Sdf, Usd, UsdGeom

    carrier = Path(carrier_path).resolve()
    assembly = Path(assembly_path)
    if assembly.exists():
        assembly.unlink()
    if not carrier.is_file():
        raise OpenUsdError(f"carrier does not exist: {carrier}")
    if display_path is None:
        display = write_display_layer(assembly.with_name("sitelook.usda"))
    else:
        display = Path(display_path)
        if not display.is_file():
            display = write_display_layer(display)
        display = display.resolve()
    assembly.parent.mkdir(parents=True, exist_ok=True)
    stage = Usd.Stage.CreateNew(str(assembly))
    UsdGeom.SetStageMetersPerUnit(stage, 1.0)
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
    world = UsdGeom.Scope.Define(stage, "/World").GetPrim()
    stage.SetDefaultPrim(world)
    world.CreateAttribute("gat:assemblyKind", Sdf.ValueTypeNames.String, custom=True).Set(
        ASSEMBLY_KIND
    )
    world.CreateAttribute("gat:restartPath", Sdf.ValueTypeNames.String, custom=True).Set(
        _asset_ref(assembly, carrier)
    )
    if bind_path is not None:
        world.CreateAttribute("gat:bindPath", Sdf.ValueTypeNames.String, custom=True).Set(
            str(Path(bind_path))
        )
        world.CreateAttribute("gat:bindsInUsd", Sdf.ValueTypeNames.Bool, custom=True).Set(False)

    gat = stage.DefinePrim("/World/GAT", "Scope")
    gat.GetReferences().AddReference(_asset_ref(assembly, carrier), "/GAT")
    look = stage.DefinePrim("/World/SiteLook", "Xform")
    look.GetPayloads().AddPayload(_asset_ref(assembly, display), "/SiteLook")
    look.CreateAttribute("gat:authoritative", Sdf.ValueTypeNames.Bool, custom=True).Set(False)

    if stage.GetPrimAtPath("/World/Binds"):
        raise OpenUsdError("combined stage must not author a /World/Binds prim")
    if not stage.GetRootLayer().Save():
        raise OpenUsdError(f"could not write assembly {assembly}")
    return CombinedUsdStage(
        assembly_path=assembly.resolve(),
        carrier_path=carrier,
        display_path=display,
        bind_path=Path(bind_path) if bind_path else None,
    )
