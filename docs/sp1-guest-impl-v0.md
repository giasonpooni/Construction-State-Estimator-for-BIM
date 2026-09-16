# SP1 guest implementation v0

Implemented: the discrete i32 maps as a Rust library and a guest-shaped
binary. Not implemented: a Succinct prove, a precompile, or default CI.

```text
rust/fixedpoint_kernel   host + unit tests against the pin
rust/sp1_guest           same maps, CLI, invoked=false
```

Next measurement, only under rust-effort-gate and workflow_dispatch:
compile `chain_jvp_i32` with `cargo prove`, record cycle count, verify
locally. That number decides whether the vector is a weekend or a
numeric redesign.
