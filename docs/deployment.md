# de.NBI Docker deployment

This is the reviewed deployment path for the existing Ubuntu 22.04 VM (one
CPU, approximately 2 GiB RAM). It derives the scientific image from the pinned
local `crispridentify-v2-backend:bb3e31d` image and the edge from the pinned
local `fasta-web:denbi` image. It does not recreate, reconfigure, or attach to
the existing FASTA containers.

Secrets stay on the host. `prepare-host.sh` generates the only application
secret—a random capability-token pepper—directly into a root-owned mode-0600
environment file. Tailscale and GitHub credentials are never copied into the
repository or images.

## Container and network boundary

The derived scientific image contains independent environments:

```text
/opt/casandra-web/venv  API, queue, worker, cleanup
/opt/casandra/venv      CasAndra production tool and bundled model
/opt/integration/venv   crispr-tools Integration 0.2.6
/opt/crispridentify     inherited CRISPRidentify 2.0.0 runtime
```

Compose creates four UID/GID `10001:10001` containers:

- `casandra-edge`: unprivileged Caddy on port 8080; published only as
  `127.0.0.1:8082`; joins `casandra-edge-host` and `casandra-ingress`.
- `casandra-api`: joins only internal `casandra-ingress` at `172.30.249.3`;
  it has no host port.
- `casandra-worker`: `network_mode: none`, one thread, 950-MiB hard limit.
- `casandra-cleanup`: `network_mode: none`, retention cleanup every 30 minutes.

Every container has a read-only root filesystem, all capabilities dropped,
`no-new-privileges`, and explicit PID/memory/CPU limits. Only edge accepts the
host-edge gateway's PROXY-v2 connection. The API trusts forwarded client
addresses only from edge's fixed internal address.

## Analysis-mode routing

The API accepts exactly four `analysis_mode` values and the worker maps each to
a fixed scientific command:

- `complete_genome`: nucleotide FASTA with deterministic `single` gene calling;
- `annotate_cas_genes`: amino-acid FASTA batch, one independent result per
  record (Cas family/profile identity or exact `no cas`; system type/subtype is
  supplementary);
- `classify_cassette`: one ordered amino-acid FASTA, producing a coordinate-free
  cassette classification; and
- `metagenomic`: nucleotide FASTA records analyzed separately with `meta` gene
  calling.

`include_crispr_arrays` defaults to false and is accepted only for
`complete_genome`. When false, the worker skips Integration/CRISPRidentify and
publishes explicit `not_requested` array provenance with no identify artifacts.
When true, CRISPRidentify runs independently and supplies context only; it does
not alter CasAndra calls. The scientific image still contains the identify
runtime because any accepted complete-genome job may request it.

For compatibility with pre-1.1 clients, a request that omits `analysis_mode`
is translated to the legacy complete-genome route and defaults arrays to true.
Current clients must send `analysis_mode`; their omitted array flag defaults to
false as described above.

## 1. Read-only prerequisites

```bash
docker image inspect crispridentify-v2-backend:bb3e31d >/dev/null
docker image inspect fasta-web:denbi >/dev/null
docker inspect fasta-web --format '{{.State.Running}} {{.HostConfig.NetworkMode}}'
docker inspect fasta-backend --format '{{.State.Running}}'
docker inspect crispridentify-v2-backend --format '{{.State.Running}} {{json .HostConfig.PortBindings}}'
```

The legacy `crispridentify-v2-backend` must remain loopback/admin-only and must
not analyze concurrently with `casandra-worker`.

## 2. Build reviewed local images

The scientific build stages only `WebServer/backend`, the production `tool`
package, and the sibling reference project's `Integration` package. It applies
the checked-in nested-process signal patch before installation. Web-required
CasAndra 0.3 sources are then overwritten from
`deploy/docker/casandra-tool-overlay`, which is tracked in this repository;
the sibling tool still supplies the frozen model bundle and unchanged package
modules. The build records a canonical SHA-256 of that overlay in the image.
Before Docker runs, it also compares every distributable source/model file in
the composed tool tree with `casandra-tool-release.sha256`; this pins the full
post-overlay package and the exact model-bundle manifest without duplicating
the model payload in this repository. Their lock digests are image labels.

