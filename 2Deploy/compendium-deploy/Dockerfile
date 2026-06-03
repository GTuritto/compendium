# Compendium access-surface image: the REST/MCP surface plus the CLI, run from
# the source tree. Dependencies are installed into /app/.venv; the project
# itself is NOT pip-installed (no [build-system] in pyproject), so it runs via
# `python -m compendium` with /app on sys.path. See deploy/README-lan.md.
#
# Base image is Docker Hub (not ghcr.io) for maximum reachability; uv is added
# with pip. The COPY paths below resolve in BOTH the in-repo build context
# (deploy/docker-compose.lan.yml, context "..") and the production bundle
# (context ".", which keeps entrypoint.sh under deploy/). See deploy/make-bundle.sh.
FROM python:3.12-slim-bookworm

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PIP_NO_CACHE_DIR=1

RUN pip install --no-cache-dir uv

# Dependency layer first for caching: install deps only, not the project.
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

# Application source (changes most often, so it goes last).
COPY compendium/ ./compendium/
COPY migrations/ ./migrations/
COPY config/ ./config/
COPY alembic.ini ./

COPY deploy/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

EXPOSE 8787
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
