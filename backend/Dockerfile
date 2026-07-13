# syntax=docker/dockerfile:1.7
FROM python:3.12-slim-bookworm@sha256:8a7e7cc04fd3e2bd787f7f24e22d5d119aa590d429b50c95dfe12b3abe52f48b

ARG VCS_REF=unknown
ARG BUILD_DATE=unknown

LABEL org.opencontainers.image.title="ECG learning backend" \
      org.opencontainers.image.revision=$VCS_REF \
      org.opencontainers.image.created=$BUILD_DATE

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

RUN groupadd --gid 10001 ecg \
    && useradd --uid 10001 --gid ecg --no-create-home --shell /usr/sbin/nologin ecg

WORKDIR /app
COPY requirements-prod.txt ./requirements-prod.txt
RUN pip install --require-hashes --requirement requirements-prod.txt
COPY --chown=10001:10001 app ./app

USER 10001:10001
EXPOSE 8000
STOPSIGNAL SIGTERM

HEALTHCHECK --interval=30s --timeout=5s --start-period=120s --retries=3 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/readyz', timeout=3).read()"]

# The GCE service runs with host networking. Loopback keeps Uvicorn private
# behind Caddy and makes 127.0.0.1 the only trusted forwarding peer.
CMD ["uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000", "--workers", "1", "--proxy-headers", "--forwarded-allow-ips=127.0.0.1"]
