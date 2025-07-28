# syntax=docker/dockerfile:1
FROM --platform=linux/amd64 python:3.12-slim AS base

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpoppler-cpp-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

ENTRYPOINT ["python", "main.py", "--input_dir", "/app/input", "--output_dir", "/app/output"] 