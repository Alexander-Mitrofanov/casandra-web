# CasAndra frontend refresh — 6 September 2026

The interface now uses a compact research workspace: analysis choices beside
FASTA input on desktop, a single-column flow on mobile, and a consistent blue
and cyan palette across submission, progress, results, inspectors and exports.
Typography, input instructions, focus indicators, table row separation, numeric
alignment and control spacing were revised. Scientific type colors, coordinate
semantics, exact tables, downloadable result contents and API contracts remain
intact. Long method identifiers have readable summary labels; exact identifiers
remain available in the tables. Sequence previews use light backgrounds,
SHA-256 labels are omitted from the interface, and download format labels sit
below their icons with dedicated spacing.

The genome viewer now exposes Focus selection and zoom buttons alongside the
existing Shift + scroll gesture. Focusing a selection fits its inclusive interval
with surrounding context, clamps to source boundaries and retains the 200-base
minimum window. The full-view control restores the complete source record.

## Guidance and skills

Read the official [Astra model guidance](https://developers.openai.com/api/docs/guides/latest-model)
and [OpenAI frontend guidance](https://developers.openai.com/api/docs/guides/frontend-prompt).
Used the [W3C target-size guidance](https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum.html)
and [focus visibility guidance](https://www.w3.org/WAI/WCAG22/Understanding/focus-not-obscured-minimum.html)
to inform controls and navigation. This is not a full WCAG conformance audit.

Installed the frontend-design and webapp-testing skills from anthropics/skills,
and Playwright from openai/skills. Applied their design and browser inspection
workflows. The Playwright CLI could not resolve the npm registry in the sandbox;
browser verification used the available Codex browser with Playwright locators.
No application dependencies were added.

## Verification

- Existing frontend suite plus the new real-fixture focus/zoom regression:
  **94 tests passed across 10 files**.
- Production build: `npm run build` passed. The full-genome example also
  completed in the production preview, with no browser console errors.
- Browser checks used the existing public inputs and captured worker outputs:
  - Complete genome: NC_002737.2, 1,852,433 bases; 55 Cas proteins, four
    cassettes; selected Type II-A at 854,751–860,064 and focused its neighborhood.
  - Protein annotation: five proteins, three Cas calls and two no-cas calls;
    the no-cas filter showed two proteins.
  - Ordered cassette: four proteins, three Cas genes, classification II-A.
  - Metagenomic: two source records, ten Cas proteins and two cassettes;
    changing to the Type I-C record showed seven genes and one cassette.
- Example JSON download emitted the browser download event without a displayed
  download error. Existing tests cover JSON/CSV/FASTA payload handling.
- Visually inspected desktop and mobile input/results; checked page reflow at
  390px and 320px. Maps and exact tables retain their own horizontal scrolling.
- Preserved reduced-motion and forced-color styles; native controls and feature
  keyboard interactions remain in use.

These checks exercise captured reference results, not a fresh scientific worker
run. The local frontend is not connected to a running API and displays Service
unavailable for custom submissions; bundled examples remain runnable. This refresh has not been deployed to the live service.
