# Two-stage Dockerfile per spec §1.11b.
# Per-producer variants (Dockerfile.{rewrite,marks,impose,trap}) override the
# build args. This base file builds the central all-in-one image used during
# development and as the fallback for sidecars.

FROM python:3.12-slim AS builder

# Build args drive per-producer customization:
#   COMPILE_EXTRAS=""        -> rewrite (no native deps)
#   COMPILE_EXTRAS="geom"    -> marks/impose/trap (Clipper2 via pyclipr)
#   COMPILE_EXTRAS="geom,trap-gs" -> trap with Ghostscript fallback engine
ARG COMPILE_EXTRAS=""
ARG NEEDS_NATIVE=""

# Install build toolchain only when a native extra is requested.
RUN if [ -n "$NEEDS_NATIVE" ]; then \
      apt-get update && apt-get install -y --no-install-recommends \
        gcc g++ cmake ninja-build python3-dev \
      && rm -rf /var/lib/apt/lists/*; \
    fi

WORKDIR /app
COPY pyproject.toml ./
COPY src/ ./src/
COPY schemas/ ./schemas/

RUN pip install --no-cache-dir uv && \
    if [ -n "$COMPILE_EXTRAS" ]; then \
      uv sync --no-dev --extra "$COMPILE_EXTRAS"; \
    else \
      uv sync --no-dev; \
    fi


FROM python:3.12-slim AS runtime

# tini handles PID-1 signal forwarding and reaps zombie children from
# the per-job rlimit subprocesses (see compile_pdf.sandbox).
RUN apt-get update && apt-get install -y --no-install-recommends tini \
 && rm -rf /var/lib/apt/lists/* \
 && groupadd --system --gid 10001 compile \
 && useradd  --system --uid 10001 --gid compile --no-create-home --shell /usr/sbin/nologin compile

WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/src /app/src
COPY --from=builder /app/schemas /app/schemas
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Producer routing: COMPILE_PRODUCER ∈ {rewrite, marks, impose, trap, all}.
# `all` mounts every router; per-producer variants override the env var.
ARG PRODUCER=all
ENV COMPILE_PRODUCER=$PRODUCER

USER compile

# Healthcheck against the canonical /healthz path. Railway's healthcheckPath
# duplicates this from railway.toml; the HEALTHCHECK directive guards local
# `docker run` and Compose users.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request,sys; r=urllib.request.urlopen('http://127.0.0.1:'+__import__('os').environ.get('PORT','8080')+'/healthz', timeout=3); sys.exit(0 if r.status==200 else 1)" || exit 1

ENTRYPOINT ["tini", "--"]
CMD ["sh", "-c", "uvicorn compile_pdf.api.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
