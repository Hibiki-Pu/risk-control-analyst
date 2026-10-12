# RiskControl Analyst — calculation service + API
# Build from the repository root:  docker build -f services/api/Dockerfile .
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Dependencies first so the layer caches.
COPY services/api/requirements.txt /app/services/api/requirements.txt
RUN pip install --no-cache-dir -r /app/services/api/requirements.txt

# Application code, seed generator and the shipped synthetic dataset.
COPY services/api /app/services/api
COPY data /app/data

# Regenerate the dataset deterministically (no-op if it is already complete) and
# make sure the runtime directory exists.
RUN cd /app && python data/synthetic/generate.py --write \
    && python data/synthetic/generate.py --check \
    && mkdir -p /app/runtime

WORKDIR /app/services/api

EXPOSE 8000

# Runs the deterministic calculation service. No key is required: market data
# falls back to clearly-labelled fixtures and the AI analyst falls back to the
# deterministic planner.
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
