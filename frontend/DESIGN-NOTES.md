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
unavailable for custom submissions; bundled examples remain runnable. Public frontend releases are published by the GitHub Pages workflow; the API
runs separately on the production VM.

## Input workspace and portrait — 14 September 2026

The two analysis panels now stretch to the same top and bottom edges on desktop,
with matching borders, backgrounds, padding and heading styles. Both step markers
are 36px squares with 18px numerals. The primary Run analysis action is at least
60px tall and 228px wide on desktop, and spans the available width on mobile.

File dropping now uses the sequence textbox itself. The empty field explains
that a FASTA file can be dropped or sequence records pasted, and retains a
molecule-specific sample placeholder. Choose FASTA remains available as a native
file picker. File reading, filenames, size limits and input validation are
preserved. Removed the "Find the Cas in your sequence." and "Sequence analysis
workspace" header lines.

A separately assigned design agent created an original classical Greek female
portrait with the built-in image generation tool. The header combines the navy
engraved portrait with a serif CasAndra wordmark. The original transparent image
is `src/assets/casandra-portrait.png` (1254 × 1254; 1,593,965 bytes). The site uses
`src/assets/casandra-portrait.webp` (1,070,388 bytes), a lossless re-encoding with
identical decoded RGBA pixels. No application dependencies were added.

Generation prompt:

> Use case: logo-brand. Asset type: a portrait mark for the header of CasAndra, a scientific sequence analysis website; must be readable when displayed at 80–100 pixels tall. Generate a beautiful original classical Greek woman portrait, Cassandra-inspired, as if illustrated for a fine nineteenth-century encyclopedia. A calm, intelligent young adult woman with an elegant Greek profile, looking slightly to the right in a three-quarter view, wavy hair gathered neatly in a classical low bun and subtle draped chiton at the shoulders. Refined dark blue engraved ink illustration, confident clean contours with restrained hatchwork, sculptural classical form, dignified and scholarly. Delicate facial features but bold readable silhouette. Tightly framed head and upper shoulders, centered, occupying about 85% of the square image, entire silhouette visible, balanced padding. No enclosing circle or border. Single deep navy blue ink close to #12304d with white negative space. Pure white background, no paper texture, colored wash, or shadows outside the portrait. One woman only; original image; no lettering, wordmark, props, symbols, laurel wreath, ornament, decorative border, scene, watermark, photographic skin texture, or gradient. Avoid overly fine hatching that disappears at small size. Produce a polished, clean square raster logo illustration.

Validation: 95 tests across 10 files and the production build passed. Added a
regression covering a FASTA file dropped into the cassette textbox and submitted
with its original filename and record order. Browser checks confirmed matching
panel edges and step positions at desktop and 900px widths; mobile layouts at
390px and 320px had no page overflow. Checked the empty-field prompt after
clearing input, and ran the existing cassette example through Run analysis,
which returned Type II-A.
