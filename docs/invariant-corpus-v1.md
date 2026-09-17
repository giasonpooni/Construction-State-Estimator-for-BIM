# Invariant reference corpus v1

Focal split for this stack:

```text
I  invariant corpus     declared identity of the plant
   needle
x  free coordinates     what measurements may still move
```

Inference does not invent names. If a tool cannot point at a row in
`validation/invariant-corpus-v1.json`, it is another file, not reconstruction.

Load: `from gat.corpus import load_corpus`.
Needle only `var.*` rows. Invariants raise `CorpusError`.

Cross-repo copies must keep `schema: invariant-corpus-v1` and
`claim_scope: computational-integrity-only`. They add local identities;
they do not add a second engine.
