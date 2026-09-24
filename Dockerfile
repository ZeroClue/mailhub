# Single-stage build - simpler and more reliable
FROM python:3.11-slim

WORKDIR /app

# Create non-root user
RUN groupadd -r mailhub && useradd -r -g mailhub mailhub

# Install system dependencies and Python packages
RUN pip install --no-cache-dir httpx mcp==1.12.4 fastapi uvicorn[standard] pydantic pydantic-settings python-dotenv

# Copy pyproject.toml and source code
COPY pyproject.toml README.md ./
COPY mailhub/ ./mailhub/

# Install the package
RUN pip install --no-cache-dir -e .

# Create config and state directories
RUN mkdir -p /home/mailhub/.config/mailhub /home/mailhub/.local/state/mailhub \
    && chown -R mailhub:mailhub /home/mailhub

USER mailhub
WORKDIR /home/mailhub

# Default to running the REST server
EXPOSE 8787
CMD ["mailhub", "serve"]
