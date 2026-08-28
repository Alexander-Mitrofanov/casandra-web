# CasAndra Web

CasAndra Web is a queue-backed application for detecting, annotating, and
classifying Cas genes from nucleotide or protein FASTA. CasAndra is the
authoritative Cas caller. CRISPRidentify v2 is an optional, independent source
of CRISPR-array context for complete-genome jobs; coordinate proximity never
changes a Cas call or subtype.

- Live application: <https://alexander-mitrofanov.github.io/casandra-web/>
- Public API health: <https://casandra-web-server.tail58d78e.ts.net/casandra/api/v1/health>
- Source repository: <https://github.com/Alexander-Mitrofanov/casandra-web>

The frontend is a static Vue 3/Vite site for GitHub Pages. The backend is a
FastAPI control plane, SQLite WAL queue, single CPU-only scientific worker,
cleanup service, and dedicated Caddy edge on the same de.NBI VM used by the
reference project. The new deployment does not modify or route through the
existing FASTA or CRISPR containers.

## Four-mode analysis contract

`POST /casandra/api/v1/jobs` accepts one `analysis_mode` and a plain FASTA in
`sequence`. The mode fixes the input alphabet and scientific route:

| `analysis_mode` | Input and fixed behavior | Primary result |
| --- | --- | --- |
| `complete_genome` | One or more nucleotide FASTA records; deterministic `single` gene calling | Detect, annotate, and classify Cas genes and genomic cassettes |
| `annotate_cas_genes` | A potentially large amino-acid FASTA batch; every record is evaluated independently | Exactly one outcome per input record: its Cas family/profile identity (for example `Cas3` or `Cas9`) or the exact label `no cas`; system type/subtype is supplementary |
| `classify_cassette` | One ordered amino-acid FASTA representing one putative cassette | One coordinate-free CRISPR–Cas cassette classification; record order supplies architecture evidence for Type II and Type III systems |
| `metagenomic` | One or more nucleotide FASTA records; each record is processed independently with `meta` gene calling | Per-record Cas gene detection and classification |

`include_crispr_arrays` is optional, defaults to `false`, and is valid only
with `complete_genome`. When true, CRISPRidentify adds array coordinates and
evidence categories as context. It remains independent of CasAndra and does not
confirm, reject, or alter a Cas prediction. Protein modes never invent genomic
coordinates, and metagenomic mode never runs array detection.

Compatibility exception: a pre-1.1 request that omits `analysis_mode` is
treated as the legacy complete-genome contract and defaults array detection to
`true`. New clients must always send `analysis_mode`; for those requests,
omitting `include_crispr_arrays` retains the documented `false` default.

The common progress path is `queued -> casandra -> indexing -> packaging ->
completed`. The scientific phase is presented as finding Cas genes, annotating
proteins, or classifying a cassette according to the mode. A
`crispridentify` phase appears only for `complete_genome` with array detection
requested. Every completed job provides `result-summary.json` and
`casandra-results.zip`. It also provides the complete, schema-versioned
`casandra-results.json`, an RFC-4180 `casandra-results.csv`, and mode-appropriate
FASTA exports. Genome modes provide Cas proteins (`.faa`) and coding DNA
(`.fna`); requested arrays add interval and repeat/spacer FASTA. Protein
annotation provides all submitted proteins and a Cas-only FASTA, while cassette
classification provides the same two scopes in submitted order. These exports
are generated server-side from the validated, untruncated result and are also
included in the ZIP.

The authenticated JSON is also the frontend's lazy interactive-detail source:
every Cas gene, submitted protein, and CRISPR array carries its validated
annotation and sequence contents. Raw sequences remain absent from the bounded,
repeatedly-polled job summary.

Genome modes additionally expose `cas_proteins.tsv`,
`cassettes.tsv`, `casandra.gff3`, and CasAndra run/manifest provenance. Protein
annotation exposes `protein-predictions.jsonl` plus CasAndra run/manifest
provenance. Cassette classification exposes
`protein-predictions.jsonl`, `cassette-classification.json`, and CasAndra
run/manifest provenance. Array artifacts exist only when array detection was
requested.

An arrays-off result is explicit rather than ambiguous:

- `include_crispr_arrays` is `false`;
- the array collection is empty, and genome summaries report a zero array
  count;
