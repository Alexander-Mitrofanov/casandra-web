# Large-input capacity validation

This is a host-capacity check, not a scientific benchmark. It uses a synthetic,
deterministic FASTA and the normal ASGI admission and web-worker paths. No
publication sequence is used.

## Reproduce

Install the backend with test dependencies, then run each measured stage as a
separate process from the `WebServer` root:

```bash
probe_root=$(mktemp -d /tmp/casandra-capacity-probe.XXXXXX)

/usr/bin/time -v backend/.venv/bin/python -B scripts/capacity-probe.py generate \
  --output "$probe_root/synthetic-100m.fna"

/usr/bin/time -v backend/.venv/bin/python -B scripts/capacity-probe.py admission \
  --fasta "$probe_root/synthetic-100m.fna" \
  --data-root "$probe_root/admission" \
  --worker-cpu 12

/usr/bin/time -v backend/.venv/bin/python -B scripts/capacity-probe.py prepare-worker \
  --fasta "$probe_root/synthetic-100m.fna" \
  --data-root "$probe_root/worker" \
  --worker-cpu 12

/usr/bin/time -v backend/.venv/bin/python -B scripts/capacity-probe.py run-worker \
  --data-root "$probe_root/worker" \
  --worker-cpu 12
```

The helper refuses to overwrite the fixture or reuse a data root. Keep the
temporary directory until its JSON output and worker artifacts have been
reviewed; removal is an explicit operator action.

## Bound result

Pre-deployment run on 2026-08-30:

| Check | Result |
| --- | --- |
| Fixture | 1,000 records; 100,000 bases/record; 100,000,000 bases total |
| Fixture file | 101,264,893 bytes; SHA-256 `a5f7158974b4d7eb0e34b1de9e52840bb2a83cc68388732c725921bc01ec8622` |
| Compact request | 102,516,004 JSON bytes; arrays explicitly false |
| ASGI admission | HTTP 202; 2.91 s wall; 861,608 KiB maximum RSS |
| Web worker | completed; 12 configured threads; 38.43 s wall; 3,282,956 KiB maximum RSS |
| Private job tree | 355,502,353 bytes |
| Deployed web canary | completed through Nginx with 3 worker threads; 5.96 s submission; 72.07 s to terminal |
| Deployed cgroup peaks | API 773,603,328 bytes; worker 3,371,184,128 bytes; zero memory-pressure events/restarts |

The ASGI measurement intentionally includes an in-process HTTP client, JSON
decode, validation, normalization, queue admission, and input persistence. GNU
`time -v` reports maximum RSS for the measured process/child path; it is not a
cgroup aggregate. Deployment acceptance repeated the exact fixture through the
real 1.5-GiB API and 5-GiB worker cgroups and observed `memory.peak`, memory
events, disk, deadline, and service health. The 110,000,000-byte edge/API
ceiling applies to all JSON transport because mode selection is inside the
body; option-aware validation then enforces 4,500,000 sequence bytes for array
and protein jobs.
