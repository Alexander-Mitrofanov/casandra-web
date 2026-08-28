# CasAndra Web

CasAndra Web is a queue-backed application for identifying and visualizing Cas
genes and Cas cassettes. CasAndra is the authoritative Cas caller.
CRISPRidentify v2 runs independently and contributes validated CRISPR-array
landmarks; coordinate proximity never changes a Cas call or subtype.

- Live application: <https://alexander-mitrofanov.github.io/casandra-web/>
- Public API health: <https://casandra-web-server.tail58d78e.ts.net/casandra/api/v1/health>
- Source repository: <https://github.com/Alexander-Mitrofanov/casandra-web>

The frontend is a static Vue 3/Vite site for GitHub Pages. The backend is a
FastAPI control plane, SQLite WAL queue, single CPU-only scientific worker,
cleanup service, and dedicated Caddy edge on the same de.NBI VM used by the
reference project. The new deployment does not modify or route through the
existing FASTA or CRISPR containers.

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
