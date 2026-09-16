# Experiment index

How to try the tools. Each repo is its own clone. No submodule. No monorepo.

BIM construction acceptance is the first demonstrator. The frameworks are
for industrial data integration, computational instrumentation, and
maintained evidence services (manufacturing, infrastructure, agri-food,
logistics). See [domain-v1.md](domain-v1.md).

## CSE (this repo)

```bash
python -m pip install -e .
python -m unittest discover
python -m gat.demo.beam_assurance out/beam
python -m gat.demo.experiment_harness --demo -o out/harness-bundle.json
```

`--demo` binds the shipped fixtures and the Beam-B1 pin. It does not prove.

## Flat torus

https://github.com/giasonpooni/Flat-Torus-Moduli-and-Geodesic-Explorer

```bash
PYTHONPATH=src python examples/quickstart.py
PYTHONPATH=src python examples/fold.py
PYTHONPATH=src python examples/write_validation.py
```

Hand `validation/torus-first-release-commitment-v1.json` to the harness with `--commit`.
Invariant of an object under a change of representation — not a BIM solid.

## Instrument host contract

https://github.com/giasonpooni/Retrofitted-Computational-Instrumentation

```bash
PYTHONPATH=src python -m pytest
PYTHONPATH=src python examples/displacement_bench.py
```

Host stand-in for computational instrumentation. Not a measured millimetre.
Never proves.

## JSPT

https://github.com/giasonpooni/Jacobian-Sensitivity-Propagation-Testbed

```bash
uv run --python 3.13 python examples/quickstart.py
```

Owns A2-A5 for every sector. Not a harness `--commit`. Not a guest.

## FSRT

https://github.com/giasonpooni/Fluid-State-Reconstruction-Testbed

```bash
uv run --frozen --python 3.13 python examples/quickstart.py
```

Inventory / balance evidence. Own experiment. No beam slot. No harness schema yet.

## Jacobi companion

https://github.com/giasonpooni/Geodesic-Flow-and-Jacobi-Field-Testbed

Scaffold. Use the torus first. Planned comparison against `s`, `sin s`, `sinh s`.
No guest.
