# Session contract v1

`GatSession` is a **facade**. It is not a second world.

```text
IFC / snapshot / OpenUSD
        |
        v
   World.compile | reconstruct
        |
        v
   execute(transform)     kernel
        |
        v
   ledger.record_*        kernel
        |
        v
   GatSession.world + ledger + trace
```

## Allowed methods

| Method | Meaning |
| --- | --- |
| `load_ifc` | Parse + lower + `World.compile` + genesis ledger |
| `var(name, quantity)` | Look up one `VarId` by entity name |
| `run(transform)` | `execute` then `record_transition` or `record_rejection` |
| `verify` | Run the invariant registry on the current world |
| `export_openusd` | Project `world + ledger + trace` to the carrier |
| `load_openusd` | Reconstruct session from a carrier; resume the same ledger |

`execute`, `World`, and `ExecutionLedger` remain the kernel. OpenUSD is a
suitcase. A stage that parses is not an accepted world.
