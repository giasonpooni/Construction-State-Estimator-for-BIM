# Declared calibration v1

Satellite record. A finite `sigma` on a named quantity. Not a certificate.

See [validation/cse-calibration-v1.json](../validation/cse-calibration-v1.json).

`gat-present --apply-lab-observation` will not run without this file.
`traceable: false` keeps `may_authorize` false even after a lab observe.
