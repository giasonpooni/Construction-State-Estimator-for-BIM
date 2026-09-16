# Covariance calibration v1

The same chart that walks the mean walks the 1x1 variance.

```text
x' = T x + c
P' = T P T^T     # JSPT push_covariance only
```

Office-A opening: sigma 0.005 m, T = 1000, P' = 25 mm^2, sigma' = 5 mm.
`fused: false`. Binding `office-a-p204:1` onto Width[m] is an observation
edge. It is not a Kalman update.

Beam-B1 live IFC and the certificate pin stay separate worlds that share
`IfcBeam:GATBEAMELEMENT00000100`.

```bash
PYTHONPATH=src:. python -m gat.demo.atlas_gap -o out/atlas
```
Needs the JSPT pin on PYTHONPATH. A local `T @ P @ T.T` in GAT is a fork.
