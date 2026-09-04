# Renovate updates tags and digests together; builds always consume immutable bases.
FROM ghcr.io/prefix-dev/pixi:0.73.0@sha256:66ae514a4421ca06587291beb037e5151b1b280a4f54eed82f57e9b70b94d5ca AS builder

WORKDIR /opt/ditto

COPY pixi.toml pixi.lock pyproject.toml README.md ./
COPY packages/ ./packages/
COPY apps/backend/ ./apps/backend/
COPY config/ ./config/

RUN pixi install --frozen --environment default


FROM docker.io/library/debian:bookworm-slim@sha256:88200866dfff7ea7f5cbcb6ec7c8a701889efe6fe859fe64d6990e4b07ea4171 AS runtime

ARG DITTO_PRODUCT_VERSION=0+unknown
ARG DITTO_GIT_SHA=unknown
ARG DITTO_API_CONTRACT_VERSION=v1
ARG DITTO_API_CONTRACT_SHA256=unknown
ARG DITTO_RESEARCH_ENVIRONMENT_LOCK_HASH

ENV DITTO_CONFIG_ROOT=/opt/ditto \
    DITTO_STATE_ROOT=/var/lib/ditto/state \
    DITTO_CACHE_ROOT=/var/cache/ditto \
    DITTO_PRODUCT_VERSION=${DITTO_PRODUCT_VERSION} \
    DITTO_GIT_SHA=${DITTO_GIT_SHA} \
    DITTO_RESEARCH_CODE_VERSION=${DITTO_GIT_SHA} \
    DITTO_RESEARCH_ENVIRONMENT_LOCK_HASH=${DITTO_RESEARCH_ENVIRONMENT_LOCK_HASH} \
    DITTO_API_CONTRACT_VERSION=${DITTO_API_CONTRACT_VERSION} \
    DITTO_API_CONTRACT_SHA256=${DITTO_API_CONTRACT_SHA256} \
    ENVIRONMENT=production \
    HOME=/var/lib/ditto \
    PATH=/opt/ditto/.pixi/envs/default/bin:${PATH} \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONNOUSERSITE=1 \
    PYTHONUNBUFFERED=1

LABEL org.opencontainers.image.title="Ditto" \
    org.opencontainers.image.version="${DITTO_PRODUCT_VERSION}" \
    org.opencontainers.image.revision="${DITTO_GIT_SHA}" \
    io.ditto.api-contract.version="${DITTO_API_CONTRACT_VERSION}" \
    io.ditto.api-contract.sha256="${DITTO_API_CONTRACT_SHA256}"

COPY --from=builder --chown=65532:65532 /opt/ditto /opt/ditto

RUN mkdir -p /var/lib/ditto/state /var/cache/ditto /var/log/ditto \
    && chown -R 65532:65532 \
        /var/lib/ditto \
        /var/cache/ditto \
        /var/log/ditto \
    && chmod 0750 \
        /var/lib/ditto/state \
        /var/cache/ditto \
        /var/log/ditto

USER 65532:65532
WORKDIR /opt/ditto

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import urllib.request; response = urllib.request.urlopen('http://127.0.0.1:8000/readyz', timeout=3); raise SystemExit(0 if response.status == 200 else 1)"]

ENTRYPOINT ["granian"]
CMD ["ditto_apps.main:app", "--interface", "asgi", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
