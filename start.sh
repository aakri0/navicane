#!/usr/bin/env bash
# ============================================================
# navicane — Universal start script
#
# Works on both macOS (Apple Silicon) and Raspberry Pi.
# Detects the platform, installs all prerequisites if missing,
# builds/pulls the Docker image, and starts the application.
#
# Usage:
#   ./start.sh              # auto-detect platform, install, run
#   ./start.sh --rebuild    # force a fresh image build
# ============================================================
set -euo pipefail

# ── Colours ──────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m' # no colour

info()  { echo -e "${CYAN}→${NC} $*"; }
ok()    { echo -e "${GREEN}✅ $*${NC}"; }
warn()  { echo -e "${YELLOW}⚠️  $*${NC}"; }
fail()  { echo -e "${RED}❌ $*${NC}"; exit 1; }

# ── Project paths ────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="${SCRIPT_DIR}"
# If this script is run from inside scripts/, go up one level
if [[ "$(basename "$SCRIPT_DIR")" == "scripts" ]]; then
    PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
fi
cd "$PROJECT_ROOT"

DOCKERHUB_USER="${DOCKERHUB_USER:-aakri0}"
IMAGE_NAME="${IMAGE_NAME:-navicane}"
TAG="${TAG:-latest}"
FULL_IMAGE="${DOCKERHUB_USER}/${IMAGE_NAME}:${TAG}"
CONTAINER_NAME="navicane"
REBUILD="${1:-}"

# ── Platform detection ───────────────────────────────────────
detect_platform() {
    local os arch
    os="$(uname -s)"
    arch="$(uname -m)"

    if [[ "$os" == "Darwin" ]]; then
        PLATFORM="mac"
        if [[ "$arch" == "arm64" ]]; then
            ARCH_LABEL="Apple Silicon (M-series)"
        else
            ARCH_LABEL="Intel Mac"
        fi
    elif [[ "$os" == "Linux" ]]; then
        # Check if we're on a Raspberry Pi
        if [[ -f /proc/device-tree/model ]] && grep -qi "raspberry" /proc/device-tree/model 2>/dev/null; then
            PLATFORM="rpi"
            ARCH_LABEL="Raspberry Pi ($(cat /proc/device-tree/model | tr -d '\0'))"
        else
            PLATFORM="linux"
            ARCH_LABEL="Linux ($arch)"
        fi
    else
        fail "Unsupported operating system: $os"
    fi
}

# ── Dependency: Docker ───────────────────────────────────────
install_docker_mac() {
    if ! command -v docker &>/dev/null; then
        info "Docker not found — installing via Homebrew..."

        # Install Homebrew if missing
        if ! command -v brew &>/dev/null; then
            info "Homebrew not found — installing..."
            /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
            # Add brew to PATH for this session
            eval "$(/opt/homebrew/bin/brew shellenv 2>/dev/null || /usr/local/bin/brew shellenv 2>/dev/null)"
        fi

        brew install --cask docker
        echo ""
        warn "Docker Desktop has been installed."
        warn "Please open Docker Desktop from Applications, wait for it to start,"
        warn "then re-run this script."
        echo ""
        exit 0
    fi

    # Check Docker daemon is running
    if ! docker info &>/dev/null; then
        warn "Docker Desktop is installed but not running."
        info "Starting Docker Desktop..."
        open -a Docker
        echo ""
        info "Waiting for Docker daemon to be ready..."
        local retries=0
        while ! docker info &>/dev/null; do
            retries=$((retries + 1))
            if [[ $retries -ge 60 ]]; then
                fail "Docker daemon did not start within 60 seconds. Open Docker Desktop manually."
            fi
            sleep 2
            printf "."
        done
        echo ""
        ok "Docker daemon is running"
    fi
}

