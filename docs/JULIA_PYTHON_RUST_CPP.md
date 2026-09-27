# CSE in the Julia–Python–Rust–C++ system

CSE remains the scientific owner of IFC lowering, Gaussian belief, the derived
quantity Jacobian, evidence conditioning, dispositions and ledger history.
`gat.adapters.polyglot.linear_response_case` exports a **local mean response**
without committing a World or introducing a second inference engine.

```text
Python CSE World + actual Jacobian
  -> notation.linear-map.v1 (data only)
  -> Python CIW validation and unit normalization
  -> existing SCR / Rust host
       -> existing C++ affine kernel OR existing Julia affine provider
  -> retained CIW result -> read-only GSC quantity inspection
```

CIW is not a dependency of this package. Its companion implementation lives in
`Notations-Engineering-Terminal/src/ciw/polyglot_linear_map.py`; the consumer
contract and runtime provisioning are documented there in
`docs/JULIA_PYTHON_RUST_CPP.md` and `docs/NATIVE_INTEROP.md`.

## Export an existing World

```python
from gat.adapters.polyglot import linear_response_case

case = linear_response_case(
    session.world,
    inputs=[width_var, height_var],       # existing raw VarIds
    outputs=[area_var],                  # existing raw or derived VarIds
    deltas=[0.001, -0.002],
    input_scales=[0.001, 0.001],
    output_scales=[0.01],
)
```

The adapter selects actual rows and columns from `world.jacobian`, means from
`world.full.mu`, units from the selected slots, and the unchanged complete
`world.digest()`. The case is `y0 + J_selected delta`: a derived area response
is a tangent approximation, not a recomputed nonlinear area or an observation.

Inputs must be known raw variables. One to eight distinct input and output
coordinates are supported; deltas/scales must match their dimensions. Missing
Jacobians, nonfinite/coerced values and nonpositive scales are refused. Scales
normalize declared units; the adapter does not guess conversions or frames.

Save the original World/snapshot alongside the case. Native execution binds
the complete case digest, including source identity, selected variables, units,
frame and scales. It cannot change a World, condition a belief, alter a ledger,
accept a construction or satisfy an as-built evidence requirement.

## Checks

```sh
python -m unittest discover -s tests -p 'test_polyglot*.py' -v
```

`test_polyglot_adapter.py` exercises explicit in-memory protocol doubles and
actual matrix selection. `test_polyglot_world.py` separately loads the shipped
IFC beam model and verifies the real World's raw identity tangent and unchanged
covariance/digest. It does not skip missing fixtures or dependencies. Native
C++/Julia execution is a separate required CIW qualification gate, not inferred
from these Python tests.

All exported cases state `first-order-mean-response-only`,
`covariance: not_propagated`, and `may_authorize: false`. The full correlated
belief remains in CSE; this adapter neither discards it from CSE nor claims to
propagate it through the new native mean-response seam. Existing Rust/SP1 paths
remain separate. No source-to-binary attestation or physical validation is added.
