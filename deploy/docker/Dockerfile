# syntax=docker/dockerfile:1
ARG BASE_IMAGE=crispridentify-v2-backend:bb3e31d

FROM ${BASE_IMAGE} AS builder

USER root
COPY backend /build/backend
COPY casandra-tool /build/casandra-tool
COPY integration /build/integration

RUN /usr/local/bin/python -m venv /opt/casandra-web/venv \
    && /opt/casandra-web/venv/bin/pip install --disable-pip-version-check --no-cache-dir /build/backend \
    && /usr/local/bin/python -m venv /opt/casandra/venv \
    && /opt/casandra/venv/bin/pip install --disable-pip-version-check --no-cache-dir /build/casandra-tool \
    && /usr/local/bin/python -m venv /opt/integration/venv \
    && /opt/integration/venv/bin/pip install --disable-pip-version-check --no-cache-dir /build/integration

FROM ${BASE_IMAGE}

LABEL org.opencontainers.image.title="CasAndra Web scientific backend" \
      org.opencontainers.image.description="CasAndra web API and worker with isolated CasAndra, Integration, and CRISPRidentify v2 runtimes" \
      org.opencontainers.image.base.name="crispridentify-v2-backend:bb3e31d"

USER root
RUN /usr/sbin/groupadd --gid 10001 casandrasvc \
    && /usr/sbin/useradd --uid 10001 --gid 10001 --home-dir /nonexistent \
       --shell /usr/sbin/nologin --no-create-home casandrasvc \
    && /usr/bin/install -d -o 10001 -g 10001 -m 0700 /data/jobs \
    && /usr/bin/install -d -o 10001 -g 10001 -m 0700 /data/tmp \
    && /usr/bin/install -d -o root -g root -m 0755 /opt/casandra-web/bin \
    && /usr/bin/install -d -o root -g root -m 0755 /opt/casandra-web/config

COPY --from=builder /opt/casandra-web/venv /opt/casandra-web/venv
COPY --from=builder /opt/casandra/venv /opt/casandra/venv
COPY --from=builder /opt/integration/venv /opt/integration/venv
COPY run-crispridentify /opt/casandra-web/bin/run-crispridentify
COPY cleanup-loop /opt/casandra-web/bin/cleanup-loop
COPY runners.json /opt/casandra-web/config/runners.json

RUN /usr/bin/chown -R root:root /opt/casandra-web /opt/casandra /opt/integration \
    && /usr/bin/chmod 0755 /opt/casandra-web/bin/run-crispridentify \
        /opt/casandra-web/bin/cleanup-loop \
    && /usr/bin/chmod 0644 /opt/casandra-web/config/runners.json \
    && /usr/bin/chmod 0555 /opt/crispridentify/components/native/libliteral_fuzzy.so \
    && /usr/bin/chmod -R go-w /opt/casandra-web /opt/casandra /opt/integration

ENV PATH=/opt/casandra-web/venv/bin:/usr/local/bin:/usr/bin:/bin \
    HOME=/data/tmp \
    PYTHONHASHSEED=0 \
    PYTHONNOUSERSITE=1 \
    PYTHONSAFEPATH=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    OMP_NUM_THREADS=1 \
    OPENBLAS_NUM_THREADS=1 \
    MKL_NUM_THREADS=1 \
    NUMEXPR_NUM_THREADS=1

WORKDIR /data/jobs
USER 10001:10001
EXPOSE 8010
ENTRYPOINT []
CMD ["/opt/casandra-web/venv/bin/casandra-web-api"]
