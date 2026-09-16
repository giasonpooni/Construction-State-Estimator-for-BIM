# JSPT consumption

GAT calls `sensitivity.push_covariance`. It does not form `T @ P @ T.T`.

Pin a JSPT SHA in CI. Tests skip if `sensitivity` is not installed.

```
pip install -e ../Jacobian-Sensitivity-Propagation-Testbed
pytest tests/test_jspt_consume.py
```
