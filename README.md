# 🦯 Navicane — Smart Blind Stick

An AI-powered navigation aid for visually impaired users. Combines ultrasonic obstacle detection, YOLOv8 camera-based object recognition, IMU fall detection, GPS tracking, and offline text-to-speech — all running on a Raspberry Pi.

## Features

| Feature | Module | Status |
|---|---|---|
| **Dual ultrasonic obstacle detection** (head + ground level) | `ultrasonic.py` | ✅ |
| **YOLOv8 object recognition** (Indian Roads: Cars, Buses, Trucks, etc.) | `camera_detect.py` | ✅ |
| **Two-phase fall detection** (free-fall → impact within 500ms) | `imu.py` | ✅ |
| **GPS location announcements** (Neo-6M via UART) | `gps_tracker.py` | ✅ |
| **Offline TTS** (espeak with pre-cached WAV phrases) | `feedback.py` | ✅ |
| **Priority-based alert arbitration** (fall > elevation > obstacle > GPS) | `sensor_fusion.py` | ✅ |
| **Indoor/outdoor sensitivity toggle** (GPIO button or env var) | `main.py` | ✅ |
| **Multi-platform Docker deployment** (Mac M2 dev → RPi production) | `Dockerfile` | ✅ |

## Architecture

```
src/
├── config/
│   └── settings.py          # Central config — all pins, thresholds, env var overrides
├── modules/
│   ├── ultrasonic.py         # HC-SR04 dual sensor interface
│   ├── imu.py                # MPU-6050 gyroscope + accelerometer + fall detection
│   ├── camera_detect.py      # YOLOv8 inference (picamera2 + ultralytics)
│   ├── elevation.py          # Step / slope / terrain change detector
│   ├── feedback.py           # Buzzer + espeak TTS + audio caching
│   ├── gps_tracker.py        # Neo-6M NMEA parser + location announcer
│   └── sensor_fusion.py      # AlertManager with priority ordering + cooldowns
└── main.py                   # Multithreaded entry point
```

## Hardware

| Component | Connection | Pin |
|---|---|---|
| HC-SR04 Top (head) | Trig / Echo | GPIO17 / GPIO27 |
| HC-SR04 Bottom (ground) | Trig / Echo | GPIO22 / GPIO24 |
| MPU-6050 IMU | I2C SDA / SCL | GPIO2 / GPIO3 |
| Buzzer (BC557 PNP) | Base | GPIO5 |
| Mode Toggle Button | Pull-up | GPIO6 |
| Neo-6M GPS | UART TX/RX | `/dev/ttyAMA0` |
| Pi Camera V2 | CSI Ribbon | — |

## Quick Start

### One-command startup (Mac or RPi)

```bash
git clone https://github.com/aakri0/navicane.git
cd navicane
./start.sh
```

This auto-detects your platform, installs Docker if needed, builds the image, and starts the container.

### Manual Docker commands

```bash
# Build locally (Mac)
./scripts/docker-build.sh

# Build + push to Docker Hub
./scripts/docker-build.sh --push

# Run on Mac (mock hardware)
docker compose -f docker-compose.yml -f docker-compose.dev.yml up

# Deploy on Raspberry Pi
./scripts/docker-deploy.sh
```

### Stop

```bash
./stop.sh              # stop container, keep logs
./stop.sh --clean      # full teardown (remove volumes + image)
```

## Configuration

All settings can be overridden via environment variables:

| Variable | Default | Description |
|---|---|---|
| `NAVICANE_HEADLESS` | `1` (Docker) | Disable GUI rendering |
| `NAVICANE_MOCK` | `0` | Use mock GPIO (for Mac/testing) |
| `NAVICANE_MODE` | `outdoor` | Sensitivity profile (`indoor`/`outdoor`) |
| `NAVICANE_MODEL_PATH` | `models/best.pt` | Custom YOLO model path |
| `NAVICANE_GPS_PORT` | `/dev/ttyAMA0` | GPS serial port |
| `NAVICANE_LOG_PATH` | `logs/blind_stick.log` | Log file path |

### Indoor vs Outdoor Mode

| Parameter | Indoor | Outdoor |
|---|---|---|
| Detection range | 0.6 m | 1.0 m |
| Confidence threshold | 0.4 | 0.3 |
| Camera resolution | 640×480 | 1280×720 |
| Alert cooldown | 3 s | 5 s |

Toggle via: physical button (GPIO6), or `NAVICANE_MODE=indoor`.

## Model Performance

Trained on [Indian Roads Detection v7](https://universe.roboflow.com/indian-road-dataset/indian-roads-detection) (Roboflow):

| Metric | Value |
|---|---|
| Precision | 0.854 |
| Recall | 0.616 |
| mAP50 | 0.731 |
| mAP50-95 | 0.454 |

Best class: **Car** (mAP50 = 0.849). See [model_metrics.md](docs/model_metrics.md) for full breakdown.

## Project Structure

```
navicane/
├── src/                    # Application source code
├── models/                 # YOLO weights (gitignored — add best.pt manually)
├── scripts/                # Build, deploy, start/stop helpers
├── docs/                   # Model metrics, training notebook
├── archive/                # Historical development iterations
├── Dockerfile              # Multi-stage ARM build
├── docker-compose.yml      # RPi production deployment
├── docker-compose.dev.yml  # Mac development override
├── start.sh                # Universal start (Mac + RPi)
├── stop.sh                 # Universal stop
└── requirements.txt        # Python dependencies
```

## License

MIT