install_docker_rpi() {
    if ! command -v docker &>/dev/null; then
        info "Docker not found — installing..."
        curl -fsSL https://get.docker.com | sh
        sudo usermod -aG docker "$USER"
        ok "Docker installed"
        warn "You were added to the 'docker' group."
        warn "Please log out and back in, then re-run this script."
        exit 0
    fi

    # Ensure current user can run docker without sudo
    if ! docker info &>/dev/null 2>&1; then
        if sudo docker info &>/dev/null 2>&1; then
            warn "Docker requires sudo. Adding you to the docker group..."
            sudo usermod -aG docker "$USER"
            warn "Please log out and back in, then re-run this script."
            exit 0
        else
            fail "Docker daemon is not running. Try: sudo systemctl start docker"
        fi
    fi
}

install_docker_linux() {
    # Same as RPi — generic Linux
    install_docker_rpi
}

ensure_docker() {
    case "$PLATFORM" in
        mac)   install_docker_mac   ;;
        rpi)   install_docker_rpi   ;;
        linux) install_docker_linux ;;
    esac
    ok "Docker is ready ($(docker --version))"
}

# ── Dependency: Buildx (Mac only — needed for ARM cross-compilation) ──
ensure_buildx() {
    if ! docker buildx version &>/dev/null; then
        warn "Docker Buildx not available. It comes with Docker Desktop 19.03+."
        warn "Please update Docker Desktop."
        exit 1
    fi

    # Create/reuse a builder instance
    local builder="navicane-builder"
    if ! docker buildx inspect "$builder" &>/dev/null; then
        info "Creating Buildx builder: $builder"
        docker buildx create --name "$builder" --driver docker-container --bootstrap
    fi
    docker buildx use "$builder"
}

# ── RPi hardware checks ─────────────────────────────────────
check_rpi_hardware() {
    info "Checking Raspberry Pi hardware interfaces..."

    # I2C
    if [[ -e /dev/i2c-1 ]]; then
        ok "I2C enabled (/dev/i2c-1)"
    else
        warn "I2C not enabled — run: sudo raspi-config → Interface → I2C → Enable"
    fi

    # Camera
    if ls /dev/video0 &>/dev/null; then
        ok "Camera device found (/dev/video0)"
    else
        warn "Camera not detected — run: sudo raspi-config → Interface → Camera → Enable"
    fi

    # Audio
    if command -v aplay &>/dev/null && aplay -l &>/dev/null 2>&1; then
        ok "Audio output available"
    else
        warn "Audio output not detected — espeak TTS may not produce sound"
    fi
}

# ── Build or pull the image ──────────────────────────────────
ensure_image() {
    local image_exists=false

    # Check if image already exists locally
    if docker image inspect "$FULL_IMAGE" &>/dev/null && [[ "$REBUILD" != "--rebuild" ]]; then
        image_exists=true
        ok "Image already exists: $FULL_IMAGE"
    fi

    if [[ "$image_exists" == "false" ]]; then
        case "$PLATFORM" in
            mac)
                info "Building Docker image locally (this may take 5–10 min on first run)..."
                ensure_buildx
                docker buildx build \
                    --platform linux/arm64 \
                    --tag "$FULL_IMAGE" \
                    --load \
                    "$PROJECT_ROOT"
                ok "Image built: $FULL_IMAGE"
                ;;
            rpi|linux)
                # Try pulling from Docker Hub first (faster), fall back to local build
                info "Pulling image from Docker Hub: $FULL_IMAGE"
                if docker pull "$FULL_IMAGE" 2>/dev/null; then
                    ok "Image pulled: $FULL_IMAGE"
                else
                    warn "Pull failed — building locally (this may take 15–20 min on RPi)..."
                    docker build --tag "$FULL_IMAGE" "$PROJECT_ROOT"
                    ok "Image built locally: $FULL_IMAGE"
                fi
                ;;
        esac
    fi
}

