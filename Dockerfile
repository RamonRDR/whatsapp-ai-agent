FROM python:3.14-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
ENV DATABASE_URL=sqlite:////app/data/whatsapp_agent.db
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src/ ./src/
RUN python -m pip install --no-cache-dir .
RUN useradd --create-home appuser \
    && mkdir -p /app/data \
    && chown appuser:appuser /app/data
USER appuser
VOLUME ["/app/data"]
EXPOSE 8000
# Bind published ports to 127.0.0.1 on the host for local demonstration.
CMD ["uvicorn", "whatsapp_ai_agent.api:app", "--host", "0.0.0.0", "--port", "8000"]
