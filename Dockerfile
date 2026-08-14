FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# SQLite mode reads fastclinic.sqlite. Mount /data and set FASTCLINIC_DB, then:
#   docker compose exec fastclinic python -m pms.importer /data/export.xlsx /data/fastclinic.sqlite
# PostgreSQL mode uses DATABASE_URL_PROD and FASTCLINIC_DB_SCHEMA=fast_clinic.
# The source SQLite database remains available as a rollback path.
EXPOSE 5005

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD curl --fail http://localhost:5005/login || exit 1

ENTRYPOINT ["python", "web_app.py"]
