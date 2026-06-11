FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Cockpit reads fastclinic.sqlite. In production mount a volume at /data and set
# FASTCLINIC_DB=/data/fastclinic.sqlite, then build it inside the container:
#   docker compose exec fastclinic python -m pms.importer /data/export.xlsx /data/fastclinic.sqlite
# If a data/*.xlsx export is present in the image, the app auto-builds on boot.
EXPOSE 5005

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD curl --fail http://localhost:5005/login || exit 1

ENTRYPOINT ["python", "web_app.py"]
