FROM python:3.12-slim

WORKDIR /app

# System deps for psycopg2, xgboost, shap (numba/llvmlite build needs)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --break-system-packages -r requirements.txt

COPY app ./app
COPY migrations ./migrations

# Model artifacts are built by the training pipeline (see README "Training
# the model") and expected at ./artifacts before the image is built, or
# mounted as a volume in docker-compose for local dev.
COPY artifacts ./artifacts

WORKDIR /app/app
EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
