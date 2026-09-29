# State Estimator

**Estimate state from evidence while keeping uncertainty and missing information explicit.**

[Notation Systems](#notation-systems) · [Quickstart](#quickstart) ·
[Technical reference](TECHNICAL_REFERENCE.md) · [Documentation](docs) ·
[Copyright and licence](#copyright-and-attribution)

## NET micro-tool

| Identity | Value |
| --- | --- |
| User-facing name | **State Estimator** |
| Proposed NET operation | `state.estimate` |
| Implementation repository | `State-Estimator-for-BIM` |
| Existing runtime | Construction State Estimator / CSE; distribution `gat-bim`; imports and command `gat` |
| Current scope | BIM-specific evidence conditioning and evidence-to-decision workflows |

The friendly name describes the reusable estimation capability to expose through
[Notations Systems Terminal (NET)](https://github.com/giasonpooni/Notations-Systems-Terminal).
The NET operation name is an interface target, **not a newly implemented command
or a claim that a general-purpose adapter is available**. Use the existing
interfaces documented in the technical reference today.

Construction State Estimator (CSE) connects IFC design intent with physical
evidence and an inspectable belief about the built state. Missing or inadequate
evidence remains explicit; a software disposition is not construction approval.
Reusable estimation primitives may be extracted behind `state.estimate`, while
this provider retains its BIM-specific assumptions and verification boundaries.

## Notation Systems

**Notation Systems develops evidence-backed industrial intelligence, computational instrumentation and tooling for physical systems.** Its purpose is to connect domain expertise, observations and declared models to inspectable computation, justified decisions and bounded production work. The service direction remains **verify → refresh → reconstruct** for an agreed scope.

The industrial domains remain **PAYLOAD** (organizations, facilities, materials, shipments and operational networks, including Caravan), **LANDSHARK** (land/site, ownership/use and spatial constraints), and **TRADEWIND** (contracts, prices and exposure). PayloadOS/ESM retain governed industrial evidence/state responsibilities; Dossier Services packages scoped service outputs. NET is the shared programmable workbench/control plane, not a replacement for those authorities or this BIM instrument.

**Cartesian Graphics** is the firm's games, graphics, physics and simulation studio/label: 1792 is primary, Garibaldi is secondary, and Geronimo remains on hold. Manufacturing, robotics, materials/chemistry, GIS/remote sensing, DSP and analytics are engineering workload families, not additional public product rooms or claims of completed adapters. The parent/studio relationship does not assert a separately incorporated subsidiary.

Work by **[Giason Pooni](https://github.com/giasonpooni)** retains contributor and upstream attribution. Each repository keeps its own implementation, scientific contracts, status and licence. Project links do not imply hosted services, a released game, or permission to execute operations.

## Role, contribution and status

| Field | This project |
| --- | --- |
| Role | State-estimation tool backed by a BIM-specific estimation and evidence-to-decision instrument; portfolio category: **Research**, with engineering-simulation applications. |
| Author's work | System design, state representation, evidence handling, disposition logic, implementation and validation workflows. |
| Technology | Python and NumPy, with the documented optional IFC/OpenUSD and native integrations. |
| Runtime identity | **Construction State Estimator / CSE**, distribution **`gat-bim`**, import and command identity **`gat`**. |
| Status | Experimental software with declared assumptions and demonstration fixtures; general-purpose extraction and NET alias registration are separate implementation work. |

## Place in the workflow

The intended expertise-amplification path is **expert input → retained claims and evidence → reviewed specification → typed work → candidate result → observations and verification → separately authorized integration/release**. CSE contributes BIM-specific evidence conditioning and dispositions; it does not turn an expert's heuristic into a physical law or a software disposition into construction approval.

NET owns investigation/session composition and execution history, retaining NET / `net` / `ciw` identities. CSE retains its BIM semantics and model assumptions. Frame Mapper may transform supplied representations and GSV may project them read-only; ESM retains industrial admission/release. Games retain their own live state, clocks and creative/release authority. New workloads extend these boundaries rather than replacing verified instruments or creating a parallel ledger.

The estimation pattern can inform other simulation projects. The tool name does
not make the existing implementation a generic rover estimator or NPC perception
library. It is not a learned model, a Revit replacement, a general finite-element
solver or a construction-approval authority. Demonstration fixtures are not
field evidence.

Evidence, operation specifications, execution attempts and verification records
remain distinct. General expertise capture, dependency-aware rebuilding and secured agent workers remain development targets. Logical containers and MCP interfaces do not themselves establish OS isolation or grant execution permission. Optional C++–Rust–Python–Julia bindings do not require four runtimes or provide arbitrary language translation. Measure accepted useful work alongside human review, cost, rework and domain-specific validation; 1792 is a reference workload, not proof of industrial transfer.

## Quickstart

Use the setup and runnable examples in
[TECHNICAL_REFERENCE.md](TECHNICAL_REFERENCE.md). The existing `gat` imports,
commands, optional-dependency boundaries and fail-closed contracts are unchanged.

## Technical reference

The complete previous technical README is preserved **verbatim** in
[TECHNICAL_REFERENCE.md](TECHNICAL_REFERENCE.md), retaining installation,
headless-request examples, workflow guidance and limitations. It remains at
the repository root so relative links retain their original base and is unchanged by this update.

[NET](https://github.com/giasonpooni/Notations-Systems-Terminal) and
[Frame Mapper / GSC](https://github.com/giasonpooni/Notations-FrameMapper-RunTime)
are related projects, not prerequisites for every standalone CSE workflow.

## Copyright and attribution

**© 2026 Giason Pooni, for original contributions.** The Notation Systems and
Cartesian Graphics relationship does not claim ownership over third-party tools
or inherited code. Contributor and upstream copyright notices remain in force.

The existing [LICENSE](LICENSE), source notices and third-party terms continue
to govern the code and included materials. This documentation update does not
relicense the project, add a blanket “all rights reserved” restriction, or
change the rights already granted by those terms.
