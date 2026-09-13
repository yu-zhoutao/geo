# syntax=docker/dockerfile:1.7
FROM python:3.12-slim AS opencode-runtime

ENV DEBIAN_FRONTEND=noninteractive

RUN rm -f /etc/apt/apt.conf.d/docker-clean \
    && echo 'Binary::apt::APT::Keep-Downloaded-Packages "true";' \
        > /etc/apt/apt.conf.d/keep-cache

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt/lists,sharing=locked \
    apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl

ARG OPENCODE_VERSION=latest

RUN --mount=type=cache,target=/root/.cache/opencode \
    if [ -z "${OPENCODE_VERSION}" ] || [ "${OPENCODE_VERSION}" = "latest" ]; then \
        latest_url="$(curl -fsSI -L -o /dev/null -w '%{url_effective}' \
            https://github.com/anomalyco/opencode/releases/latest)"; \
        resolved_version="${latest_url##*/v}"; \
    else \
        resolved_version="${OPENCODE_VERSION#v}"; \
    fi \
    && if [ -z "${resolved_version}" ] || [ "${resolved_version}" = "${latest_url:-}" ]; then \
        echo "Failed to resolve OpenCode version" >&2; \
        exit 1; \
    fi \
    && curl -fsSL https://opencode.ai/install \
        | bash -s -- --version "${resolved_version}" --no-modify-path

FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1
ENV DEBIAN_FRONTEND=noninteractive
ENV GDAL_CONFIG=/usr/bin/gdal-config
ENV UV_LINK_MODE=copy
ENV GEO_AGENT_APP_SUPPORT_DIR=/opt/geo-agent/app-support
ENV GEO_AGENT_STATE_DIR=/tmp/geo-agent-eval/state
ENV GEO_AGENT_DATABASE_PATH=/tmp/geo-agent-eval/metadata.db
ENV GEO_AGENT_WORKSPACE_ROOT=/tmp/geo-agent-eval/workspace
ENV GEO_AGENT_RUNTIME_CONFIG_ROOT=/tmp/geo-agent-eval/runtime-config
ENV GEO_AGENT_OPENCODE_BINARY=opencode

WORKDIR /app

RUN rm -f /etc/apt/apt.conf.d/docker-clean \
    && echo 'Binary::apt::APT::Keep-Downloaded-Packages "true";' \
        > /etc/apt/apt.conf.d/keep-cache

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt/lists,sharing=locked \
    apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        ca-certificates \
        curl \
        gdal-bin \
        git \
        libgdal-dev \
        proj-bin \
        proj-data

RUN --mount=type=cache,target=/root/.cache/pip \
    --mount=type=cache,target=/root/.cache/uv \
    python -m pip install --upgrade pip uv

COPY pyproject.toml uv.lock ./
COPY app ./app
COPY frontend/src/shared ./frontend/src/shared

RUN ln -s /data /app/data

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --extra docker \
    && UV_PROJECT_ENVIRONMENT=/opt/geo-agent/app-support/runtime/geospatial-python/.venv \
        uv --project app/runtime_assets/geospatial-python sync --frozen --python 3.12

COPY --from=opencode-runtime /root/.opencode /root/.opencode
RUN ln -s /root/.opencode/bin/opencode /usr/local/bin/opencode

ARG GEO_AGENT_REVISION=unknown
ARG GEO_AGENT_BUILD_DATE=unknown

LABEL org.opencontainers.image.title="geo-agent-evaluation"
LABEL org.opencontainers.image.description="Isolated single-attempt evaluation runner for geo-agent"
LABEL org.opencontainers.image.revision="${GEO_AGENT_REVISION}"
LABEL org.opencontainers.image.created="${GEO_AGENT_BUILD_DATE}"

ENTRYPOINT ["/app/.venv/bin/python", "-m", "app.evaluation.container_attempt"]
