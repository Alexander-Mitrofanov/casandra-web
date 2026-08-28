# Architecture and scientific contract

## Trust boundaries

The GitHub Pages client is untrusted static code from the API's perspective and
contains no service-wide credential. Tailscale Funnel terminates public TLS and
forwards PROXY protocol v2 to loopback port 8082. The dedicated unprivileged
Caddy edge accepts that protocol only from its host-edge gateway and routes
only `/casandra/api/*` to the API.

Docker networks deliberately separate roles:

```text
casandra-edge-host (bridge)    edge only; enables 127.0.0.1:8082 publication
casandra-ingress (internal)    edge 172.30.249.2 -> API 172.30.249.3
network_mode: none             worker and cleanup
```

FastAPI validates bounded JSON/FASTA input, creates private job storage, and
updates SQLite. It never starts a scientific command. The worker claims one
durable lease at a time and invokes only fixed image-owned command arrays.
Request data cannot select a binary, model, runner configuration, path, thread
count, or arbitrary argument.

| Resource | Ownership/purpose |
| --- | --- |
| `crispridentify-v2-backend:bb3e31d` | Pinned local CRISPRidentify base image |
| `casandra-web:<release>` | Backend, CasAndra, patched Integration, inherited CRISPRidentify |
| `casandra-edge:<release>` | Dedicated PROXY-v2 Caddy route only |
| `/srv/casandra/jobs` | UID/GID 10001, mode 0700 queue and private job trees |
| `/srv/casandra/tmp` | UID/GID 10001, mode 0700 worker temporary space |
| `/srv/casandra/config/casandra-web.env` | root:root mode 0600 policy and token pepper |

API, worker, and cleanup share numeric identity 10001 because they share the
queue. They do not share storage or identity with the existing FASTA service.
All four new containers have read-only roots, dropped capabilities,
`no-new-privileges`, and explicit cgroup limits.

## Capability authorization and privacy

Job creation returns a random bearer capability once. The random 128-bit job ID
is only a locator. The server stores a keyed digest using an installation-local
random pepper; plaintext capabilities never enter SQLite. Tokens are accepted
by the API only in the `Authorization` header. For explicit browser recovery,
the static client may place a job-specific capability in a `#recover=` URL
fragment. Fragments are not transmitted in HTTP requests or referrer headers;
the client validates and immediately scrubs the fragment, then keeps the active
credential in tab-scoped `sessionStorage` for reloads. Capabilities must never
appear in URL paths or queries, server logs, analytics, Pages configuration, or
support messages. Anyone holding a private analysis link has access to that job
until the backend expires it.

Input is duplicated only into the normalized combined FASTA and bounded
per-record files needed by the two tools. Admission occurs before materializing
the job tree and is rechecked atomically when the queue record is created.
Persistent per-client submission events prevent cancellation from bypassing
the rate limit. Terminal data is deleted after retention; queued/running jobs
also have an absolute deadline.

## Job lifecycle

```text
queued -> running/casandra -> running/crispridentify
       -> running/indexing -> running/packaging -> completed
       -> cancelled | failed

completed | cancelled | failed -> expired -> deleted
```

SQLite transactions guard claim, lease, cancellation, and publication.
Graceful worker shutdown returns the job to the queue without consuming an
attempt. Each attempt uses a unique output directory. Completion and artifact
registration are one transaction with `cancel_requested=0`, so cancellation
cannot lose a final publication race.

Scientific subprocesses run in their own process group. Cancellation, timeout,
lease loss, or shutdown sends TERM and then bounded KILL to the entire tree.
The patched Integration wrapper also forwards termination to its nested tool
process group. Partial output is never published.

Zero Cas calls or zero accepted arrays is a successful biological no-result,
not a worker failure.

## Scientific pipeline

One normalized nucleotide FASTA is the source of truth:

1. CasAndra performs Pyrodigal gene calling, per-gene translation, Cas protein
   inference, and cassette classification.
2. CRISPRidentify 2.0.0 detects arrays independently through the patched
   Integration runner.
3. The indexer validates both result families against the submitted records.
4. A sequence-free projection joins features only by contig and source-forward
   coordinates.

Only the production `casandra` package is deployed. Training, benchmarking,
comparators, and research data remain outside the image. Model inspection must
report verified integrity, CPU-only inference, and offline operation before the
worker enters its loop.

### CasAndra validation

The indexer requires output schema 4 or 5 with a matching manifest, submitted
FASTA digest, safe manifest paths, exact file sizes/digests, and reconciled run
counts. Each gene must report Pyrodigal, requested/selected mode, caller
version, per-gene translation table/policy, valid coordinates, and boolean
5-prime/3-prime partial flags. Cassette protein references and evidence-gate
provenance are fail-closed.

CasAndra is authoritative for Cas proteins, cassette boundaries, and
class/type/subtype. Its margins, profile scores, and cassette confidence values
are evidence scores, not calibrated probabilities.

### CRISPRidentify validation

Each FASTA record must produce exactly one canonical report 1.1.0 whose source
ID, length, uppercase-sequence digest, coordinate convention, source
reconstruction status, validation counts, category counts, array IDs,
intervals, strand, repeat/spacer counts, and finite score values reconcile.
Only `Bona-fide` and `Possible` arrays enter the overlay.

Array category is the primary detector result; raw certainty/model score is not
a calibrated probability. A nearby array is only coordinate co-location. It
never changes or confirms a Cas call.

All accepted arrays participate in overview counts and nearest-array distance.
The interactive API projection is capped at 2,000 arrays, with an explicit
truncation flag. `crispr-arrays.json` preserves the complete sequence-free set;
no consensus repeats or spacers appear in the public projection.

## Coordinate and interpretation rules

- Coordinates are 1-based, end-inclusive, and relative to the submitted
  forward record; strand is separate.
- Minus-strand features do not reverse the visualization axis.
- Coordinates are never inferred from display IDs or filenames.
- Partial 5-prime/3-prime gene flags are exposed for boundary review.
- Fragmented contigs can split systems; divergent Cas proteins can be missed.
- Absence of a prediction is not proof of biological absence.
- Gene mode and genetic code are reported provenance, not universal biological
  assumptions.
- Circular-origin adjacency is not repaired by this release.

## Resource and admission model

The target has one CPU and about 2 GiB RAM. Edge/API/worker/cleanup hard limits
are 64/192/950/64 MiB, and CPU quotas sum to one. The worker runs one job and
one scientific thread. A monitored 1,750,832-base E2E peaked below 950 MiB and
completed; the old 800-MiB limit produced a confirmed container-local OOM.

The API admits at most two queued/three globally active jobs, one active job per
client, three submissions per client per hour, 20 retained jobs, 20 million
retained bases, and 600 MB per job. It refuses admission below 5 GB or 100,000
free inodes. Queue/runtime lifetime is eight hours and terminal retention is 24
hours.

The existing loopback CRISPRidentify container is intentionally not routed by
the new edge. It is admin-only and must not run analysis concurrently with the
public worker. Production metrics may include counts, sizes, timing, phase, and
failure class, but never sequence, FASTA headers, capabilities, result bodies,
or source filesystem paths.
