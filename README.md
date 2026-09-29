# Notations Estimator for BIM

**Connect IFC design intent with evidence about the built state, keeping uncertainty and missing information explicit.**

[Quickstart](#quickstart) · [Technical reference](TECHNICAL_REFERENCE.md) · [Research profile](#research-profile) · [Documentation](docs) · [Licence](LICENSE)

Construction State Estimator (CSE) produces an inspectable belief and disposition under its declared BIM assumptions. A software disposition is not construction approval, and a demonstration fixture is not field evidence.

## NET micro-tool

| Identity | Value |
| --- | --- |
| User-facing capability | **State Estimator — BIM** |
| Proposed NET operation | `state.estimate` |
| Current repository | `Notations-Estimator-for-BIM` |
| Existing runtime | CSE; distribution `gat-bim`; imports and command `gat` |
| Scope | BIM-specific evidence conditioning and evidence-to-decision workflows |

The NET name is an interface target, not a newly installed command or a generic estimator adapter. Use the existing interfaces in the technical reference. Reusable estimation primitives may be extracted while this provider retains its BIM semantics.

## Notation Systems

**Frontier Tooling and Instrumentation for Digital Futures.** Notation Systems develops computational instruments and operational tooling that connect scientific methods, specialist computation and human expertise.

[Notations Systems Terminal](https://github.com/giasonpooni/Notations-Systems-Terminal) owns investigation/session composition and execution history. This repository owns its mathematical and BIM implementation. Operational products, governed evidence/state services and Cartesian Graphics' interactive worlds, simulation and digital-IP work retain separate responsibilities. [Organization profile](https://github.com/giasonpooni/Notations-Systems-Terminal/blob/b41b84922d4963a9206202029afd1e78b9451f9c/PUBLIC_POSITIONING.md).

## Role, contribution and status

Experimental research software with declared assumptions and fixtures. Original work covers system design, state representation, evidence handling, disposition logic, implementation and validation workflows. The implementation uses Python and NumPy with documented optional IFC/OpenUSD and native integrations.

The package is not a Revit replacement, general finite-element solver, learned model, generic rover estimator or NPC perception library. NET alias registration and additional applications require explicit implementation and validation.

## Place in the workflow

An expert supplies design intent, evidence and questions. CSE applies its declared evidence-conditioning rules. NET can coordinate supported work; FrameMapper and the geographic viewer consume explicit representations. ESM retains industrial admission and release authority. Neither a visual projection nor a generated explanation authorizes a state change.

Evidence, annotations, specifications, execution attempts, results and verification remain distinct. Game worlds keep their own live state, clocks and creative approval. Shared geometry or software interfaces do not establish physical validity across domains.

## Research profile

**Question:** how should a system preserve the distinction between intended, observed, inferred and accepted built state? This instrument offers a concrete specimen for missing evidence, conflicting claims and model-conditional dispositions.

Proposed evaluation should compare fixed evidence-to-decision cases, retain unresolved outcomes and measure traceability, reproducibility and expert review effort. Synthetic correctness is not field validation. Changes to a representation must preserve the assumptions and evidence needed by the actual disposition—not merely reproduce a screenshot.

The wider programme studies composition and computational cost without forcing every project into the same schema or language. Python/Julia/Rust/C++ providers and CUDA are optional, separately qualified implementations; this README installs none. [Research protocol](https://github.com/giasonpooni/Notations-Systems-Terminal/blob/b41b84922d4963a9206202029afd1e78b9451f9c/RESEARCH_PROGRAMME.md).

## Quickstart

Use the setup and runnable examples in [TECHNICAL_REFERENCE.md](TECHNICAL_REFERENCE.md). Existing `gat` imports, commands, dependency boundaries and refusal contracts remain unchanged.

## Technical reference

[TECHNICAL_REFERENCE.md](TECHNICAL_REFERENCE.md) retains the full technical README verbatim, including installation, headless requests, workflows and limitations. Its root-relative links remain valid and its contents are unchanged by this update.

[NET](https://github.com/giasonpooni/Notations-Systems-Terminal) and [FrameMapper](https://github.com/giasonpooni/Notations-FrameMapper-RunTime) are related projects, not prerequisites for every standalone workflow. No code, tests, licences or release state are changed here; no new qualification run is claimed.

## Copyright and attribution

**© 2026 Giason Pooni, for original contributions.** Contributor and upstream notices remain in force. Existing [LICENSE](LICENSE), source notices and third-party terms govern the materials. Public-interest and private-IP positioning do not relicense code, transfer rights or establish a new legal entity.
