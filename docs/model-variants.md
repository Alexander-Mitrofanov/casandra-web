# Separately named deployment models

The server supports an operator-owned registry of immutable model bundles.
`CASANDRA_WEB_MODEL_NAME=default` keeps the packaged model and its existing
identity pins. Selecting a registered name sets both the CLI `--model` path and
the public identity shown by `/casandra/api/v1/version`. All four analysis modes
use that bundle. Completed outputs must match its ID, manifest hash, runtime
version, role and result schema before publication.

The first optional bundle is **`casandra-kira-2026-09-15-full-v1`**: 361 HMMs,
45,645 eligible reference proteins, and a cassette estimator refitted on 717
usable cassettes. It retains the 341 original profile identities and adds 20
versioned profiles from Kira's update. Supplemental profiles provide family
evidence; uncertain type/subtype labels are withheld. Existing hard-negative
profiles remain part of detection.

This is a full-data deployment refit after evaluation. It includes the former
train, validation and test partitions and is unsuitable for estimating accuracy
on those holdouts. The separate extension experiments remain the evidence for
benefit; refitting does not establish improved Cas12/Cas13 or cassette accuracy.

## Install and register on the standalone server

First install a backend release containing this feature and the updated systemd
units through the normal [deployment procedure](standalone-deployment.md).
The optional selection file is read after the base environment by API, worker
and cleanup services. Keep the scientific runtime at `casandra 0.3.0.dev0`
with `scikit-learn==1.8.0`.

Copy the trusted bundle archive to the server and verify its SHA-256:

```text
777a85a75ea8f6d24aff33f4855080458f284c3952d76fe2a4106538be98813f
```

Extract it under `/srv/casandra/models/` so its `manifest.json` resides at
`/srv/casandra/models/casandra-kira-2026-09-15-full-v1/manifest.json`.
The manifest pin is:

```text
4e527cf17c56b9967a6e1c7664238196df9a0c0da76b9d7f7f99c55cc9a9ec41
```

Keep the bundle and registry owned by the operator and readable by
`casandrasvc`, outside the writable jobs directory. Register the installed path:

```bash
sudo /srv/casandra/releases/backend/current/venv/bin/python -I -B \
  -m casandra_web.model_registry \
  --registry /srv/casandra/models/registry.json \
  --name casandra-kira-2026-09-15-full-v1 \
  --bundle /srv/casandra/models/casandra-kira-2026-09-15-full-v1 \
  --program-version 0.3.0.dev0 --result-schema-version 5
```

Registration checks every manifest-listed artifact without deserializing the
estimator. Re-registering the same entry is harmless; a name cannot be rebound
to a different bundle. Public runtime schema **5** describes genome output;
protein/cassette command artifacts use their own schema **1**, and the bundle
manifest uses schema **4**. Registration alone does not activate the model.

## Switch or roll back

After installing the updated backend and systemd units, run
`sudo systemctl daemon-reload`. From the deployed checkout, switch with:

```bash
sudo ./deploy/switch-model.sh casandra-kira-2026-09-15-full-v1 \
  --registry /srv/casandra/models/registry.json
```

Roll back with:

```bash
sudo ./deploy/switch-model.sh default
```

The command checks the candidate as `casandrasvc` before changing anything. It
then stops the API, lets queued/running jobs finish with the previous model,
stops the idle worker, atomically updates `/etc/casandra-web-model.env`, and
starts the worker and API with the same selection. It waits for a fresh worker
heartbeat and a healthy API. Startup failure triggers restoration of the prior
selection and services. A drain timeout leaves the worker and selection intact
and reopens the API; the default timeout is four hours and can be changed with
`--drain-timeout SECONDS`. `--check` only validates the candidate.

The API is temporarily unavailable during draining and restart, so users may
briefly see their existing retry/offline state. Jobs, access tokens, cancellation
flags, retry counts, completed results, and retention state remain in the same
database. The switch never edits or clears the queue. Completed jobs retain
their original provenance. Concurrent switch commands are prevented by a lock.
Run `sudo ./deploy/verify-deployment.sh` afterward to verify the deployment.

There is **no model selector or trained-model label in the user interface**.
The API rejects model-selection fields supplied by clients. Technical result
downloads and the machine-readable version endpoint retain model identity for
reproducibility; the feature inspector displays biological evidence without a
model identifier. Queue, polling, cancellation, export and cleanup code do not
depend on the model's name.

For local execution, set the same two environment variables on both processes,
using an absolute registry path appropriate to that machine. The registry stores
absolute bundle paths, so register again after moving a bundle to another host.
Never expose registry names, bundle paths or executable selection as upload or
job-request fields.

## Active deployment and examples

The dedicated production server selected `casandra-kira-2026-09-15-full-v1` on
2026-09-15. Backend release:
`b13e74bada02557f7cfd294ef8666c96f48ce45a2f0ced17711a7ec7d6509ce7`.
The previous packaged model remains available as `default`.

All four bundled examples were recomputed through the public API using their
unchanged input files. Their IDs, input hashes and deployed model pin are recorded
in `frontend/public/examples/capture-manifest.json`. To refresh them, capture to
a staging directory with `scripts/capture-example-results.py`, supplying both
`--expected-bundle-id` and `--expected-manifest-sha256`. The capture rejects a
different server/job model or an artifact whose checksum or size does not match.
Run the frontend tests with `CASANDRA_EXAMPLE_ROOT=/absolute/staging/examples`
before replacing the bundled files. Update the capture manifest with the new
job IDs and input hashes, then publish the tested frontend through Pages.
