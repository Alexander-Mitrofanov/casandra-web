# Example UI audit — 20 September 2026

Checked the published cap15 interface with real Chrome at 320, 390, 768 and
1440 CSS pixels. All four examples were exercised at every width.

## Fixed

- **Example loading race:** with valid input already present, Run analysis could
  submit that previous input while the new example was still loading. Submission
  now waits for the example fetch, including direct form/keyboard submission.
- **Mobile download overflow:** opening raw evidence expanded the 390px page to
  401px. Filenames now wrap within their cards, with the download action below
  the filename on narrow screens.
- **Feature panel spacing:** specificity notes and disclosures now align with
  the panel's padding. Accepted calls no longer display the withheld-call notice.
- **Evidence readability:** shortened generated IDs, formatted coordinates,
  keyboard-scrollable tables and responsive pagination. Full IDs remain in each
  evidence disclosure. Replacing a result resets its pagination.
- **Navigation:** the specificity section is directly reachable; phone navigation
  stays compact and anchor targets remain below the sticky navigation.

## Verification

- 117 frontend tests and the production build passed.
- Every example's filters, selections, map controls, pagination, evidence
  disclosures and section links passed real-browser checks.
- All 63 example files downloaded through the UI and matched their SHA256 values.
- All 16 mode/viewport combinations passed without horizontal page overflow,
  including expanded raw downloads and evidence details.
- Delayed example loading was reproduced with the attempted request intercepted;
  the corrected path submitted no job and displayed the new cached result.
- The public backend remained healthy with runtime `0.3.0.dev2` and the cap15 pin.

This change affects presentation and submission readiness. Scientific outputs
and precomputed artifact bytes are unchanged. Local screenshots, scripts and
receipts are in `releases/cap15-ui-audit-2026-09-20/` (excluded from Git). The local
layout harness supplies health/config responses; the published-site checks use
the real API.
