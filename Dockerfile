FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir fastapi uvicorn requests

COPY find_jobs.py server.py jobs.jsonl jobs.db ./
COPY static ./static

ENV DB_PATH=/data/jobs.db

CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8080"]
