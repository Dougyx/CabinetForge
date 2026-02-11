# syntax=docker/dockerfile:1.7
FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.prod.txt requirements.lock.txt requirements.txt ./
COPY vendor/wheels ./vendor/wheels

RUN python -m pip install --upgrade pip && \
    python -m pip install --no-index --find-links=/app/vendor/wheels -r requirements.prod.txt

COPY cabinetforge ./cabinetforge
COPY templates ./templates
COPY static ./static
COPY app.py ./app.py

EXPOSE 8000

CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "1", "--threads", "8", "app:app"]
