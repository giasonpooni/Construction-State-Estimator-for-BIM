# State Estimator

**Estimate state from evidence while keeping uncertainty and missing information explicit.**

[Portfolio](https://notation.systems) · [Quickstart](#quickstart) ·
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
[Notations Engineering Terminal (NET)](https://github.com/giasonpooni/Notations-Engineering-Terminal).
The NET operation name is an interface target, **not a newly implemented command
or a claim that a general-purpose adapter is available**. Use the existing
interfaces documented in the technical reference today.

Construction State Estimator (CSE) connects IFC design intent with physical
evidence and an inspectable belief about the built state. Missing or inadequate
evidence remains explicit; a software disposition is not construction approval.
Reusable estimation primitives may be extracted behind `state.estimate`, while
this provider retains its BIM-specific assumptions and verification boundaries.

## Notation Systems

[notation.systems](https://notation.systems) is the portfolio umbrella for
independent computational systems, simulation and interactive-software projects
by **[Giason Pooni](https://github.com/giasonpooni)**. The website presents the
work; each repository retains its own implementation, status and licence.

Portfolio areas: **Games & Interactive · Simulation · Tools · Research · About**.
Website publication and repository availability are separate; a project link
does not imply that a hosted demo or released game exists.

## Role, contribution and status

| Field | This project |
| --- | --- |
| Role | State-estimation tool backed by a BIM-specific estimation and evidence-to-decision instrument; portfolio category: **Research**, with engineering-simulation applications. |
| Author's work | System design, state representation, evidence handling, disposition logic, implementation and validation workflows. |
| Technology | Python and NumPy, with the documented optional IFC/OpenUSD and native integrations. |
| Runtime identity | **Construction State Estimator / CSE**, distribution **`gat-bim`**, import and command identity **`gat`**. |
| Status | Experimental software with declared assumptions and demonstration fixtures; general-purpose extraction and NET alias registration are separate implementation work. |

## Place in the workflow

NET is the surrounding investigation workbench; CSE retains its BIM semantics
and model assumptions. GSC may present explicitly supplied representations,
while the portfolio explains the work and links to its source.

The estimation pattern can inform other simulation projects. The new name does
not make the existing implementation a generic rover estimator or NPC perception
library. It is not a learned model, a Revit replacement, a general finite-element
solver or a construction-approval authority. Demonstration fixtures are not
field evidence.

Evidence, operation specifications, execution attempts and verification records
remain distinct. Renaming the overview does not change contracts or authorize
execution, admission or release.

## Quickstart

Use the setup and runnable examples in
[TECHNICAL_REFERENCE.md](TECHNICAL_REFERENCE.md). The existing `gat` imports,
commands, optional-dependency boundaries and fail-closed contracts are unchanged.

## Technical reference

The complete previous technical README is preserved **verbatim** in
[TECHNICAL_REFERENCE.md](TECHNICAL_REFERENCE.md), retaining installation,
headless-request examples, workflow guidance and limitations. It remains at
the repository root so relative links retain their original base.

[NET](https://github.com/giasonpooni/Notations-Engineering-Terminal) and
[Frame Mapper / Geospatial Systems Compiler](https://github.com/giasonpooni/Geospatial-Systems-Compiler)
are related projects, not prerequisites for every standalone CSE workflow.

## Copyright and attribution

**© 2026 Giason Pooni, for original contributions.** Notation Systems is the
independent project umbrella, not a claim of ownership over third-party tools
or inherited code. Contributor and upstream copyright notices remain in force.

The existing [LICENSE](LICENSE), source notices and third-party terms continue
to govern the code and included materials. This documentation update does not
relicense the project, add a blanket “all rights reserved” restriction, or
change the rights already granted by those terms.
