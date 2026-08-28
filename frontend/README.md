# CasAndra web frontend

Vue 3/Vite client for the CasAndra public analysis service. It accepts nucleotide FASTA, submits an asynchronous job, keeps the active credential in tab-scoped session state, polls status, and presents Cas proteins, Cas cassettes, and CRISPRidentify v2 array context on source-forward contigs.

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

The visualization and tables use 1-based, inclusive coordinates on the submitted source record. Minus-strand Cas arrows point left, but the contig is never reverse-complemented in the display. CasAndra cassette evidence and CRISPRidentify v2 array evidence remain distinct; proximity is shown and is not promoted to proof of biological linkage.
