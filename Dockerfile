# Use Python 3.13 slim image
FROM python:3.13-slim AS builder

WORKDIR /app

# Copy dependency files first for better caching
COPY requirements.txt ./

# Create virtual environment and install dependencies
RUN python -m venv /app/.venv && \
    /app/.venv/bin/pip install --no-cache-dir --upgrade pip && \
    /app/.venv/bin/pip install --no-cache-dir -r requirements.txt

# Production image
FROM python:3.13-slim

WORKDIR /app

# Configure environment
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

# Copy virtual environment from builder
COPY --from=builder /app/.venv /app/.venv

# Copy application code
COPY src/ ./src/

# Run the service
CMD ["python", "-m", "src.main"]

