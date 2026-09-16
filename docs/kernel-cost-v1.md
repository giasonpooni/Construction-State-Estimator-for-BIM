# Kernel cost v1

Host op counts for the discrete maps that a guest could later prove.
SP1 cycles stay empty until `cargo execute` on the pinned ELF fills them.
Do not invent a cycle number.

```bash
python -m gat.demo.kernel_cost -o out/kernel-cost
```

chain_jvp_i32: 8 mul, 4 add. Lyapunov decrease sample: 16 mul, 8 add.
IEEE-754 guest: false. RISC-V OT: declared, not flashed. Sheaf: closed.
