FROM python:3.11-slim

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY alembic.ini ./
COPY alembic ./alembic
COPY src ./src

RUN pip install --no-cache-dir -e .

ENV PYTHONUNBUFFERED=1

CMD ["backtest", "serve", "--host", "0.0.0.0", "--port", "8000"]
