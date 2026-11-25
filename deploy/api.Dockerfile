# 后端：规则引擎 + FastAPI + RAG。语料不进镜像，运行时按数据卷挂载。
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    UV_HTTP_TIMEOUT=180 \
    UV_HTTP_RETRIES=5

COPY campus-kb/pyproject.toml campus-kb/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

FROM python:3.12-slim-bookworm

# onnxruntime（本地语义检索）需要 libgomp1；HTTPS 调模型需要 CA 证书
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY campus-kb/checker.py campus-kb/authority.json ./
COPY campus-kb/rules ./rules
COPY campus-kb/api ./api

RUN useradd --system --create-home --uid 10001 appuser \
    && mkdir -p /app/corpus/text /app/corpus/.index /app/corpus/images \
    && mkdir -p /home/appuser/.cache/huggingface \
    && chown -R appuser:appuser /app/corpus /home/appuser

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    CAMPUS_CORPUS_DIR=/app/corpus/text \
    CAMPUS_INDEX_DIR=/app/corpus/.index

USER appuser
EXPOSE 8000

# SSE 是 async 单 worker 即可；多 worker 会把向量模型重复加载进内存
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
