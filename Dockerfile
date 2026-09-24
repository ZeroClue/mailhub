# Multi-stage build for smaller final image
FROM python:3.11-slim AS builder

WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy dependency files and README (needed for package metadata)
COPY pyproject.toml uv.lock* README.md ./

# Install package with dependencies to system Python
RUN uv pip install --system --no-cache .

# Copy source code
COPY mailhub/ ./mailhub/

# Re-install package (non-editable)
RUN uv pip install --system --no-cache .

# Final stage
FROM python:3.11-slim

WORKDIR /app

# Create non-root user
RUN groupadd -r mailhub && useradd -r -g mailhub mailhub

# Copy Python packages and binaries from builder (installed to /usr/local)
COPY --from=builder /usr/local /usr/local

# Install runtime dependencies via pip (fallback)
RUN pip install --no-cache-dir httpx mcp==1.12.4

# Create config and state directories
RUN mkdir -p /home/mailhub/.config/mailhub /home/mailhub/.local/state/mailhub \
    && chown -R mailhub:mailhub /home/mailhub

USER mailhub
WORKDIR /home/mailhub

# Default to running the REST server
EXPOSE 8787
CMD ["mailhub", "serve"]
