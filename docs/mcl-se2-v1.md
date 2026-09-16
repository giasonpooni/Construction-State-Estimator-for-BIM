# SE(2) Monte Carlo localization satellite v1

Status: satellite. Not kernel.

## What shipped

`gat.localize` is planar MCL on a known occupancy slice:

- poses live on SE(2); motion and process noise live in se(2)
- optional tangents are pushed by the adjoint of each increment
- the measurement morphism is a range residual against the occupancy grid
- `N_eff`, unique support, max weight, and tangent covariance are recorded
  *before* resampling
- `gat.satellites.scan_residual_i32` is the integer residual a guest could
  later prove; it is not a particle filter

```bash
python -m unittest tests.test_mcl_se2
python -m gat.demo.mcl_floor
python -m gat.demo.mcl_floor out/mcl
```

## What it is allowed to say

Tracking from a local prior on the two-room plate can lock. Global
initialization on that plate is **UNRESOLVED** under the bootstrap
proposal: rooms A and B are similar, lidar-like scans are sharp, and
the motion model is a poor proposal. That is an observability statement,
not a bug to hide.

## What it is not

- Not a kernel change. Dispositions, digests, and ledger replay are
  untouched.
- Not `IndependentPoseCalibration`. A particle mean cannot close a
  clearance case and cannot feed `gat.geometry.scan_likelihood` as
  survey control.
- Not a fluid-state estimator. High-dimensional fields stay with ensemble
  / variational tools.
- Not an SP1 guest of the cloud. The guest-shaped object is the i32
  residual, and even that is not packaged as a circuit in this grain.
- Not AMCL, ROS, or a 3D lidar stack.

## Relation to existing geometry modules

`gat.geometry.registration` fits a deterministic 4-DOF transform and
must not be recycled as independent evidence about the same BIM.
`gat.geometry.scan_likelihood` already requires an external pose.
This satellite estimates pose given a *declared* floor plate. Those
three roles stay separate.
