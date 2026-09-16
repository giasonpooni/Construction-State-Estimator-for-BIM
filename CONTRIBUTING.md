# Contributing to CSE

CSE treats numerical state, evidence, verification, and provenance as one
assurance boundary. Changes should be small enough to review and should add
executable evidence for their claims.

Public name: Construction State Estimator (CSE). Package: `gat-bim`.
Import / CLI: `gat`.

## Change process

1. Work on a topic branch. Do not push implementation commits directly to
   `main`.
2. Open a pull request and wait for all required CI jobs to pass.
   The SP1 beam job is a satellite: it runs only on `workflow_dispatch`
   with `run_sp1=true`, or when the commit message contains `[sp1]`.
   A red SP1 lane must not block a kernel change that does not touch
   the guest.
3. Keep each pull request focused on one falsifiable milestone.
4. For large or security-relevant changes, include an adversarial review pass
   before merge and resolve or explicitly document every finding.
5. Describe limitations and negative results alongside successful behavior.
6. A change that alters a disposition, digest, or replay on the acceptance /
   beam / RFI slice is a kernel version bump. See `docs/kernel-v1.md`.

Repository administrators should protect `main` by requiring pull requests,
green CI, and no force pushes. Branch protection is a repository setting and
cannot be enforced by this file alone.

## Verification

Before opening a pull request, run:

```console
python -m pip install -e .
python -m unittest discover -s tests -v
python -m gat.demo.workflow
```

When OpenUSD or carrier-signature code changes, install `.[openusd]` and run:

```console
python -m unittest tests.test_openusd tests.test_headless -v
python -m gat.demo.openusd_portability openusd-validation-out
```

## Public validation data

Do not add unpinned downloads or large opaque fixtures. A public model entry
must record its source repository, exact commit, license, source path, byte
size, SHA-256, and measured expected result in
`validation/ifc-corpus-v1.json`. Routine CI data should remain small. Large
models belong in the optional validation tier.

Compatibility work must report unsupported entities explicitly. Partial
ingestion or skipped geometry must never silently authorize an acceptance
decision. An audit is not a decision; see
`docs/real-ifc-validation-v1.md`.
