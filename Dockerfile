# Stage 1: Builder
FROM python:3.12-slim AS builder

WORKDIR /build

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# Stage 2: Runtime
FROM python:3.12-slim

RUN groupadd --gid 1000 botuser && \
    useradd --uid 1000 --gid botuser --shell /bin/bash --create-home botuser

WORKDIR /app

COPY --from=builder /install /usr/local

COPY . .

RUN mkdir -p /app/storage && chown botuser:botuser /app/storage

USER botuser

EXPOSE 9090

VOLUME ["/app/storage"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -m core.healthcheck_cmd

ENTRYPOINT ["python", "main.py"]
