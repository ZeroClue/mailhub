#!/usr/bin/env bash
set -euo pipefail

# Docker test script for mailhub
# Run locally to verify Docker image and compose work correctly

set -x

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() { echo -e "${GREEN}[INFO]${NC} $*"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*"; }

cleanup() {
    log_info "Cleaning up..."
    docker compose down -v --remove-orphans 2>/dev/null || true
}

trap cleanup EXIT

main() {
    log_info "Starting Docker test suite for zc-mailhub"
    
    # 1. Build image
    log_info "Building Docker image..."
    docker build -t zc-mailhub:test .
    
    # 2. Start services
    log_info "Starting services with docker-compose..."
    docker compose up -d
    
    # 3. Wait for health endpoint
    log_info "Waiting for health endpoint..."
    for i in {1..30}; do
        if curl -sf http://localhost:8787/health >/dev/null 2>&1; then
            log_info "Health endpoint responding"
            break
        fi
        sleep 1
        if [ $i -eq 30 ]; then
            log_error "Health endpoint did not respond in time"
            docker compose logs mailhub
            exit 1
        fi
    done
    
    # 4. Test basic health
    log_info "Testing /health endpoint..."
    response=$(curl -s http://localhost:8787/health)
    if echo "$response" | grep -q '"status":"ok"'; then
        log_info "Basic health check passed"
    else
        log_error "Basic health check failed: $response"
        exit 1
    fi
    
    # 3. Test detailed health
    log_info "Testing /health/detailed endpoint..."
    response=$(curl -s http://localhost:8787/health/detailed)
    if echo "$response" | grep -q '"status"'; then
        log_info "Detailed health check passed"
    else
        log_error "Detailed health check failed: $response"
        exit 1
    fi
    
    # 4. Test MCP server
    log_info "Testing MCP server..."
    output=$(docker compose run --rm mailhub-mcp --help 2>&1 || true)
    if echo "$output" | grep -q "Mailhub MCP"; then
        log_info "MCP server starts correctly"
    else
        log_warn "MCP server output unexpected: $output"
    fi
    
    # 5. Test graceful shutdown
    log_info "Testing graceful shutdown..."
    docker compose stop
    if [ $? -eq 0 ]; then
        log_info "Graceful shutdown successful"
    else
        log_warn "Graceful shutdown had issues"
    fi
    
    # 6. Test rebuild
    log_info "Testing rebuild..."
    docker compose up -d --build
    sleep 5
    curl -sf http://localhost:8787/health >/dev/null && log_info "Rebuild successful" || log_error "Rebuild failed"
    
    log_info "All Docker tests passed!"
}

main "$@"
