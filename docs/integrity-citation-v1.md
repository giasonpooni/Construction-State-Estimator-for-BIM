# Integrity citation v1

Team convenience without coupling SP1 to the OpenUSD carrier.

```text
packet/
  cse.usdc                     signed restart (unchanged digest)
  world.usda                   assembly; may point at a citation
  kernel_sp1_receipt.json      statement_digest + status
  06-integrity-citation.json   pointer, not proof bytes
```

`gat:integrityCitation` on `/World` is a string JSON pointer. It is not
inside `/GAT/State`. `read_openusd` still fails closed on the assembly.
Proof bytes never go in USD.

A citation cannot condition belief or authorize.
