# SP1 numerics v0

Hard constraint: zkVMs are integer / finite-field machines. IEEE-754 in
the guest is emulated and expensive. Do not start with a
double-precision geodesic.

## Honest paths

1. Fixed-point / scaled-integer recurrences for maps already discrete.
2. Interval or affine boxes so the claim is "the real result is in this
   interval," which matches uncertainty better than one float.
3. A precompile only if a kernel is hot enough to justify it.
4. Research float arithmetizations later. Not production SP1 today.

## First kernel (shipped as a host reference)

`gat.satellites.fixedpoint_kernel` is two pure i32 maps:

- `chain_jvp_i32` — \(y = J_2 J_1 dx\) (JSPT chain rule, 2×2).
- `discrete_lyapunov_decrease_i32` — \(x^+ = Ax\), \(V=x^TPx\),
  claim \(V^+ < V\) on one published sample (PLSR shape, not a synthesis).

Both refuse Python `float` in the hot path. Neither is a guest binary.
`sp1_zkvm` stays `allowed: false`.

## Order after this page

1. Compile one of those functions as an SP1 guest. Measure cycles.
   Prove locally. Then decide if the vector is a weekend or a redesign.
2. Treat RISC-V as an ISA with a Sail/Lean witness, not a brand.
3. Rank SP1 / RISC Zero / Jolt on *this* kernel's cycle count, not on
   light-client benches.
4. Next discrete morphisms worth a circuit: Jacobian products along a
   trajectory, a symplectic step check, a discrete Jacobi field, a
   Lyapunov inequality on the same trace.
5. RISC-V outside ZK stays the OT line (Ibex-class estimators).
6. Sheaf language only if a specific certificate gets shorter.

## Do not

- Prove arbitrary Rust with allocations and floats.
- Replace interval analysis, adjoints, or Lyapunov theory with a prover.
- Index on rollup gas.
- Make SP1 the only zkVM. The ISA outlives the prover.
