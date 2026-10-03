# Complete bounded belief covariance in native response studies

The new `gat.adapters.polyglot_uncertainty.uncertainty_inputs` adapter extends
the existing mean-response adapter. It includes every raw variable in the World,
the full raw belief covariance, and selected output rows of the current actual
Jacobian. Worlds with more than eight raw variables refuse: this interface does
not quietly discard correlations by substituting selected marginals.

```python
from gat.adapters.polyglot_uncertainty import uncertainty_inputs

export = uncertainty_inputs(world, selected_output_vars, delta_for_every_raw_var,
                            input_scales=raw_scales, output_scales=output_scales)
```

The Jacobian is fixed at the original World. The covariance of its belief is
translated into perturbation coordinates about the current means; translation
does not change covariance. A changed mean does not trigger relinearization in
this interface. The original World, full covariance, digest and ledger remain
unchanged. This is not evidence conditioning or a construction disposition.

The returned notation.domain-uncertainty-inputs.v1 is plain data. The
[companion Terminal implementation](https://github.com/giasonpooni/Notations-Engineering-Terminal/blob/8782bee2a83087cf66d325e0b4b42a4fe5b04cdb/src/ciw/polyglot_uncertainty.py)
validates and binds it through the existing covariance-artifact validator, then
computes J C J^T by composing approved Rust-supervised C++ or Julia affine
operations. A separate rational reference checks the output. No CIW dependency
or native implementation is copied into CSE.

The [shared contract](https://github.com/giasonpooni/Notations-Engineering-Terminal/blob/8782bee2a83087cf66d325e0b4b42a4fe5b04cdb/docs/POLYGLOT_UNCERTAINTY.md)
defines normalization, numerical policy, stage identities, replay and limits.
A covariance view is not calibration, physical validation, a Gaussian interval,
SP1 proof or state admission. Evidence dependencies remain with the retained
World; this adapter does not manufacture a list of independent measurements.

Run `python -m unittest discover -s tests -p 'test_polyglot*.py' -v` for the
producer gates. Four added tests use the actual shipped IFC beam World and
check complete covariance, its derived congruence, immutable source state and
refusal of partial/oversized inputs. Native execution is a separate gate in the
Terminal/SCR integration, not inferred from these Python tests.
