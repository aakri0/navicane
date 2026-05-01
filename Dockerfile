# ============================================================
# navicane — production Dockerfile
#
# Multi-stage build optimised for Raspberry Pi (ARM64/ARMv7).
# Also runs on Apple Silicon Macs (ARM64) for development.
#
# Uses Debian Bookworm (same base as RPi OS) and installs
# picamera2 via system packages so libcamera bindings work.
# ============================================================

# ── Stage 1 : Build wheels ──────────────────────────────────
FROM python:3.11-slim-bookworm AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        cmake \
        pkg-config \
        libcap-dev \
        libatlas-base-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

COPY requirements.txt .

# Build binary wheels into /wheels (speeds up the runtime stage)
RUN pip wheel --no-cache-dir --wheel-dir=/wheels -r requirements.txt


# ── Stage 2 : Runtime ───────────────────────────────────────
FROM python:3.11-slim-bookworm AS runtime

LABEL maintainer="aakri0" \
      description="navicane — Smart Blind Stick for visually impaired" \
      version="1.0.0"

# ── System dependencies ─────────────────────────────────────
# espeak          – offline TTS
# i2c-tools       – MPU-6050 debugging
# libcamera0.3    – Pi Camera (libcamera runtime)
# python3-picamera2 – Pi Camera Python bindings
# libcap2         – gpiozero capability checks
# libatlas3-base  – numpy BLAS backend (smaller than openblas)
# libgl1 + libglib2.0-0 – OpenCV headless runtime deps
RUN apt-get update && apt-get install -y --no-install-recommends \
        espeak \
        espeak-data \
        i2c-tools \
        python3-picamera2 \
        python3-libcamera \
        libcap2 \
        libatlas3-base \
        libgl1 \
        libglib2.0-0 \
        libgomp1 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# Install pre-built wheels from stage 1
COPY --from=builder /wheels /wheels
RUN pip install --no-cache-dir --no-deps /wheels/*.whl \
    && rm -rf /wheels

# ── Application code ────────────────────────────────────────
WORKDIR /app

# Copy source tree (models are in .dockerignore — mounted at runtime)
COPY src/         ./src/
COPY scripts/     ./scripts/
COPY models/      ./models/

# Ensure log directory exists
RUN mkdir -p /app/logs /app/audio_cache

# ── Runtime configuration ───────────────────────────────────
# Headless by default inside containers (no X11 display)
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    NAVICANE_HEADLESS=1 \
    NAVICANE_BASE_DIR=/app \
    NAVICANE_MODEL_PATH=/app/models/best.pt \
    NAVICANE_MODEL_FALLBACK=/app/models/yolov8n.pt \
    NAVICANE_LOG_PATH=/app/logs/blind_stick.log

# Health check — the process should stay alive
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD pgrep -f "python.*main.py" || exit 1

# ── Entry point ─────────────────────────────────────────────
CMD ["python3", "src/main.py"]
