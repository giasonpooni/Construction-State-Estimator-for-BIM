# Experiment index

How to try the tools. Each repo is its own clone. No submodule. No monorepo.

BIM construction acceptance is the first demonstrator. The frameworks are
for industrial data integration, computational instrumentation, and
maintained evidence services. See [domain-v1.md](domain-v1.md),
[sandbox-v0.md](sandbox-v0.md), and [calibrate-verify-v1.md](calibrate-verify-v1.md).

## CSE (this repo)

```bash
python -m pip install -e .
python -m unittest discover
python -m gat.demo.beam_assurance out/beam
python -m gat.demo.experiment_harness --demo -o out/harness-bundle.json
python -m gat.demo.usd_projection --demo -o out/usd-projection.json
python -m gat.demo.calibrate_verify --demo -o out/calibrate-verify
```

`calibrate_verify` will not run without a calibration declaration and a
measurement. The shipped demo is a prototype: invariants may pass and the
packet may be presentable; it is still not field evidence.

## Flat torus

https://github.com/giasonpooni/Flat-Torus-Moduli-and-Geodesic-Explorer

```bash
PYTHONPATH=src python examples/quickstart.py
PYTHONPATH=src python examples/write_validation.py
```

## Instrument host contract

https://github.com/giasonpooni/Retrofitted-Computational-Instrumentation

```bash
PYTHONPATH=src python -m pytest
PYTHONPATH=src python examples/displacement_bench.py
```

## JSPT

https://github.com/giasonpooni/Jacobian-Sensitivity-Propagation-Testbed

Owns A2-A5. Pin SHA in [jspt-pin-v1.md](jspt-pin-v1.md).