- provenance reports array detection as `not_requested`; and
- there is no CRISPRidentify phase or CRISPRidentify artifact.

This differs from a requested CRISPRidentify run that completed successfully
and found no accepted arrays. Live nucleotide and protein record/length limits
are advertised by `GET /casandra/api/v1/config`; clients must use the limits
for the selected input kind rather than assuming nucleotide base limits apply
to amino-acid batches.

The bundled complete-genome showcase uses the full 1,852,433-base
`NC_002737.2` RefSeq record with array detection off. Its captured result and
downloads come from the same worker path as a live run and include an accepted
Type II-A Cas9–Cas1–Cas2 cassette at bases 854,751–860,064.

Type II and Type III cassette subtypes use the packaged ordered-profile
architecture ExtraTrees model. The direct profile result remains in the
scientific output as supporting evidence. The Type II routing addition has a
targeted canonical-locus regression, while aggregate accuracy has not been
re-estimated; the bundle metadata records that boundary explicitly.

The underlying coordinate-free cassette route is also available from the
installed CasAndra CLI:

```bash
casandra classify-cassette \
  --input putative_cas_genes.faa \
  --output cassette_output
```

## Production topology

```text
GitHub Pages
    |
    | HTTPS API requests
    v
Tailscale Funnel :443 (TLS termination + PROXY protocol v2)
    |
    v
127.0.0.1:8082 -> casandra-edge:8080
                         |
                         | casandra-ingress (internal Docker network)
                         v
                    casandra-api:8010
                         |
                         v
             SQLite + private jobs in /srv/casandra/jobs
                         ^
                         |
              network-disabled casandra-worker
                    |                 |
                    v                 v
                 CasAndra      CRISPRidentify v2
```

The edge is dual-homed: only it joins `casandra-edge-host`, which makes the
loopback publication possible. The API joins only the internal
`casandra-ingress` network. Worker and cleanup containers have no network.

See [Architecture](docs/architecture.md) for trust and scientific boundaries
and [Deployment](docs/deployment.md) for the exact Ubuntu 22.04 procedure.

## Layout

- `backend/` — FastAPI, durable queue, worker, output validation, and tests.
- `frontend/` — Vue/Vite submission and Cas-focused visualization.
- `deploy/docker/` — scientific image, Compose services, host preparation,
  credential-safe E2E smoke, and deployment verification.
- `deploy/caddy/` — dedicated unprivileged API edge image.
- `docs/` — architecture and operations documentation.
- `.github/workflows/pages.yml` — frontend test/build and Pages publication.

`deploy/systemd/` and `deploy/nginx/` are retained only as an optional
non-container skeleton. They are not used by the de.NBI deployment.

Only `frontend/dist/` is public. Never publish environment files, submitted
sequence, queue databases, job artifacts, bearer capabilities, or private
logs.

## Local verification

```bash
cd backend
python3.10 -m venv .venv
.venv/bin/pip install -e '.[test]'
.venv/bin/ruff check src tests ../deploy/docker/smoke-e2e.py
.venv/bin/pytest
.venv/bin/pip check

cd ../frontend
npm ci --ignore-scripts
npm test -- --run
npm run build

cd ..
bash -n deploy/docker/*.sh deploy/caddy/*.sh
CASANDRA_WEB_ENV_FILE="$PWD/deploy/docker/casandra-web.env.example" \
  docker compose -f deploy/docker/compose.yml config --quiet
```

## Checked-in production policy

The one-CPU, approximately 2-GiB VM policy permits one scientific worker and
two queued jobs, up to 2 million bases per submission, three submissions per
client per hour, 20 retained jobs/20 million retained input bases, an 8-hour
absolute queue/runtime deadline, and 24-hour terminal retention. Admission
also requires 5 GB and 100,000 inodes free. Each job is capped at 600 MB.

The edge/API/worker/cleanup memory limits are 64/192/950/64 MiB. A real
1.75-Mbase deployment smoke completed within the 950-MiB worker limit. The
legacy loopback CRISPRidentify service is admin-only and must not run analysis
concurrently with the public CasAndra worker on this host.

These are host-survival controls, not scientific limits or an SLA. Anonymous
submission is suitable only for non-sensitive research sequence unless the
operator adds the institutional authentication, encrypted storage, auditing,
and governance required for sensitive data.
