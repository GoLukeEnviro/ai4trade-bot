FROM python:3.12-slim AS builder

WORKDIR /app

COPY requirements.txt requirements-dev.txt ./

RUN pip install --no-cache-dir -r requirements.txt


FROM python:3.12-slim AS runtime

ARG RAINBOW_UID=10000
ARG RAINBOW_GID=10000

RUN groupadd --gid "${RAINBOW_GID}" rainbow \
    && useradd \
       --uid "${RAINBOW_UID}" \
       --gid "${RAINBOW_GID}" \
       --no-create-home \
       --shell /usr/sbin/nologin \
       rainbow

WORKDIR /app

COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

COPY --chown=10000:10000 core ./core
COPY --chown=10000:10000 rainbow ./rainbow

RUN mkdir -p /app/rainbow/storage \
    && chown -R 10000:10000 /app

USER 10000:10000

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD python -c "import json,sys,time;from pathlib import Path; p=Path('storage/heartbeat_rainbow.json'); \
    sys.exit(0 if p.exists() and time.time()-json.loads(p.read_text()).get('timestamp_unix',0)<120 else 1)"

ENTRYPOINT ["uvicorn", "rainbow.main:create_app", "--host", "0.0.0.0", "--port", "8000", "--factory"]
