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
the checked-in nested-process signal patch before installation.

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
- exact CasAndra/Integration/CRISPRidentify versions and verified model bundle.

## 5. Real private E2E before publication

Use a reviewed non-sensitive FASTA. The smoke never prints bearer tokens and
routes every request through the loopback PROXY-v2 edge:

```bash
WebServer/deploy/docker/smoke-e2e.py \
  --fasta /path/to/non-sensitive-genome.fasta \
  --origin https://YOUR-GITHUB-ACCOUNT.github.io
```

It verifies POST, queue/worker execution, CasAndra schema 5, canonical
CRISPRidentify result validation, complete sequence-free array artifacts,
archive digest/ZIP integrity, exact CORS, wrong-token rejection, and a second
job's cancellation. The production acceptance run used the 1,750,832-base
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
and cancellation checks through the public HTTPS origin. Confirm the frontend
build's CSP contains that exact origin.

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
against the same queue.