# ── Start the container ──────────────────────────────────────
start_container() {
    # Stop any existing container
    if docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
        info "Stopping existing container..."
        docker rm -f "$CONTAINER_NAME" &>/dev/null || true
    fi

    case "$PLATFORM" in
        mac)
            info "Starting navicane in development mode (mock hardware)..."
            docker run -d \
                --name "$CONTAINER_NAME" \
                --restart unless-stopped \
                -e NAVICANE_HEADLESS=1 \
                -e NAVICANE_MOCK=1 \
                -e GPIOZERO_PIN_FACTORY=mock \
                -v "${PROJECT_ROOT}/src:/app/src:ro" \
                -v "${PROJECT_ROOT}/models:/app/models:ro" \
                -v navicane-logs:/app/logs \
                "$FULL_IMAGE"
            ;;
        rpi)
            info "Starting navicane in production mode (full hardware access)..."
            docker run -d \
                --name "$CONTAINER_NAME" \
                --restart unless-stopped \
                --privileged \
                --network host \
                -v /run/udev:/run/udev:ro \
                -v navicane-logs:/app/logs \
                -v navicane-audio:/app/audio_cache \
                -e NAVICANE_HEADLESS=1 \
                "$FULL_IMAGE"
            ;;
        linux)
            info "Starting navicane (generic Linux, mock hardware)..."
            docker run -d \
                --name "$CONTAINER_NAME" \
                --restart unless-stopped \
                -e NAVICANE_HEADLESS=1 \
                -e NAVICANE_MOCK=1 \
                -e GPIOZERO_PIN_FACTORY=mock \
                -v navicane-logs:/app/logs \
                "$FULL_IMAGE"
            ;;
    esac
}

# ── Post-start checks ────────────────────────────────────────
verify_running() {
    sleep 2
    if docker ps --filter "name=${CONTAINER_NAME}" --format '{{.Status}}' | grep -qi "up"; then
        ok "navicane is running!"
    else
        warn "Container may have exited. Checking logs..."
        docker logs --tail 30 "$CONTAINER_NAME" 2>&1
        echo ""
        fail "Container failed to start. See logs above."
    fi
}

# ── Main ─────────────────────────────────────────────────────
main() {
    echo ""
    echo -e "${BOLD}══════════════════════════════════════════════════════${NC}"
    echo -e "${BOLD}  🦯 navicane — Smart Blind Stick                    ${NC}"
    echo -e "${BOLD}══════════════════════════════════════════════════════${NC}"
    echo ""

    # Step 1: Detect platform
    detect_platform
    info "Platform detected: ${BOLD}${ARCH_LABEL}${NC}"
    echo ""

    # Step 2: Install Docker if missing
    echo -e "${BOLD}[1/4] Checking Docker...${NC}"
    ensure_docker
    echo ""

    # Step 3: RPi-specific hardware checks
    if [[ "$PLATFORM" == "rpi" ]]; then
        echo -e "${BOLD}[2/4] Checking hardware interfaces...${NC}"
        check_rpi_hardware
        echo ""
    else
        echo -e "${BOLD}[2/4] Hardware checks (skipped — not on RPi)${NC}"
        echo ""
    fi

    # Step 4: Build or pull image
    echo -e "${BOLD}[3/4] Preparing Docker image...${NC}"
    ensure_image
    echo ""

    # Step 5: Start the container
    echo -e "${BOLD}[4/4] Starting navicane...${NC}"
    start_container
    verify_running

    # Print summary
    echo ""
    echo -e "${BOLD}══════════════════════════════════════════════════════${NC}"
    echo -e "${GREEN}  navicane is up and running!${NC}"
    echo ""
    echo "  View logs:     docker logs -f ${CONTAINER_NAME}"
    echo "  Open shell:    docker exec -it ${CONTAINER_NAME} bash"
    echo "  Stop:          ./stop.sh"
    echo "  Restart:       docker restart ${CONTAINER_NAME}"

    if [[ "$PLATFORM" == "mac" ]]; then
        echo ""
        echo -e "  ${YELLOW}Running in MOCK mode (no real hardware).${NC}"
        echo "  Source code is bind-mounted — edits in src/ are live."
    fi

    echo -e "${BOLD}══════════════════════════════════════════════════════${NC}"
    echo ""
}

main "$@"
