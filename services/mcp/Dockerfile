FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    MCP_TRUST_TRANSPORT_AUTH=true \
    PORT=8000

WORKDIR /app

COPY pyproject.toml ./
COPY erp_forecast ./erp_forecast

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir .

EXPOSE 8000

CMD ["sh", "-c", "uvicorn erp_forecast.server:app --host 0.0.0.0 --port ${PORT:-8000}"]
