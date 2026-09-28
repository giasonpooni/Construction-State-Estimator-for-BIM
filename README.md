# State Estimator for BIM

**A portable, BIM-specific evidence-to-decision runtime.**

[Portfolio](https://notation.systems) · [Quickstart](#quickstart) ·
[Technical reference](TECHNICAL_REFERENCE.md) · [Documentation](docs) ·
[Copyright and licence](#copyright-and-attribution)

Construction State Estimator (CSE) connects IFC design intent with physical
evidence and an inspectable belief about the built state. Missing or inadequate
evidence remains explicit; a software disposition is not construction approval.

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
| Role | BIM-specific estimation and evidence-to-decision instrument; portfolio category: **Research**, with engineering-simulation applications. |
| Author's work | System design, state representation, evidence handling, disposition logic, implementation and validation workflows. |
| Technology | Python and NumPy, with the documented optional IFC/OpenUSD and native integrations. |
| Runtime identity | **Construction State Estimator / CSE**, distribution **`gat-bim`**, import and command identity **`gat`**. |
| Status | Experimental software with declared assumptions and demonstration fixtures. |

## Place in the workflow

NET is the surrounding investigation workbench; CSE retains its BIM semantics
and model assumptions. GSC may present explicitly supplied representations,
while the portfolio explains the work and links to its source.

The estimation pattern can inform other simulation projects, but this repository
is not relabelled as a generic rover estimator or NPC perception library. It is
not a learned model, a Revit replacement, a general finite-element solver or a
construction-approval authority. Demonstration fixtures are not field evidence.

## Quickstart

Use the setup and runnable examples in
[TECHNICAL_REFERENCE.md](TECHNICAL_REFERENCE.md). The existing `gat` imports,
commands, optional-dependency boundaries and fail-closed contracts are unchanged.

## Technical reference

The complete previous README is preserved **verbatim** in
[TECHNICAL_REFERENCE.md](TECHNICAL_REFERENCE.md), retaining installation,
headless-request examples, workflow guidance and limitations. It remains at
the repository root so relative links retain their original base.

[NET](https://github.com/giasonpooni/Notations-Engineering-Terminal) and the
[Geospatial Systems Compiler](https://github.com/giasonpooni/Geospatial-Systems-Compiler)
are related projects, not prerequisites for every standalone CSE workflow.

## Copyright and attribution

**© 2026 Giason Pooni, for original contributions.** Notation Systems is the
independent project umbrella, not a claim of ownership over third-party tools
or inherited code. Contributor and upstream copyright notices remain in force.

The existing [LICENSE](LICENSE), source notices and third-party terms continue
to govern the code and included materials. This documentation update does not
relicense the project, add a blanket “all rights reserved” restriction, or
change the rights already granted by those terms.
