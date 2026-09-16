# Tool selection v1

Routing spec. Not a new kernel. Not a manifesto.

Pick the question first. Then pick the opcode or repo that already
answers it. Do not open CUDA because the question was hard.

| Problem asks | Machine | Here |
|---|---|---|
| What is changing? | derivatives | JSPT `jacobian_at`; CSE `propagate` |
| What accumulated? | integration | FSRT storage/balance; CSE ledger |
| What interacts linearly? | linear algebra | dense `Sigma`; FSRT incidence |
| What is uncertain? | probability | calibrated `sigma`; Joseph update |
| What state generated observations? | estimation | `ObserveQuantity` / `ObserveLinearized` |
| Where is it heading? | dynamics | `evolve_linear_gaussian` |
| Will it converge? | Lyapunov | PLSR on a declared `A` from JSPT |
| What action should I take? | control / plan | `plan_observations`; `SetParameter` |
| What is connected? | graphs | IFC contain/void; FSRT incidence |
| What structure survives transform? | invariants | world digest; units; beam identity |
| How does geometry transform? | charts | JSPT; IFC placements |
| What frequencies/modes exist? | spectrum | cut hint on declared `G` only |
| What can actually be reached? | viability | inspectability fold on `space_id` |

## Authority

- Python may INVOKE `python_uv`.
- `rust_ingest`, `cuda_jspt`, `sp1_zkvm`, `dense_sigma_rebuild` are
  `rust-effort-gate`, default refuse.
- IfcOpenShell inventories Guids. It does not pass inspection.
- OpenUSD carries a restart. Blender paints a receipt.

If the hole is `bind.point_to_guid`, the machine is a bind file, not a
renderer.
