# Cloud Run Job image. Deploy region MUST be europe-west1 (action-plan.md §3)
# for EU data residency; region is the one setting in this file that is
# reversible later by redeploying, everything else (bucket/DB jurisdiction)
# is not.
FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml ./
COPY src ./src

RUN pip install --no-cache-dir .

ENV PYTHONUNBUFFERED=1

ENTRYPOINT ["python", "-m", "reporting_etl.main"]
