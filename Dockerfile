FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install ".[dashboard]"

COPY dashboard ./dashboard

RUN useradd --create-home --uid 1000 app
USER app

CMD ["python", "-m", "txpipeline", "schedule", "--source", "s3", "--interval", "30"]
