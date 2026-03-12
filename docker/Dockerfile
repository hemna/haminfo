#FROM python:3.11-slim AS prepare
#FROM ghcr.io/astral-sh/uv:python3.11-bookworm AS prepare
FROM ghcr.io/astral-sh/uv:python3.11-bookworm AS prepare

# Dockerfile for building a container during aprsd development.
ARG BRANCH
ARG COMMIT_SHA
ARG UID
ARG GID

ENV APP_GIT=https://github.com/hemna/haminfo.git
ENV APP_BRANCH=${BRANCH:-master}
ENV APP_COMMIT_SHA=${COMMIT_SHA:-}
ENV VIRTUAL_ENV=/root/.venv
ENV UID=${UID:-1000}
ENV GID=${GID:-1000}

RUN apt-get update && apt-get install -y --no-install-recommends \
    git sudo cron libmemcached-dev build-essential \
    && rm -rf /var/lib/apt/lists/*

ENV PIP_DEFAULT_TIMEOUT=100 \
    # Allow statements and log messages to immediately appear
    PYTHONUNBUFFERED=1 \
    # disable a pip version check to reduce run-time & log-spam
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    # cache is useless in docker image, so disable to reduce image size
    PIP_NO_CACHE_DIR=1

ENV LC_ALL=C.UTF-8
ENV LANG=C.UTF-8

# Stage 2
FROM prepare AS install
ARG CACHEBUST

WORKDIR /app
RUN uv venv
# Upgrade pip and virtualenv to patched versions (CVE fixes)
RUN uv pip install -U "pip>=26.0" "virtualenv>=20.36.1" "filelock>=3.20.3" wheel
RUN mkdir /config

# Clone the repo and checkout specific commit SHA if provided for reproducibility
# This ensures the image contains the exact revision that triggered the build
# For PR builds, github.sha is a merge commit that doesn't exist in the repo,
# so we fetch unshallow and try the checkout, falling back to HEAD if it fails
# Note: CACHEBUST is echoed to bust Docker layer cache when commit changes
RUN echo "Cache bust: $CACHEBUST" && \
    git clone -b $APP_BRANCH $APP_GIT && \
    cd /app/haminfo && \
    if [ -n "$APP_COMMIT_SHA" ]; then \
        git fetch --unshallow 2>/dev/null || true; \
        git checkout $APP_COMMIT_SHA 2>/dev/null || echo "SHA not found, using branch HEAD"; \
    fi && \
    echo "typing-extensions>=4.15.0" > /tmp/overrides.txt && \
    cd /app && uv pip install --override /tmp/overrides.txt /app/haminfo

RUN uv pip install oslo-config
RUN mkdir -p /app/.config/haminfo
RUN uv run oslo-config-generator --namespace haminfo --namespace haminfo.db --namespace haminfo.flask --namespace oslo.log > /config/haminfo.conf


### Final stage
FROM install AS final

# override this to run another configuration
ENV CONF=default
VOLUME ["/config"]
EXPOSE 8081/tcp
EXPOSE 8081/udp

COPY ./bin/api_entry.sh /app/
COPY ./bin/reload_db.sh /app/
COPY ./bin/db_upgrade.sh /app/
COPY ./bin/cron_entry.sh /app/
COPY ./bin/run_mqtt.sh /app/
COPY ./bin/clean_db.sh /app/
ENTRYPOINT ["/app/api_entry.sh"]
