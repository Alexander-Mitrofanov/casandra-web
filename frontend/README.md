# CasAndra web frontend

Vue 3/Vite client for the CasAndra public analysis service. It accepts
nucleotide or amino-acid FASTA according to the selected analysis mode, submits
an asynchronous job, keeps the active credential in tab-scoped session state,
polls status, and presents mode-specific results and checksummed artifacts.

## Analysis modes

| UI choice / API value | Input | Result |
| --- | --- | --- |
| Global analysis / `complete_genome` | Nucleotide FASTA; one or more complete-genome records | Detect, annotate, and classify Cas genes with fixed `single` gene calling |
| Annotate Cas genes / `annotate_cas_genes` | Amino-acid FASTA; potentially many protein records | Every record is shown independently by its Cas family/profile identity (for example `Cas3` or `Cas9`), or exact `no cas`; system class/type/subtype is supplementary |
| Classify cassette / `classify_cassette` | One ordered amino-acid FASTA representing one putative cassette | One coordinate-free CRISPR–Cas classification; input order is material, especially for Type III |
| Metagenomic analysis / `metagenomic` | Nucleotide FASTA; one or more metagenomic records | Cas genes detected separately per record with fixed `meta` gene calling |

Global analysis includes an optional “complement the analysis with CRISPR array
detection” control. It is off by default and is not offered for the
other modes. The question-mark help beside Global analysis describes CasAndra;
the help beside the array option describes CRISPRidentify as an independent
context detector. Array proximity never changes or confirms a CasAndra call.

The client sends `analysis_mode`, `sequence`, `filename`, and
`include_crispr_arrays`. It reads live nucleotide and protein count/length caps
from `/casandra/api/v1/config`, validates the alphabet for the selected mode,
and clears the array flag when the user leaves complete-genome mode.

## Local development

```bash
npm install
npm run dev
npm test
npm run build
```

Copy `.env.example` to an untracked environment file when needed:

- `VITE_API_BASE_URL` is the exact HTTPS API origin, without a path. An empty value uses the page origin.
- `VITE_BASE_PATH` is the GitHub Pages project path, such as `/casandra/`.

Every API request is rooted at `/casandra/api/v1`. A production build emits a restrictive Content Security Policy whose `connect-src` contains only the page origin and the configured API origin.

## Browser-side security and recovery

API requests use the access token only in the `Authorization: Bearer` header. After submission, the client can create a private analysis link whose job ID and capability appear only in the URL fragment (`#recover=...`), never in its path or query. Browsers do not transmit fragments in HTTP requests or referrer headers. When the link is opened, the client validates it, immediately removes the fragment from the address bar with `history.replaceState`, and retains the credential in `sessionStorage` for same-tab reloads. Leaving the analysis, an expired/unauthorized response, or an invalid stored credential clears that session state. The application does not send the capability to analytics or logs, but anyone holding the private link can access the job while it remains available.

Artifact URLs supplied in job metadata are not followed; downloads are reconstructed from the fixed API route and artifact ID. The static page also fails closed when embedded in another site’s frame, which supplements controls unavailable as GitHub Pages response headers.

The frontend is suitable only for non-sensitive research sequence. TLS and the bearer token do not hide sequence from the service operator. Retention, authorization, storage isolation, and deletion must also be enforced by the backend.

## Result semantics

Complete-genome and metagenomic visualizations and tables use 1-based,
inclusive coordinates on the submitted source record. Minus-strand Cas arrows
point left, but the contig is never reverse-complemented in the display.
Metagenomic records remain separate. Protein annotation and cassette
classification are coordinate-free; the latter preserves FASTA record order as
scientific evidence rather than inventing positions.

Every completed mode exposes `result-summary.json`, mode-native downloads, and
the checksummed `casandra-results.zip`. A shared result workbench renders
strand-aware genomic features for complete-genome and metagenomic modes, an
ordered score landscape for protein annotation, and a coordinate-free protein
architecture for cassette classification. Every plotted Cas gene, protein,
cassette, and CRISPR array is pointer- and keyboard-selectable. Selection opens
an inline inspector with exact annotations and available protein, coding-DNA,
source-forward, repeat, and spacer sequences, plus per-feature JSON and FASTA.

The inspector securely loads `casandra-results.json` through the authenticated
artifact endpoint; the access token is never placed in a URL. The same complete
validated result is downloadable as JSON or RFC-4180 CSV. Mode-specific FASTA
choices include all/Cas-only proteins for protein modes, Cas protein/coding DNA
for genome modes, and CRISPR array/components when arrays exist. Native reports,
manifests, TSV/GFF3 files, and the ZIP remain available under Technical
artifacts.

Protein annotation also adds
`protein-predictions.jsonl` plus CasAndra run/manifest provenance; cassette
classification adds that file and
`cassette-classification.json`; genome modes add coordinate-bearing TSV/GFF3
and CasAndra provenance downloads. The progress display uses `queued`, a
mode-specific CasAndra step, `indexing`, `packaging`, and completion. A
CRISPRidentify step and CRISPRidentify downloads appear only for a
complete-genome job that requested array detection.

When arrays were not requested, the UI treats the empty collection (and the
zero count in genome summaries) as the explicit `not_requested` state, not as a
detector result. When arrays were requested, CasAndra cassette evidence and
CRISPRidentify v2 array evidence remain distinct; proximity is shown and is not
promoted to proof of biological linkage. A requested detector run with zero
accepted arrays is a successful no-result and is distinguishable from arrays
being off.
