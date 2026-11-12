# API image. Build from the repository root:  docker build -t slotpay-api .
FROM python:3.11-slim
WORKDIR /srv
COPY api/requirements.txt api/requirements.txt
RUN pip install --no-cache-dir -r api/requirements.txt
COPY api api
COPY supabase supabase
COPY scripts scripts
WORKDIR /srv/api
ENV PORT=8000
EXPOSE 8000
# Apply migrations, then serve. DATABASE_URL must point at Postgres (Supabase direct or pooler connection).
CMD ["sh", "-c", "python ../scripts/migrate.py && python run.py"]