```bash
cd /path/to/CasAndraProject

CASANDRA_DOCKER_BUILD_NETWORK=host \
CASANDRA_WEB_IMAGE=casandra-web:local \
  WebServer/deploy/docker/build-image.sh

CASANDRA_EDGE_IMAGE=casandra-edge:local \
  WebServer/deploy/caddy/build-image.sh
```

`CASANDRA_DOCKER_BUILD_NETWORK=host` is needed on this VM because Docker's
build bridge cannot resolve package hosts. It applies only to dependency
installation while building; runtime worker/cleanup networking remains
disabled. A release process should replace live resolution with a
hash-pinned, offline wheelhouse.

The scientific build refuses to pull a different base and records the local
base image ID as an OCI label. The edge strips the base Caddy binary's privileged
port capability because it listens on unprivileged port 8080.

## 3. Prepare root-owned host state

Pass the exact GitHub Pages origin, without a repository path or trailing
slash:

```bash
sudo WebServer/deploy/docker/prepare-host.sh \
  https://YOUR-GITHUB-ACCOUNT.github.io
```

The helper creates:

| Host path | Owner/mode | Purpose |
| --- | --- | --- |
| `/srv/casandra/config/casandra-web.env` | `root:root` `0600` | Policy and generated pepper |
| `/srv/casandra/compose.yml` | `root:root` `0644` | Reviewed Compose definition |
| `/srv/casandra/jobs` | `10001:10001` `0700` | SQLite queue and private jobs |
| `/srv/casandra/tmp` | `10001:10001` `0700` | Worker temporary files |

It does not start containers and does not overwrite an existing environment
file. Review policy keys without printing the pepper. Because the environment
file is root-readable, run production Compose commands through `sudo`.

## 4. Start and verify the private deployment

```bash
sudo docker compose -f /srv/casandra/compose.yml config --quiet
sudo docker compose -f /srv/casandra/compose.yml up -d

sudo CASANDRA_COMPOSE_FILE=/srv/casandra/compose.yml \
  /path/to/CasAndraProject/WebServer/deploy/docker/verify-docker.sh
```

The verifier fails closed unless it confirms:

- exact edge/API addresses and loopback publication;
- internal-only API and network-disabled worker/cleanup;
- service UID, read-only roots, dropped privilege, PID/memory/CPU limits;
- a common scientific image ID for API/worker/cleanup;
- exact PROXY-v2 health through Caddy;
- healthy database and worker heartbeat;
- readable identify-only runner configuration with disabled stages pinned to
  `/usr/bin/false`;
- importable CRISPRidentify source and loadable native matcher as UID 10001;
- exact CasAndra/Integration/CRISPRidentify versions and verified model bundle;
- exact equality between this checkout's tracked CasAndra overlay digest and
  the digest label on the running scientific image;
- exact equality for the pinned full-tool release manifest and model-bundle
  manifest labels.

## 5. Real private E2E before publication

Use a reviewed non-sensitive FASTA. The smoke never prints bearer tokens and
routes every request through the loopback PROXY-v2 edge:

```bash
WebServer/deploy/docker/smoke-e2e.py \
  --fasta /path/to/non-sensitive-genome.fasta \
  --origin https://YOUR-GITHUB-ACCOUNT.github.io
```

The required local smoke exercises all four real worker/CLI routes. It verifies
complete-genome schema 5 and canonical CRISPRidentify output; literal ordered
Cas-family/`no cas` annotation rows; ordered, coordinate-free cassette results;
separate metagenomic sequence summaries; each mode's provenance and artifacts;
complete authenticated JSON/CSV/FASTA exports, interactive feature sequence
contents and cross-format row counts; archive integrity, exact CORS,
wrong-token rejection, and cancellation. It uses
distinct documentation-range PROXY source addresses so the ordinary per-client
submission limit remains active. `--api-origin` verifies public transport for
the complete-genome route only and does not replace this local four-mode gate.
The production acceptance run used the 1,750,832-base
`NC_017040.1` example and returned 48 Cas proteins, 4 cassettes, and 2 accepted
arrays. Peak worker use remained below the 950-MiB ceiling.

