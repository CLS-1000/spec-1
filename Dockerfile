# SPEC-1 Intelligence Engine — production image
# Build:  docker build -t spec-1 .
# Run:    docker run --rm -p 8000:8000 -e ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY spec-1

FROM python:3.11-slim-bookworm AS builder

WORKDIR /build

RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential \
 && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml requirements.txt ./
COPY src/ src/

RUN pip install --no-cache-dir --upgrade pip \
 && pip wheel --no-cache-dir --wheel-dir /wheels -e .


FROM python:3.11-slim-bookworm AS runtime

LABEL org.opencontainers.image.title="SPEC-1 Intelligence Engine" \
      org.opencontainers.image.source="https://github.com/mjlak1000/spec-1" \
      org.opencontainers.image.licenses="Proprietary"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    SPEC1_API_HOST=0.0.0.0 \
    SPEC1_API_PORT=8000 \
    SPEC1_STORE_PATH=/data/spec1_intelligence.jsonl \
    SPEC1_DB_PATH=/data/spec1.db \
    SPEC1_ENVIRONMENT=production

WORKDIR /app

# Non-root user — fail closed if container is compromised
RUN useradd --create-home --shell /usr/sbin/nologin --uid 10001 spec1

COPY --from=builder /wheels /wheels
COPY pyproject.toml requirements.txt ./
COPY src/ src/
COPY mcp_server.py ./
COPY ui/ ui/

RUN pip install --no-cache-dir --no-index --find-links=/wheels \
        -e . \
 && rm -rf /wheels \
 && mkdir -p /data \
 && chown -R spec1:spec1 /app /data

USER spec1
VOLUME ["/data"]
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request,sys; urllib.request.urlopen('http://127.0.0.1:8000/health',timeout=3); sys.exit(0)" || exit 1

CMD ["python", "-m", "spec1_api.main"]
