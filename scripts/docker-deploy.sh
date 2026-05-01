#!/usr/bin/env bash
# ============================================================
# navicane — Deploy on Raspberry Pi
#
# Run this script ON the Raspberry Pi to pull the latest image
# and start the navicane service.
#
# Prerequisites:
#   1. Docker installed:  curl -fsSL https://get.docker.com | sh
#   2. User in docker group:  sudo usermod -aG docker $USER
#   3. I2C enabled:  sudo raspi-config → Interface → I2C
#   4. Camera enabled:  sudo raspi-config → Interface → Camera
#
# Usage:
#   ./scripts/docker-deploy.sh          # pull + start
#   ./scripts/docker-deploy.sh stop     # stop
#   ./scripts/docker-deploy.sh logs     # tail logs
#   ./scripts/docker-deploy.sh shell    # open shell in container
# ============================================================
set -euo pipefail

DOCKERHUB_USER="${DOCKERHUB_USER:-aakri0}"
IMAGE_NAME="${IMAGE_NAME:-navicane}"
TAG="${TAG:-latest}"
FULL_IMAGE="${DOCKERHUB_USER}/${IMAGE_NAME}:${TAG}"
CONTAINER_NAME="navicane"

ACTION="${1:-start}"

case "${ACTION}" in

  start)
    echo "→ Pulling latest image: ${FULL_IMAGE}"
    docker pull "${FULL_IMAGE}"

    echo "→ Stopping existing container (if any)..."
    docker rm -f "${CONTAINER_NAME}" 2>/dev/null || true

    echo "→ Starting navicane..."
    docker run -d \
        --name "${CONTAINER_NAME}" \
        --restart unless-stopped \
        --privileged \
        --network host \
        -v /run/udev:/run/udev:ro \
        -v navicane-logs:/app/logs \
        -v navicane-audio:/app/audio_cache \
        -e NAVICANE_HEADLESS=1 \
        "${FULL_IMAGE}"

    echo ""
    echo "✅ navicane is running!"
    echo "   Logs:   docker logs -f ${CONTAINER_NAME}"
    echo "   Stop:   docker stop ${CONTAINER_NAME}"
    echo "   Shell:  docker exec -it ${CONTAINER_NAME} bash"
    ;;

  stop)
    echo "→ Stopping navicane..."
    docker stop "${CONTAINER_NAME}" 2>/dev/null || true
    docker rm "${CONTAINER_NAME}" 2>/dev/null || true
    echo "✅ Stopped"
    ;;

  logs)
    docker logs -f "${CONTAINER_NAME}"
    ;;

  shell)
    docker exec -it "${CONTAINER_NAME}" bash
    ;;

  status)
    docker ps --filter "name=${CONTAINER_NAME}" --format "table {{.Status}}\t{{.Ports}}\t{{.Image}}"
    echo ""
    echo "Recent logs:"
    docker logs --tail 20 "${CONTAINER_NAME}" 2>/dev/null || echo "(not running)"
    ;;

  *)
    echo "Usage: $0 {start|stop|logs|shell|status}"
    exit 1
    ;;

esac