Smoke jobs are ordinary private jobs and count toward rate/storage limits.
Allow retention cleanup to remove them, or expire only the exact operator-owned
smoke job IDs and invoke `casandra-web-cleanup`. Never purge unknown jobs.

## 6. Enable the stable HTTPS edge

Install/login Tailscale once, then enable Funnel only after confirming the
tailnet policy and public hostname:

```bash
sudo tailscale up --hostname=casandra-web --operator=ubuntu
sudo tailscale funnel --bg --proxy-protocol=2 \
  --tls-terminated-tcp=443 tcp://127.0.0.1:8082
tailscale funnel status
```

Funnel terminates public TLS and sends PROXY protocol v2 so rate limits use the
real client address. Caddy accepts PROXY frames only from the dedicated
`casandra-edge-host` gateway. Do not expose port 8082 on a non-loopback host
address, and do not reuse the anonymous localhost.run tunnel used by the
reference service.

## 7. Publish GitHub Pages

Create a public repository containing this `WebServer` tree and push `main`.
In repository settings:

1. select GitHub Actions as the Pages source;
2. set repository variable `CASANDRA_API_ORIGIN` to the exact Tailscale Funnel
   HTTPS origin, without a path;
3. optionally set `PAGES_BASE_PATH`; otherwise the workflow uses
   `/<repository-name>/`.

The workflow tests and builds only `frontend/`. The API origin is public build
configuration, not a credential. Browser requests use `/casandra/api/v1`.

After Pages deploys, repeat health, CORS, wrong-token, completed-job artifact,
and cancellation checks through the public HTTPS origin:

```bash
WebServer/deploy/docker/smoke-e2e.py \
  --api-origin https://casandra-web.YOUR-TAILNET.ts.net \
  --fasta /path/to/non-sensitive-genome.fasta \
  --origin https://YOUR-GITHUB-ACCOUNT.github.io
```

Confirm the frontend build's CSP contains that exact origin.

Before promoting a release that changes mode routing, also submit reviewed,
non-sensitive fixtures for the other contracts and confirm:

- protein annotation returns one result for every FASTA record, including exact
  `no cas` negatives;
- cassette classification preserves the submitted record order and publishes
  no nucleotide coordinates; and
- metagenomic output is partitioned by submitted nucleotide record, reports
  `meta` gene-calling provenance, and contains no array phase or artifacts.

These checks use the normal API and job artifact downloads; they do not require
enabling the legacy CRISPRidentify container.

## Capacity and coexistence

Production policy is:

- 2,000,000 bases/request, 20 records, 4.5-MB JSON body;
- one worker, two queued jobs, three global active jobs, one active job/client;
- three submissions/client/hour, persisted even after cancellation;
- 20 retained jobs and 20,000,000 retained input bases;
- admission floor of 5 GB free and 100,000 free inodes;
- 600 MB/job, 8-hour queue/runtime deadline, 24-hour terminal retention;
- edge/API/worker/cleanup hard memory limits of 64/192/950/64 MiB;
- one aggregate CPU across the four services.

The live `/casandra/api/v1/config` response also advertises separate total,
per-record, and record-count limits for nucleotide and amino-acid FASTA. Keep
the frontend and external clients bound to those advertised values. Do not
reuse the nucleotide base cap as an implicit protein-batch cap or raise either
class of limit without measuring the corresponding worker and storage cost.

Do not increase worker concurrency on this VM. Do not overlap an administrative
run in the legacy CRISPRidentify container with a public CasAndra job. If host
memory or disk headroom falls below policy, stop accepting jobs rather than
raising limits.

## Updates and rollback

Build a new reviewed tag, inspect it, render Compose with that exact tag, and
recreate only the CasAndra project. Preserve the prior image for rollback.
Take a private SQLite online backup before a future schema-changing release;
do not routinely back up job trees because that extends submitted-sequence
retention.

The optional systemd/Nginx files must not run alongside this Compose project
against the same queue. Native deployments enable scientific-runtime preflight
and pin the same CasAndra, Integration, and CRISPRidentify versions (including
the CRISPRidentify `VERSION` attestation); `verify-deployment.sh` checks those
versions before accepting the service as reviewed.
