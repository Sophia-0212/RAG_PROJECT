FROM python:3.11.15-slim-bookworm@sha256:d29f48a31a8b408ed19272ca1e7b10ebae13b240a27e862d3d4217c528e2e0c3 AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    VIRTUAL_ENV=/opt/venv

RUN python -m venv "$VIRTUAL_ENV"
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

WORKDIR /build
COPY requirements.service.lock .
RUN pip install --no-compile \
        --index-url https://download.pytorch.org/whl/cpu \
        "torch==2.9.1+cpu"
RUN pip install --no-compile -r requirements.service.lock \
    && pip install --no-compile --no-deps "langchain-milvus==0.4.0"

FROM python:3.11.15-slim-bookworm@sha256:d29f48a31a8b408ed19272ca1e7b10ebae13b240a27e862d3d4217c528e2e0c3 AS runtime

LABEL org.opencontainers.image.title="RAG Enterprise Service" \
      org.opencontainers.image.description="CRM knowledge retrieval service" \
      org.opencontainers.image.source="RAG_PROJECT"

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    LANGGRAPH_STRICT_MSGPACK=true \
    RAG_ENV=production \
    RAG_API_HOST=0.0.0.0 \
    RAG_API_PORT=8000 \
    RAG_CHECKPOINT_PATH=/var/lib/rag/checkpoints.sqlite3 \
    HF_HUB_OFFLINE=true

RUN groupadd --system --gid 10001 rag \
    && useradd --system --uid 10001 --gid rag --home-dir /nonexistent --shell /usr/sbin/nologin rag \
    && mkdir -p /app /var/lib/rag \
    && chown -R rag:rag /app /var/lib/rag

COPY --from=builder /opt/venv /opt/venv
WORKDIR /app
COPY --chown=rag:rag . .

USER 10001:10001
EXPOSE 8000
VOLUME ["/var/lib/rag"]

HEALTHCHECK --interval=30s --timeout=3s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/live', timeout=2).read()"]

CMD ["python", "-m", "rag_service.api_cli", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
