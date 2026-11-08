FROM python:3.14-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src/ ./src/
RUN python -m pip install --no-cache-dir .
RUN useradd --create-home appuser
USER appuser
EXPOSE 8000
# Bind published container ports to 127.0.0.1 on the host for demo use.
CMD ["uvicorn", "whatsapp_ai_agent.api:app", "--host", "0.0.0.0", "--port", "8000"]
