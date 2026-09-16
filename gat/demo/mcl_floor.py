"""SE(2) MCL on the two-room floor plate.

Tracking from a local prior should lock. Global initialization starts
bimodal because rooms A and B are similar; the doorway sequence is what
breaks the symmetry. Diagnostics are printed. Nothing is written to BIM
state.

    python -m gat.demo.mcl_floor
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np

from gat.localize import se2
from gat.localize.filter import MotionNoise, ParticleFilter
from gat.localize.floor import corridor_path, two_room_grid
from gat.localize.residual import synthesize_scan


ANGLES = np.linspace(-math.pi * 0.75, math.pi * 0.75, 21)
MAX_RANGE = 5.0
SIGMA = 0.05
MOTION = MotionNoise(sigma_x=0.03, sigma_y=0.01, sigma_theta=0.03)


def _step_control(a: tuple[float, float, float], b: tuple[float, float, float]) -> tuple[float, float, float]:
    rel = se2.relative(np.array(a), np.array(b))
    dt = 1.0
    v = float(rel[0]) / dt
    omega = float(rel[2]) / dt
    return v, omega, dt


def _run_tracking(grid, rng: np.random.Generator) -> list[dict]:
    path = corridor_path()
    filt = ParticleFilter.around(np.array(path[0]), 400, rng, MotionNoise(0.15, 0.15, 0.20))
    rows = []
    for i in range(len(path) - 1):
        pose = np.array(path[i])
        nxt = np.array(path[i + 1])
        v, omega, dt = _step_control(tuple(pose), tuple(nxt))
        scan_next = synthesize_scan(nxt, grid, ANGLES, MAX_RANGE, SIGMA, rng)
        diag = filt.step(v, omega, dt, MOTION, scan_next, grid, SIGMA)
        err = se2.relative(diag.mean_pose, nxt)
        rows.append(
            {
                "step": i + 1,
                "mode": "track",
                "n_eff": diag.n_eff,
                "unique": diag.unique_count,
                "max_w": diag.max_weight,
                "collapsed": diag.collapsed,
                "err_xy": float(math.hypot(err[0], err[1])),
                "err_th": abs(float(err[2])),
            }
        )
    return rows


def _run_global(grid, rng: np.random.Generator) -> list[dict]:
    path = corridor_path()
    filt = ParticleFilter.uniform_free(grid, 800, rng)
    rows = []
    pose = np.array(path[0])
    scan = synthesize_scan(pose, grid, ANGLES, MAX_RANGE, SIGMA, rng)
    filt.update(scan, grid, SIGMA)
    diag = filt.diagnostics()
    filt.resample_if_needed(0.5)
    rows.append(
        {
            "step": 0,
            "mode": "global",
            "n_eff": diag.n_eff,
            "unique": diag.unique_count,
            "max_w": diag.max_weight,
            "collapsed": diag.collapsed,
            "mean": [float(x) for x in diag.mean_pose],
        }
    )
    for i in range(len(path) - 1):
        nxt = np.array(path[i + 1])
        v, omega, dt = _step_control(tuple(path[i]), tuple(nxt))
        scan = synthesize_scan(nxt, grid, ANGLES, MAX_RANGE, SIGMA, rng)
        diag = filt.step(v, omega, dt, MOTION, scan, grid, SIGMA)
        err = se2.relative(diag.mean_pose, nxt)
        rows.append(
            {
                "step": i + 1,
                "mode": "global",
                "n_eff": diag.n_eff,
                "unique": diag.unique_count,
                "max_w": diag.max_weight,
                "collapsed": diag.collapsed,
                "err_xy": float(math.hypot(err[0], err[1])),
                "err_th": abs(float(err[2])),
            }
        )
    return rows


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    out = Path(argv[0]) if argv else None
    rng = np.random.default_rng(7)
    grid = two_room_grid(0.05)
    tracking = _run_tracking(grid, rng)
    global_rows = _run_global(grid, rng)
    print("MCL satellite — two-room floor plate")
    print("Not kernel. Mean pose is not IndependentPoseCalibration.")
    print("tracking:")
    for row in tracking:
        print(
            f"  step {row['step']}  n_eff={row['n_eff']:.1f}  "
            f"unique={row['unique']}  err_xy={row['err_xy']:.3f} m"
        )
    print("global:")
    for row in global_rows:
        extra = ""
        if "err_xy" in row:
            extra = f"  err_xy={row['err_xy']:.3f} m"
        print(f"  step {row['step']}  n_eff={row['n_eff']:.1f}  unique={row['unique']}{extra}")
    last = tracking[-1]
    if last["err_xy"] > 0.35:
        raise SystemExit(f"tracking failed to lock: err_xy={last['err_xy']:.3f}")
    g_last = global_rows[-1]
    print(
        "global disposition: UNRESOLVED "
        f"(bootstrap proposal; n_eff={g_last['n_eff']:.1f}, err_xy={g_last.get('err_xy', float('nan')):.3f} m)"
    )
    if out is not None:
        out = Path(out)
        out.mkdir(parents=True, exist_ok=True)
        payload = {
            "claim": "mcl-se2-v1",
            "not": [
                "kernel",
                "IndependentPoseCalibration",
                "clearance field evidence",
                "zkVM guest of the particle cloud",
            ],
            "tracking": tracking,
            "global": global_rows,
        }
        (out / "mcl-floor.json").write_text(json.dumps(payload, indent=2) + "\n")
        print(f"wrote {out / 'mcl-floor.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
