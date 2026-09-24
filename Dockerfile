# Multi-stage build for smaller final image
FROM python:3.11-slim AS builder

WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy dependency files
COPY pyproject.toml uv.lock* ./

# Install dependencies
RUN uv sync --no-install-project --extra dev

# Copy source code
COPY mailhub/ ./mailhub/

# Install the package
RUN uv pip install --no-cache -e . --no-deps

# Final stage
FROM python:3.11-slim

WORKDIR /app

# Create non-root user
RUN groupadd -r mailhub && useradd -r -g mailhub mailhub

# Copy from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin/mailhub /usr/local/bin/mailhub
COPY --from=builder /usr/local/bin/mail /usr/local/bin/mail

# Create config and state directories
RUN mkdir -p /home/mailhub/.config/mailhub /home/mailhub/.local/state/mailhub \
    && chown -R mailhub:mailhub /home/mailhub

USER mailhub
WORKDIR /home/mailhub

# Default to running the REST server
EXPOSE 8787
CMD ["mailhub", "serve"]
