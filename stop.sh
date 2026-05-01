#!/usr/bin/env bash
# ============================================================
# navicane — Universal stop script
#
# Stops the navicane container on any platform (Mac / RPi).
#
# Usage:
#   ./stop.sh              # stop the container
#   ./stop.sh --clean      # stop + remove volumes + image
# ============================================================
set -euo pipefail

# ── Colours ──────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

info()  { echo -e "${CYAN}→${NC} $*"; }
ok()    { echo -e "${GREEN}✅ $*${NC}"; }
warn()  { echo -e "${YELLOW}⚠️  $*${NC}"; }

CONTAINER_NAME="navicane"
DOCKERHUB_USER="${DOCKERHUB_USER:-aakri0}"
IMAGE_NAME="${IMAGE_NAME:-navicane}"
FULL_IMAGE="${DOCKERHUB_USER}/${IMAGE_NAME}:latest"
CLEAN="${1:-}"

echo ""
echo -e "${BOLD}══════════════════════════════════════════════════════${NC}"
echo -e "${BOLD}  🦯 navicane — Shutting down                        ${NC}"
echo -e "${BOLD}══════════════════════════════════════════════════════${NC}"
echo ""

# ── Stop the container ───────────────────────────────────────
if docker ps --format '{{.Names}}' 2>/dev/null | grep -q "^${CONTAINER_NAME}$"; then
    info "Stopping container: ${CONTAINER_NAME}..."
    docker stop "$CONTAINER_NAME"
    ok "Container stopped"
else
    info "Container '${CONTAINER_NAME}' is not running"
fi

# ── Remove the container ────────────────────────────────────
if docker ps -a --format '{{.Names}}' 2>/dev/null | grep -q "^${CONTAINER_NAME}$"; then
    info "Removing container: ${CONTAINER_NAME}..."
    docker rm "$CONTAINER_NAME"
    ok "Container removed"
fi

# ── Deep clean (optional) ───────────────────────────────────
if [[ "$CLEAN" == "--clean" ]]; then
    echo ""
    warn "Deep clean requested — removing volumes and image..."

    # Remove named volumes
    for vol in navicane-logs navicane-audio; do
        if docker volume inspect "$vol" &>/dev/null; then
            info "Removing volume: $vol"
            docker volume rm "$vol"
        fi
    done
    ok "Volumes removed"

    # Remove the image
    if docker image inspect "$FULL_IMAGE" &>/dev/null; then
        info "Removing image: $FULL_IMAGE"
        docker rmi "$FULL_IMAGE"
        ok "Image removed"
    fi

    # Remove buildx builder
    if docker buildx inspect navicane-builder &>/dev/null 2>&1; then
        info "Removing buildx builder..."
        docker buildx rm navicane-builder 2>/dev/null || true
        ok "Builder removed"
    fi

    echo ""
    ok "Full cleanup complete — everything removed"
else
    echo ""
    info "Logs are preserved in the 'navicane-logs' volume."
    info "To also remove volumes and image: ./stop.sh --clean"
fi

echo ""
echo -e "${BOLD}══════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}  navicane is stopped.${NC}"
echo -e "${BOLD}══════════════════════════════════════════════════════${NC}"
echo ""
