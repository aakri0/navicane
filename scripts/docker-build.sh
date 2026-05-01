#!/usr/bin/env bash
# ============================================================
# navicane — Build, tag, and push multi-platform Docker image
#
# Prerequisites:
#   1. Docker Desktop with Buildx enabled
#   2. docker login  (authenticated to Docker Hub)
#
# Usage:
#   ./scripts/docker-build.sh                 # build only
#   ./scripts/docker-build.sh --push          # build + push
#   DOCKERHUB_USER=myuser ./scripts/docker-build.sh --push
# ============================================================
set -euo pipefail

# ── Configuration ────────────────────────────────────────────
DOCKERHUB_USER="${DOCKERHUB_USER:-aakri0}"
IMAGE_NAME="${IMAGE_NAME:-navicane}"
TAG="${TAG:-latest}"
FULL_IMAGE="${DOCKERHUB_USER}/${IMAGE_NAME}:${TAG}"

# Platforms: ARM64 covers both Apple Silicon Mac and RPi 4 (64-bit)
# ARMv7 covers RPi 3/4 running 32-bit RPi OS
PLATFORMS="linux/arm64,linux/arm/v7"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# ── Pre-flight checks ───────────────────────────────────────
echo "══════════════════════════════════════════════════════"
echo "  navicane Docker Build"
echo "══════════════════════════════════════════════════════"
echo "  Image:      ${FULL_IMAGE}"
echo "  Platforms:  ${PLATFORMS}"
echo "  Context:    ${PROJECT_ROOT}"
echo "══════════════════════════════════════════════════════"

# Ensure buildx builder exists
BUILDER_NAME="navicane-builder"
if ! docker buildx inspect "${BUILDER_NAME}" &>/dev/null; then
    echo "→ Creating buildx builder: ${BUILDER_NAME}"
    docker buildx create \
        --name "${BUILDER_NAME}" \
        --driver docker-container \
        --bootstrap
fi
docker buildx use "${BUILDER_NAME}"

# ── Build ────────────────────────────────────────────────────
PUSH_FLAG=""
if [[ "${1:-}" == "--push" ]]; then
    PUSH_FLAG="--push"
    echo "→ Will PUSH to Docker Hub after building"
else
    # Load into local Docker (only works for single-platform)
    PUSH_FLAG="--load"
    PLATFORMS="linux/arm64"  # load only supports single platform
    echo "→ Local build only (use --push to upload to Docker Hub)"
fi

echo ""
echo "→ Building for: ${PLATFORMS}"
docker buildx build \
    --platform "${PLATFORMS}" \
    --tag "${FULL_IMAGE}" \
    --tag "${DOCKERHUB_USER}/${IMAGE_NAME}:$(date +%Y%m%d)" \
    ${PUSH_FLAG} \
    "${PROJECT_ROOT}"

echo ""
echo "✅ Build complete: ${FULL_IMAGE}"

if [[ "${1:-}" == "--push" ]]; then
    echo ""
    echo "══════════════════════════════════════════════════════"
    echo "  Image pushed successfully!"
    echo ""
    echo "  Pull on Raspberry Pi:"
    echo "    docker pull ${FULL_IMAGE}"
    echo ""
    echo "  Run on Raspberry Pi:"
    echo "    docker compose up -d"
    echo "══════════════════════════════════════════════════════"
fi
