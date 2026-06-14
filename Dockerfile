FROM python:3.11-slim

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./

# Install dependencies before copying app code so src edits don't bust the pip layer.
RUN mkdir -p src/app \
    && touch src/app/__init__.py \
    && pip install --no-cache-dir .

COPY alembic.ini ./
COPY alembic ./alembic
COPY resources ./resources
COPY src ./src

RUN pip install --no-cache-dir -e . --no-deps

ENV PYTHONUNBUFFERED=1

CMD ["kalyxctl", "serve", "--host", "0.0.0.0", "--port", "8000"]
