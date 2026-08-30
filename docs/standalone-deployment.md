# Standalone production deployment

This is the active CasAndra Web profile. It runs on a dedicated Ubuntu 24.04
de.NBI VM with 4 vCPUs, approximately 8 GB RAM, and one attached 200-GB ext4
volume. The container and shared-Workbench profiles are not used.

## Storage and immutable inputs

Mount the data volume at `/srv/casandra` and bind its `crispr` directory at
`/srv/crispr`. Persist both mounts in `/etc/fstab`. Before installation, verify:

- `/srv/casandra` is a dedicated mount with at least 20 GB free;
- staged source and wheels are root-owned and not group/world writable;
- offline wheel manifest SHA-256 is
  `c73be92c23c44815d51c961995018dfe796518bf0ace68b05096dd030947d607`;
- scientific release ID is
  `178f45ddd4080e30774d9e92d913a35088e253c24116e7149d6859639278ff42`;
- its verifier prints that same ID with `--require-current`; and
- `/opt/crispr-suite`, `/opt/crispr-workers`, and
  `/etc/crispr-tools/release-manifest.json` resolve into that release.

The installer expects Ubuntu Python 3.12, `python3-venv`, Nginx, OpenSSL,
systemd, and the verified wheelhouse under `/srv/casandra/staging`.

## Install and verify

Use the exact GitHub Pages origin without a path or trailing slash:

```bash
sudo deploy/install-service.sh \
  /srv/casandra/source/SOURCE_SHA256/WebServer \
  https://YOUR-GITHUB-ACCOUNT.github.io
sudo deploy/verify-deployment.sh
```

The first install generates the bearer-token pepper in
`/etc/casandra-web.env`; never print or copy that file. Upgrades preserve the
pepper. The installer installs backend dependencies only from the
checksum-pinned offline wheelhouse; no external build tooling or network access
is used. A standard-library builder reuses only the reviewed wheel's metadata,
checks it against `pyproject.toml`, replaces its payload with the exact
content-addressed `backend/source` tree, regenerates `RECORD`, and installs that
derived wheel. It never installs the reviewed wheel's stale Python payload.
Review changed non-secret policy keys explicitly before restarting.

The verifier checks the entire scientific release, executable and model
identities, equality of every installed `casandra_web` Python source with the
release source, systemd sandboxes, cgroups, exact public policy, service health,
and both loopback listeners. `/casandra/api/v1/version` publishes the full
64-hex `web_release_id`; its first 24 characters are the active backend release
directory name. The active limits are:

| Scope | Limit |
| --- | --- |
| Cas-only nucleotide | 110,000,000 request bytes; 100,000,000 nt; 10,000 records |
| With CRISPR arrays | 4,500,000 request bytes; 2,000,000 nt; 20 records |
| Protein modes | 4,500,000 request bytes; 2,000,000 residues |
| Queue/concurrency | 1 queued; 2 active globally; 1 active per client; 1 worker |
| Retention/storage | 20 jobs; 250,000,000 retained bases; 2 GB/job; 20 GB free floor |
| API | 0.5 CPU; 1.5 GiB hard memory; loopback port 8010 |
| Worker | 3 CPUs/threads; 5 GiB hard memory; no IP networking |
| Edge | Nginx loopback port 8082; PROXY protocol required; one global upload |

## Release gates

Before publication, run the credential-safe four-mode smoke through the local
PROXY-v2 edge. It covers real CasAndra and CRISPRidentify execution,
authorization, CORS, artifacts, exports, cancellation, and result integrity:

```bash
python3 -B deploy/docker/smoke-e2e.py \
  --fasta /path/to/reviewed-non-sensitive.fasta \
  --origin https://YOUR-GITHUB-ACCOUNT.github.io
```

Also submit an exact 100,000,000-nt Cas-only request through Nginx and observe
API/worker `MemoryPeak`, `memory.events`, restarts, disk, and health. The
2026-08-30 acceptance run completed in 72.07 seconds. API and worker peaks were
773,603,328 and 3,371,184,128 bytes, with zero pressure events and restarts.

## Public transport and Pages

Install Tailscale from its signed Ubuntu repository, authenticate this VM, then
publish only the Nginx loopback edge:

```bash
sudo tailscale up --hostname=casandra-web-server --operator=ubuntu
sudo tailscale funnel --bg --yes --proxy-protocol=2 \
  --tls-terminated-tcp=443 tcp://127.0.0.1:8082
tailscale funnel status
```

Do not bind ports 8010 or 8082 to a non-loopback address. Set the GitHub
repository variable `CASANDRA_API_ORIGIN` to the exact Funnel HTTPS origin,
rebuild Pages, and run the public smoke with `--api-origin`.

The active endpoint is
`https://casandra-web-server-1.tail58d78e.ts.net`; the suffix distinguishes it
from the retired node, which remains outside this deployment's authority.

## Operations and rollback

Monitor only counts, sizes, durations, phases, resource use, and failure
classes—never sequences, FASTA headers, bearer capabilities, or result bodies.
Cleanup runs every 30 minutes; do not manually delete unknown jobs.

Backend releases are content-addressed under `/srv/casandra/releases/backend`.
Rollback means repointing `current` to a previously verified release,
reinstalling its reviewed unit/Nginx definitions, restarting API and worker,
then running the full verifier and private smoke again. Preserve the SQLite
queue and attached volume during rollback. Each immutable release owns its
non-secret `release.env`, so the public `web_release_id` follows an atomic
`current` rollback; the separate pepper file is never rewritten.

Pre-v2 releases are not rollback targets: they lack the source/install
attestation and release-owned identity, and the verifier and systemd conditions
reject them. The first v2 upgrade preserves `/etc/casandra-web.env`; retain at
least one subsequently verified v2 release for rollback.
