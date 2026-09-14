# Renovate updates tags and digests together; builds always consume immutable bases.
FROM ghcr.io/astral-sh/uv:0.12.7@sha256:95f2aa1fe59274951cfe9b0cbc7972e879ff1004bc8945d130a32eb0dbd85945 AS uv
FROM docker.io/library/python:3.13.14-slim-bookworm@sha256:67a1e1f215ccda113cfc024e8639049257e88f273898f595b61476d128d387e8 AS builder

WORKDIR /opt/ditto
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_PYTHON_PREFERENCE=only-system UV_PYTHON_DOWNLOADS=never
COPY uv.lock pyproject.toml .python-version README.md ./
COPY packages/ ./packages/
COPY apps/backend/ ./apps/backend/
RUN uv sync --locked --no-dev --all-packages --no-editable --python /usr/local/bin/python \
    && mkdir -p /runtime/var/lib/ditto/state /runtime/var/cache/ditto /runtime/var/log/ditto \
    && chown -R 65532:65532 /runtime/var \
    && rm -rf /usr/local/lib/python3.13/ensurepip \
    && find /usr/local/lib/python3.13/site-packages -maxdepth 1 \
         \( -name 'pip*' -o -name 'setuptools*' -o -name 'wheel*' \) -exec rm -rf {} +

FROM docker.io/library/python:3.13.14-slim-bookworm@sha256:67a1e1f215ccda113cfc024e8639049257e88f273898f595b61476d128d387e8 AS python-runtime
RUN rm -rf /usr/local/lib/python3.13/ensurepip \
    && find /usr/local/lib/python3.13/site-packages -maxdepth 1 \
         \( -name 'pip*' -o -name 'setuptools*' -o -name 'wheel*' \) -exec rm -rf {} +

FROM gcr.io/distroless/python3-debian13@sha256:f2b206661cee3edb44f132d7f054a9ced96f671d8a973de0db750895c9acb2fb AS debian-libraries

FROM gcr.io/distroless/base-debian13@sha256:9ef50bca108839d5986e4d84b7f7b2d79024c9293b7c35b162c6c55485bd5868 AS runtime

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
    PYTHON_VERSION=3.13.14 \
    PYTHONPATH=/opt/ditto/.venv/lib/python3.13/site-packages \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONNOUSERSITE=1 \
    PYTHONUNBUFFERED=1

LABEL org.opencontainers.image.title="Ditto" \
    org.opencontainers.image.version="${DITTO_PRODUCT_VERSION}" \
    org.opencontainers.image.revision="${DITTO_GIT_SHA}" \
    io.ditto.api-contract.version="${DITTO_API_CONTRACT_VERSION}" \
    io.ditto.api-contract.sha256="${DITTO_API_CONTRACT_SHA256}"

COPY --from=debian-libraries /usr/lib /usr/lib
COPY --from=debian-libraries /usr/lib /lib
COPY --from=python-runtime /usr/local /usr/local
COPY --from=builder --chown=65532:65532 /opt/ditto/.venv /opt/ditto/.venv
COPY --from=builder --chown=65532:65532 /runtime/var /var
COPY --chown=65532:65532 config/ /opt/ditto/config/

USER 65532:65532
WORKDIR /opt/ditto

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["/usr/local/bin/python", "-c", "import urllib.request; response = urllib.request.urlopen('http://127.0.0.1:8000/readyz', timeout=3); raise SystemExit(0 if response.status == 200 else 1)"]

ENTRYPOINT ["/usr/local/bin/python", "-m", "granian"]
CMD ["ditto_apps.main:app", "--interface", "asgi", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
