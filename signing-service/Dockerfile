# Cloud Run SERVICE (not a Job — listens on $PORT). Deploy region MUST be
# europe-west1, same as the GCS bucket and the ETL job, so no inter-region
# egress is added on any path (action-plan.md §3, §6).
FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml ./
COPY src ./src

RUN pip install --no-cache-dir .

ENV PYTHONUNBUFFERED=1

# Cloud Run injects $PORT; default 8080 covers local `docker run`.
CMD exec uvicorn signing_service.asgi:app --host 0.0.0.0 --port ${PORT:-8080}
