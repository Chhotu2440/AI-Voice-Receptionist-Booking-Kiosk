# syntax=docker/dockerfile:1.7
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Apply Debian security updates at build time (base images lag behind fixes, e.g. zlib CVEs found by Trivy).
RUN apt-get update     && apt-get upgrade -y --no-install-recommends     && rm -rf /var/lib/apt/lists/*

# Dependencies first for layer caching.
COPY pyproject.toml ./
RUN python - <<'EOF' > /tmp/requirements.txt
import tomllib
print("\n".join(tomllib.load(open("pyproject.toml", "rb"))["project"]["dependencies"]))
EOF
RUN pip install -r /tmp/requirements.txt

COPY alembic.ini ./
COPY migrations ./migrations
COPY app ./app

RUN useradd --system --uid 10001 --home /app appuser && chown -R appuser /app
USER appuser

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=3).status==200 else 1)"

# 3 workers suit a 4 vCPU host shared with MySQL/Redis. Graceful timeout lets requests drain on SIGTERM.
CMD ["gunicorn", "app.main:create_app()", "-k", "uvicorn.workers.UvicornWorker", \
     "--bind", "0.0.0.0:8000", "--workers", "3", "--graceful-timeout", "30", "--timeout", "60", \
     "--forwarded-allow-ips", "*", "--access-logfile", "-"]
