#!/usr/bin/env bash
# ============================================================
# navicane — GitHub issue creation script
# Prerequisites: gh CLI installed and authenticated
# Labels and milestones must already exist in the repo.
# Usage: bash create_issues.sh
# ============================================================
set -euo pipefail

REPO="$(gh repo view --json nameWithOwner -q .nameWithOwner 2>/dev/null)"
if [[ -z "$REPO" ]]; then
  echo "ERROR: Could not detect repo. Run from inside the repo directory," \
       "or run: gh repo set-default"
  exit 1
fi

echo "==> Creating 45 issues in: $REPO"
echo ""

# ── Milestone title lookup ───────────────────────────────────
# gh issue create --milestone expects the milestone TITLE string.
get_milestone() {
  gh api "repos/$REPO/milestones" --paginate \
    --jq ".[] | select(.title | startswith(\"$1\")) | .title" \
    | head -1
}

M1=$(get_milestone "M1")
M2=$(get_milestone "M2")
M3=$(get_milestone "M3")
M4=$(get_milestone "M4")
M5=$(get_milestone "M5")
M6=$(get_milestone "M6")
M7=$(get_milestone "M7")
M8=$(get_milestone "M8")

echo "Milestones resolved:"
echo "  M1: $M1"
echo "  M2: $M2"
echo "  M3: $M3"
echo "  M4: $M4"
echo "  M5: $M5"
echo "  M6: $M6"
echo "  M7: $M7"
echo "  M8: $M8"
echo ""

# ── Helper ───────────────────────────────────────────────────
issue() {
  local title="$1" labels="$2" milestone="$3"
  shift 3
  # remaining args are the body lines (passed via heredoc in each call)
  gh issue create \
    --title  "$title" \
    --label  "$labels" \
    --milestone "$milestone" \
    --body   "$*"
  echo "  ✓ $title"
}

# ============================================================
# MILESTONE 1 — Hardware procurement & wiring
# ============================================================

gh issue create \
  --title "Source and verify all BOM components" \
  --label "hardware,good first issue" \
  --milestone "$M1" \
  --body "Go through the Bill of Materials and order every component. Once received, power-test each one individually before wiring anything together. Verify the Raspberry Pi 4B boots, confirm the HC-SR04 emits a ping (oscilloscope or logic analyser), confirm the MPU-6050 shows up on \`i2cdetect -y 1\` (address 0x68), and verify the Pi Camera shows a live feed with \`raspistill -o test.jpg\`.

**Acceptance criteria:**
- [ ] Every component powered and responding before any wiring begins
- [ ] Photo of all components laid out attached to this issue"
echo "  ✓ Issue 1 created"

gh issue create \
  --title "Wire HC-SR04 with voltage divider on ECHO pin" \
  --label "hardware" \
  --milestone "$M1" \
  --body 'The HC-SR04 VCC runs at 5V and ECHO output is 5V logic, but Raspberry Pi GPIO is 3.3V tolerant only. Skipping the divider risks permanently damaging GPIO27.

**Wiring:**
- VCC → Pin 2 (5V)
- GND → Pin 6 (GND)
- TRIG → Pin 11 (GPIO17)
- ECHO → 1kΩ → Pin 13 (GPIO27), junction also connected through 2kΩ to GND

**Test:** Run a quick Python snippet using `RPi.GPIO` to read distance. Confirm readings in the 5–400 cm range against a tape measure at known distances (20 cm, 50 cm, 100 cm, 200 cm).

**Acceptance criteria:**
- [ ] Readings within ±3 cm at 20 cm
- [ ] Readings within ±3 cm at 50 cm
- [ ] Readings within ±3 cm at 100 cm
- [ ] Readings within ±3 cm at 200 cm'
echo "  ✓ Issue 2 created"

gh issue create \
  --title "Wire MPU-6050 IMU via I2C" \
  --label "hardware" \
  --milestone "$M1" \
  --body 'The MPU-6050 communicates over I2C at 3.3V — no level shifting needed since both devices operate at the same voltage.

**Wiring:**
- VCC → Pin 1 (3.3V)
- GND → Pin 9 (GND)
- SDA → Pin 3 (GPIO2)
- SCL → Pin 5 (GPIO3)

**Test:** Run `sudo i2cdetect -y 1` and confirm 0x68 appears in the address grid. Then run a short `smbus2` script reading the accelerometer registers and confirm non-zero values that change when the sensor is tilted.

**Acceptance criteria:**
- [ ] Device appears at 0x68 in `i2cdetect -y 1` output
- [ ] Raw accelerometer readings respond visibly to physical movement'
echo "  ✓ Issue 3 created"

gh issue create \
  --title "Wire buzzer and vibration motor via GPIO and NPN transistor" \
  --label "hardware" \
  --milestone "$M1" \
  --body 'The active buzzer draws ~30 mA which the RPi GPIO can supply directly. The vibration motor can draw up to 80–120 mA which exceeds GPIO limits — use a 2N2222 NPN transistor to switch it.

**Buzzer wiring:**
- Buzzer (+) → GPIO22 (Pin 15) via 100Ω resistor
- Buzzer (−) → GND (Pin 14)

**Motor wiring:**
- Motor (+) → 5V (Pin 2)
- Motor (−) → Transistor Collector
- Transistor Base → GPIO23 (Pin 16) via 1kΩ resistor
- Transistor Emitter → GND
- 1N4007 flyback diode across motor terminals (cathode to +)

**Acceptance criteria:**
- [ ] Buzzer sounds on GPIO22 HIGH
- [ ] Vibration motor spins on GPIO23 HIGH
- [ ] No GPIO damage or warnings after toggling both outputs'
echo "  ✓ Issue 4 created"

gh issue create \
  --title "Connect Pi Camera Module v2 via CSI port" \
  --label "hardware" \
  --milestone "$M1" \
  --body 'Lift the plastic latch on the CSI port (between HDMI and headphone jack), insert the ribbon cable with the contacts facing the HDMI side, and press the latch down firmly. Incorrect orientation is the most common camera failure.

**Test:** Run `raspistill -o test.jpg` and open the file. Then verify OpenCV can read frames:
```bash
python3 -c "import cv2; cap=cv2.VideoCapture(0); ret,f=cap.read(); print(ret, f.shape)"
```

**Acceptance criteria:**
- [ ] `raspistill` produces a clear, in-focus image
- [ ] OpenCV captures a valid frame with shape `(480, 640, 3)` or similar'
echo "  ✓ Issue 5 created"

gh issue create \
  --title "Wire Neo-6M GPS module via UART (optional)" \
  --label "hardware,enhancement" \
  --milestone "$M1" \
  --body 'The GPS module uses UART serial at 9600 baud. RPi'\''s UART pins are shared with the serial console by default — disable the serial login shell in `raspi-config` first (keep hardware port enabled).

**Wiring:**
- GPS VCC → Pin 4 (5V)
- GPS GND → Pin 6 (GND)
- GPS TX → Pin 8 (GPIO14 / UART RX on RPi)
- GPS RX → Pin 10 (GPIO15 / UART TX on RPi)

**Test:** `cat /dev/ttyAMA0` should stream NMEA sentences. Parse with `pynmea2` and confirm lat/lon update outdoors.

**Acceptance criteria:**
- [ ] Valid NMEA sentences received on `/dev/ttyAMA0`
- [ ] Latitude/longitude accurate to within 10 metres in an outdoor test'
echo "  ✓ Issue 6 created"

gh issue create \
  --title "Validate full breadboard prototype continuity" \
  --label "hardware,testing" \
  --milestone "$M1" \
  --body 'Before committing to the final enclosure, verify the full circuit with all sensors, actuators, and the RPi operating simultaneously.

**Steps:**
1. Connect all components as per issues #2–#6
2. Import and exercise each module from the terminal
3. Observe no GPIO warnings, no SMBus errors, no camera errors
4. Run all modules concurrently for 10 minutes and monitor temperature

```bash
vcgencmd measure_temp
```

**Acceptance criteria:**
- [ ] All sensors active simultaneously for 10 minutes without exceptions
- [ ] CPU temperature stays below 80°C throughout the run
- [ ] No GPIO warnings or SMBus errors in the terminal output'
echo "  ✓ Issue 7 created"

# ============================================================
# MILESTONE 2 — OS & development environment
# ============================================================

gh issue create \
  --title "Flash Raspberry Pi OS 64-bit and initial boot configuration" \
  --label "software,good first issue" \
  --milestone "$M2" \
  --body 'Use Raspberry Pi Imager (v1.8+). Select "Raspberry Pi OS (64-bit)", configure WiFi SSID/password and SSH in the Imager settings before writing so the device is headless-ready on first boot.

After boot, run `sudo raspi-config` and set: locale, timezone, hostname (`navicane`), and expand the filesystem.

**Acceptance criteria:**
- [ ] `ssh pi@navicane.local` connects without errors
- [ ] `uname -m` returns `aarch64`'
echo "  ✓ Issue 8 created"

gh issue create \
  --title "Enable I2C, UART, Camera interfaces via raspi-config" \
  --label "software" \
  --milestone "$M2" \
  --body 'Under "Interface Options" in `raspi-config`, enable: Camera, I2C, Serial Port (disable login shell, keep hardware port enabled). Reboot, then verify:

```bash
ls /dev/video0    # camera
ls /dev/i2c-1     # I2C
ls /dev/ttyAMA0   # UART
```

**Acceptance criteria:**
- [ ] `/dev/video0` exists after reboot
- [ ] `/dev/i2c-1` exists after reboot
- [ ] `/dev/ttyAMA0` exists after reboot'
echo "  ✓ Issue 9 created"

gh issue create \
  --title "Create and activate Python virtual environment" \
  --label "software,good first issue" \
  --milestone "$M2" \
  --body '```bash
sudo apt install python3-venv -y
python3 -m venv ~/navicane-env
echo "source ~/navicane-env/bin/activate" >> ~/.bashrc
source ~/.bashrc
```

**Acceptance criteria:**
- [ ] `which python3` returns a path inside `navicane-env`
- [ ] `python3 --version` returns 3.10 or higher
- [ ] `pip` points to the venv (not the system pip)'
echo "  ✓ Issue 10 created"

gh issue create \
  --title "Install and verify all Python dependencies" \
  --label "software" \
  --milestone "$M2" \
  --body 'With the venv active:

```bash
pip install opencv-python-headless ultralytics RPi.GPIO smbus2 \
            gTTS pygame gpsd-py3 pynmea2 numpy pyserial
```

Verify each critical import:
```bash
python3 -c "import cv2, ultralytics, RPi.GPIO, smbus2, pygame, gtts"
```

**Acceptance criteria:**
- [ ] All imports succeed with no errors
- [ ] `requirements.txt` with exact pinned versions committed to `main`'
echo "  ✓ Issue 11 created"

gh issue create \
  --title "Configure SSH and remote VS Code access" \
  --label "software" \
  --milestone "$M2" \
  --body 'Set up passwordless SSH with key-based auth for development convenience:

```bash
ssh-keygen -t ed25519
ssh-copy-id pi@navicane.local
```

Install the "Remote - SSH" extension in VS Code and connect to `navicane.local`. Verify you can open and edit files in `/home/pi/navicane/` directly.

**Acceptance criteria:**
- [ ] VS Code remote session opens to `navicane.local` without a password prompt
- [ ] Files in `/home/pi/navicane/` are editable from the remote session'
echo "  ✓ Issue 12 created"

# ============================================================
# MILESTONE 3 — Core software modules
# ============================================================

gh issue create \
  --title "Implement ultrasonic distance measurement module" \
  --label "software" \
  --milestone "$M3" \
  --body 'Create `modules/ultrasonic.py` with `setup()` and `get_distance()` functions.

- The 10µs TRIG pulse must be exact — use `time.sleep(0.00001)`.
- The ECHO measurement uses time between rising and falling edge.
- Guard against a timeout (ECHO stuck HIGH) with a maximum wait of 0.04 seconds, returning `None` on timeout.

**Acceptance criteria:**
- [ ] `get_distance()` returns values within ±3 cm at 20 cm
- [ ] `get_distance()` returns values within ±3 cm at 50 cm
- [ ] `get_distance()` returns values within ±3 cm at 100 cm
- [ ] `get_distance()` returns values within ±3 cm at 200 cm
- [ ] Returns `None` when no object is present within range'
echo "  ✓ Issue 13 created"

gh issue create \
  --title "Implement MPU-6050 fall detection module" \
  --label "software" \
  --milestone "$M3" \
  --body 'Create `modules/fall_detect.py`.

1. Wake the MPU-6050 by writing `0x00` to register `0x6B`
2. Read raw 16-bit signed values from registers `0x3B–0x40` for Ax, Ay, Az
3. Scale by 16384 (±2g default range)
4. Compute magnitude = √(Ax² + Ay² + Az²)
5. Thresholds: below 0.5g = free-fall; above 2.5g = impact
6. Both conditions within 500 ms = fall event

**Acceptance criteria:**
- [ ] Controlled drop test (stick dropped 1 m onto padded surface) triggers fall detection
- [ ] Zero false positives during a 5-minute normal walking test'
echo "  ✓ Issue 14 created"

gh issue create \
  --title "Implement multi-modal feedback module" \
  --label "software" \
  --milestone "$M3" \
  --body 'Create `modules/feedback.py` with three output methods:

- `buzz(duration)`: GPIO22 HIGH for `duration` seconds
- `vibrate(duration)`: GPIO23 HIGH for `duration` seconds
- `speak(text)`: Generate TTS with gTTS, cache the mp3 to `audio_cache/{hash}.mp3`, play with pygame (non-blocking)

Pre-generate audio cache on module `setup()` for all common phrases to eliminate network dependency at runtime.

**Acceptance criteria:**
- [ ] `buzz()` triggers the buzzer correctly
- [ ] `vibrate()` triggers the motor correctly
- [ ] `speak()` plays audio offline from the local cache
- [ ] `speak()` does not block the calling thread beyond the audio duration'
echo "  ✓ Issue 15 created"

gh issue create \
  --title "Implement YOLOv8 camera detection module" \
  --label "software,ml" \
  --milestone "$M3" \
  --body 'Create `modules/camera_detect.py`.

- Load `models/best.pt` at module import time — not per frame
- Resize incoming frames to 320×240 before inference to reduce latency on the RPi
- Return a list of `{"label": str, "conf": float}` dicts filtered to `conf >= 0.5`

**Acceptance criteria:**
- [ ] `capture_and_detect()` correctly labels a car held in front of the camera
- [ ] `capture_and_detect()` correctly labels a person held in front of the camera
- [ ] `capture_and_detect()` correctly labels a bus held in front of the camera
- [ ] Inference time per frame is under 200 ms on RPi 4B CPU'
echo "  ✓ Issue 16 created"

gh issue create \
  --title "Implement GPS location announcement module" \
  --label "software,enhancement" \
  --milestone "$M3" \
  --body 'Create `modules/gps_tracker.py`.

- Parse NMEA sentences from `/dev/ttyAMA0` using `pynmea2`
- Extract latitude and longitude from `$GPRMC` or `$GPGGA` sentences
- Implement a 30-second announcement interval
- Graceful fallback message when GPS has no fix

**Acceptance criteria:**
- [ ] `get_location()` returns valid float coordinates outdoors within 60 seconds of startup
- [ ] `get_location()` returns `(None, None)` indoors without crashing or blocking'
echo "  ✓ Issue 17 created"

gh issue create \
  --title "Implement sensor fusion and event arbitration logic" \
  --label "software" \
  --milestone "$M3" \
  --body 'Create `modules/sensor_fusion.py` to combine signals from all modules into a priority-ordered alert system.

**Priority order (highest → lowest):**
1. Fall detection
2. Obstacle within 50 cm (ultrasonic)
3. Object detected within 1 m (camera)
4. GPS announcement

Implement a global `AlertManager` class with a `should_alert(source)` method that enforces per-source cooldowns to prevent alert flooding.

**Acceptance criteria:**
- [ ] When ultrasonic detects an obstacle and a fall occurs simultaneously, the fall alert fires first
- [ ] No duplicate alerts from any single source within the cooldown window'
echo "  ✓ Issue 18 created"

# ============================================================
# MILESTONE 4 — ML model training & deployment
# ============================================================

gh issue create \
  --title "Download and prepare Indian Roads Detection dataset" \
  --label "ml" \
  --milestone "$M4" \
  --body 'Download the dataset from Roboflow Universe ("Indian Roads Detection" project) in YOLOv8 format.

- Inspect `data.yaml` for class names and counts
- Note any class with fewer than 200 samples for discussion
- Split: 80% train / 10% val / 10% test

**Acceptance criteria:**
- [ ] `data.yaml` is valid and all class paths resolve correctly
- [ ] Class distribution is documented in a comment on this issue
- [ ] Dataset is committed to `datasets/` or linked via `.gitignore` + DVC'
echo "  ✓ Issue 19 created"

gh issue create \
  --title "Fine-tune YOLOv8s for 75 epochs on GPU" \
  --label "ml" \
  --milestone "$M4" \
  --body 'Train on a GPU machine (Google Colab T4, local NVIDIA GPU, or cloud VM).

- Base checkpoint: `yolov8s.pt`
- Settings: `imgsz=640`, `batch=16`, `epochs=75`
- Save run to `runs/detect/navicane_v1/`
- Monitor val/box_loss — add early stopping if it stops improving after epoch 50

**Acceptance criteria:**
- [ ] Training completes without error
- [ ] `best.pt` produced in `runs/detect/navicane_v1/weights/`
- [ ] Loss curves show convergence (val loss not increasing at end)
- [ ] `mAP50 > 0.70` on the validation set'
echo "  ✓ Issue 20 created"

gh issue create \
  --title "Evaluate model metrics: mAP50, precision, recall per class" \
  --label "ml,testing" \
  --milestone "$M4" \
  --body 'Run `model.val()` on the held-out test set. Record per-class Precision, Recall, mAP50, and mAP50-95 in `docs/model_metrics.md`. Generate and commit the confusion matrix image.

**Target metrics:**

| Class | P target | R target | mAP50 target |
|---|---|---|---|
| Car | ≥0.88 | ≥0.70 | ≥0.83 |
| Bus | ≥0.85 | ≥0.50 | ≥0.68 |
| Truck | ≥0.83 | ≥0.65 | ≥0.76 |

Flag any class with Recall below 0.50 for dataset augmentation in a follow-up issue.

**Acceptance criteria:**
- [ ] All classes documented with P, R, mAP50, mAP50-95 values
- [ ] Confusion matrix image committed to `docs/`
- [ ] `docs/model_metrics.md` committed to `main`'
echo "  ✓ Issue 21 created"

gh issue create \
  --title "Export weights and transfer best.pt to Raspberry Pi" \
  --label "ml,software" \
  --milestone "$M4" \
  --body 'Copy `best.pt` (target ≤ 25 MB) to the RPi. Optionally export to ONNX and benchmark both formats on the RPi to determine which runs faster.

```bash
# ONNX export (optional)
model.export(format="onnx")

# Transfer to RPi
scp runs/detect/navicane_v1/weights/best.pt pi@navicane.local:~/navicane/models/
```

**Acceptance criteria:**
- [ ] `best.pt` loads in `modules/camera_detect.py` without errors on the RPi
- [ ] Inference completes within 200 ms per frame on the RPi'
echo "  ✓ Issue 22 created"

# ============================================================
# MILESTONE 5 — System integration
# ============================================================

gh issue create \
  --title "Build multithreaded main loop with thread safety" \
  --label "software" \
  --milestone "$M5" \
  --body 'Implement `main.py` using `threading.Thread(daemon=True)` for four threads: ultrasonic, camera, fall detection, GPS.

- Use `threading.Lock()` around all shared state (last alert time, mode flag)
- Handle `KeyboardInterrupt` cleanly with `GPIO.cleanup()` in a `finally` block

**Acceptance criteria:**
- [ ] All four threads start and run for 30 minutes without deadlock or crash
- [ ] `htop` shows no single thread consuming > 80% CPU during the 30-minute run'
echo "  ✓ Issue 23 created"

gh issue create \
  --title "Implement alert cooldown and debounce logic" \
  --label "software" \
  --milestone "$M5" \
  --body 'Implement global `DETECTION_PAUSE = 3.0` seconds.

- `should_alert(source)` checks `time.time() - last_alert[source] > DETECTION_PAUSE`
- Each source (ultrasonic, camera, fall, GPS) has its own independent cooldown
- Fall alert overrides cooldown on all other sources

**Acceptance criteria:**
- [ ] Walking past a stationary obstacle triggers exactly one alert per 3-second window, not a continuous stream
- [ ] Fall alert fires immediately regardless of other sources'\'' cooldown state'
echo "  ✓ Issue 24 created"

gh issue create \
  --title "Pre-cache TTS audio for all common alert phrases" \
  --label "software,enhancement" \
  --milestone "$M5" \
  --body 'At system startup, generate and save mp3 files for every phrase the system might speak. Store in `audio_cache/`. Cache key: `hashlib.md5(text.encode()).hexdigest()`.

**Phrases to cache:**
- "Obstacle ahead"
- "Car detected ahead"
- "Bus detected ahead"
- "Person detected ahead"
- "Truck detected ahead"
- "Fall detected, are you okay"
- "Smart stick ready"
- "GPS signal not available"
- Distance variants at 30 / 50 / 80 / 100 cm

**Acceptance criteria:**
- [ ] All audio files exist in `audio_cache/` on first boot
- [ ] `speak()` never makes a network call after initial cache generation
- [ ] Device operates correctly with WiFi disabled'
echo "  ✓ Issue 25 created"

gh issue create \
  --title "Create systemd auto-start service unit" \
  --label "software" \
  --milestone "$M5" \
  --body 'Create `/etc/systemd/system/navicane.service` so the main loop starts on power-on with no user interaction:

```ini
[Unit]
Description=navicane Smart Stick
After=network.target sound.target

[Service]
ExecStart=/home/pi/navicane-env/bin/python /home/pi/navicane/main.py
WorkingDirectory=/home/pi/navicane
User=pi
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

Enable with: `sudo systemctl enable navicane && sudo systemctl start navicane`

**Acceptance criteria:**
- [ ] Device announces "Smart stick ready" within 30 seconds of power-on without any SSH intervention
- [ ] `journalctl -u navicane -f` shows clean output with no Python tracebacks'
echo "  ✓ Issue 26 created"

gh issue create \
  --title "Add indoor/outdoor sensitivity toggle via physical button" \
  --label "software,enhancement" \
  --milestone "$M5" \
  --body 'Wire a momentary push button between GPIO25 and GND (use internal pull-up). A short press cycles between modes:

| Mode | Obstacle threshold | Detection confidence |
|---|---|---|
| INDOOR | 80 cm | 0.65 |
| OUTDOOR | 150 cm | 0.50 |

The current mode is announced via TTS on each toggle.

**Acceptance criteria:**
- [ ] Single press changes mode and speaks the new mode name
- [ ] No false triggers from button bounce (debounce window 200 ms)'
echo "  ✓ Issue 27 created"

# ============================================================
# MILESTONE 6 — Mechanical assembly
# ============================================================

gh issue create \
  --title "Design RPi, sensor, and power bank enclosures in CAD" \
  --label "mechanical" \
  --milestone "$M6" \
  --body 'Design three enclosures in Fusion 360, FreeCAD, or Tinkercad. Export STL files to `cad/stl/`.

**RPi enclosure:** 90×65×35 mm interior, vents on top face, cutouts for USB-C power, GPIO ribbon exit, camera ribbon passthrough, and micro-HDMI for setup.

**Sensor cap:** Attaches to the cane tip. Two forward-facing slots for HC-SR04 TRIG/ECHO windows. Cable channel through the centre to route wires up the pipe.

**Power bank pocket:** Friction-fit or velcro-close, sized to the specific power bank. Centre-of-gravity analysis should show the loaded assembly balances below the handle.

**Acceptance criteria:**
- [ ] All three STL files pass Cura/PrusaSlicer slicing with no non-manifold errors
- [ ] Post dimensions committed to `cad/README.md`'
echo "  ✓ Issue 28 created"

gh issue create \
  --title "3D print and fit-test all PLA enclosures" \
  --label "mechanical" \
  --milestone "$M6" \
  --body 'Print at 30% gyroid infill, 0.2 mm layer height, PLA+. Line RPi enclosure interior with copper adhesive tape for basic EMI shielding.

Test that all components seat correctly:
- RPi screws into M3 standoffs
- Camera ribbon exits cleanly
- GPIO ribbon bends without kinking
- Sensor cap fits snugly on 25 mm PVC OD

**Acceptance criteria:**
- [ ] All three enclosures printed and assembled
- [ ] All components fit without forcing
- [ ] No layer delamination visible
- [ ] Dimensions within ±0.5 mm of CAD spec'
echo "  ✓ Issue 29 created"

gh issue create \
  --title "Assemble 80–110 cm telescopic PVC frame" \
  --label "mechanical" \
  --milestone "$M6" \
  --body 'Use 25 mm OD / 21 mm ID PVC pipe for the outer section (110 cm) and a matching inner section (80 cm) for telescoping. A nylon grub screw through a pre-drilled hole in the outer pipe locks the extension height.

- Drill a 16 mm cable routing hole at 15 cm from the top to pass the camera ribbon
- Smooth all cut edges with sandpaper

**Acceptance criteria:**
- [ ] Pipe telescopes smoothly from 80–110 cm and locks firmly at any point
- [ ] Cable routing hole allows ribbon to pass without sharp bends'
echo "  ✓ Issue 30 created"

gh issue create \
  --title "Mount all electronics and cable-manage inside pipe" \
  --label "mechanical" \
  --milestone "$M6" \
  --body 'Thread all sensor wires through the PVC pipe interior before screwing the sensor cap on.

- Bundle wires in 3–4 groups using spiral wrap or cable ties at 10 cm intervals
- Secure the RPi enclosure and power bank pocket to the pipe mid-section using stainless M4 hose clamps
- Label each connector with heat-shrink marker sleeves

**Acceptance criteria:**
- [ ] No loose wires externally visible
- [ ] All connectors labelled
- [ ] Device can be dropped from 50 cm onto a padded surface without any component dislodging'
echo "  ✓ Issue 31 created"

gh issue create \
  --title "Install ergonomic foam grip and rubber cane tip" \
  --label "mechanical" \
  --milestone "$M6" \
  --body 'Slide a 20 cm EVA foam grip (18 mm ID) onto the top section of the pipe. If needed, wrap one layer of handlebar tape first to build up the diameter. Attach a 25 mm rubber ferrule tip to the bottom.

Verify the camera enclosure is positioned just below the grip and angled 30° downward.

**Acceptance criteria:**
- [ ] Grip is comfortable for a 5-minute continuous hold
- [ ] Rubber tip is secure and does not slip on tile or concrete
- [ ] Camera angle captures ground 80–120 cm ahead'
echo "  ✓ Issue 32 created"

# ============================================================
# MILESTONE 7 — Testing & validation
# ============================================================

gh issue create \
  --title "Unit test each sensor module in isolation" \
  --label "software,testing" \
  --milestone "$M7" \
  --body 'Write `tests/test_modules.py` using `pytest`. Mock GPIO and smbus2 where needed (or run live on hardware). Verify:

- `get_distance()` returns a float within expected range
- `read_accel()` returns a 3-tuple of floats
- `is_fall()` returns `True` when magnitude is injected below 0.5 or above 2.5
- `speak()` creates a cache file and does not raise

**Acceptance criteria:**
- [ ] `pytest tests/` passes with no failures
- [ ] Coverage report shows > 80% for all modules in `modules/`'
echo "  ✓ Issue 33 created"

gh issue create \
  --title "Indoor integration testing" \
  --label "testing" \
  --milestone "$M7" \
  --body 'Walk through three indoor scenarios with the fully assembled prototype:

1. Narrow corridor (< 80 cm wide)
2. Open room with furniture obstacles
3. Doorway approach

Log every alert triggered (timestamp, type, distance) to a CSV for review. Count false positives (alerts with no real obstacle) and false negatives (obstacles not detected).

**Acceptance criteria:**
- [ ] False positive rate < 5% over a 10-minute test per scenario
- [ ] All obstacles within 80 cm detected and alerted within 1.5 seconds
- [ ] CSV log committed to `docs/test_results/indoor.csv`'
echo "  ✓ Issue 34 created"

gh issue create \
  --title "Outdoor integration testing" \
  --label "testing" \
  --milestone "$M7" \
  --body 'Test on three outdoor surfaces: concrete footpath, gravel path, and grass. Repeat obstacle detection for a parked car (static) and a moving person (dynamic). Test in bright sun, overcast, and dusk lighting conditions.

**Acceptance criteria:**
- [ ] Obstacle detection works in all three lighting conditions
- [ ] No false positives triggered by ground texture variations
- [ ] Moving person detected at ≥ 1.5 m distance'
echo "  ✓ Issue 35 created"

gh issue create \
  --title "Fall detection accuracy testing: 20 controlled drops" \
  --label "testing" \
  --milestone "$M7" \
  --body 'Perform 20 controlled test drops: hold the stick upright, then let it drop 1 m onto a foam mat (simulating a user falling). Also perform a 20-minute normal walking test to check for false positives.

**Acceptance criteria:**
- [ ] Fall detected in ≥ 18/20 controlled drops (≥ 90% sensitivity)
- [ ] Zero false positives during the 20-minute normal walking test'
echo "  ✓ Issue 36 created"

gh issue create \
  --title "Obstacle detection range and latency benchmarking" \
  --label "hardware,testing" \
  --milestone "$M7" \
  --body 'Place a flat board perpendicular to the stick at distances: 30, 50, 80, 100, 150, 200, 250, 300 cm. Record time from object placement to alert sound onset for 5 trials at each distance.

**Acceptance criteria:**
- [ ] Reliable detection (5/5 trials) at all distances up to 200 cm
- [ ] Alert latency < 1.0 s at all distances up to 200 cm
- [ ] Zero false alarms at 300+ cm (above the configured threshold)'
echo "  ✓ Issue 37 created"

gh issue create \
  --title "Battery runtime test — target 4+ hour operation" \
  --label "hardware,testing" \
  --milestone "$M7" \
  --body 'Fully charge the power bank. Run `main.py` with all modules active and log the shutdown time. Measure idle current draw with a USB power meter throughout the test.

**Acceptance criteria:**
- [ ] Continuous runtime ≥ 4 hours on a 10,000 mAh power bank
- [ ] Average current draw ≤ 2.5 A at 5 V (≤ 12.5 W total)
- [ ] Results committed to `docs/test_results/battery.md`'
echo "  ✓ Issue 38 created"

gh issue create \
  --title "Low-light camera detection accuracy test" \
  --label "ml,testing" \
  --milestone "$M7" \
  --body 'Test object detection under four lighting conditions:
- Full daylight
- Indoor fluorescent
- Evening dusk (lux 10–50)
- Near-dark (lux < 5)

Use the same 5 vehicle/object targets at each condition. Log confidence scores for all detections.

**Acceptance criteria:**
- [ ] Average confidence > 0.55 in all conditions above lux 10
- [ ] Low-light performance degradation documented in `docs/known_limitations.md`'
echo "  ✓ Issue 39 created"

# ============================================================
# MILESTONE 8 — Optimization & documentation
# ============================================================

gh issue create \
  --title "Optimize inference latency via frame downscaling and threading" \
  --label "software,enhancement" \
  --milestone "$M8" \
  --body 'Profile current inference time on the RPi with `time.perf_counter()`.

- Implement frame resizing to 320×240 before passing to YOLOv8
- Compare FPS before and after resizing
- Explore ONNX runtime as an alternative backend
- Ensure the model object is cached at module import time (not per-call)
- Target: ≤ 150 ms per inference frame

**Acceptance criteria:**
- [ ] Inference time reduced by ≥ 30% vs the unoptimized baseline
- [ ] Before/after benchmarks committed to `docs/performance.md`'
echo "  ✓ Issue 40 created"

gh issue create \
  --title "Write README with full hardware and software setup guide" \
  --label "documentation" \
  --milestone "$M8" \
  --body '`README.md` must include:

- Project overview and demo GIF
- Hardware requirements with wiring diagrams or photos
- Step-by-step software setup instructions
- How to train or replace the model
- How to run the system end-to-end
- Troubleshooting for the three most common issues (camera not found, I2C device missing, audio not playing)

**Acceptance criteria:**
- [ ] A person with no prior context can follow the README to a working prototype
- [ ] README reviewed and approved in a PR by at least one other contributor'
echo "  ✓ Issue 41 created"

gh issue create \
  --title "Write CONTRIBUTING.md and GitHub issue templates" \
  --label "documentation,good first issue" \
  --milestone "$M8" \
  --body 'Create `CONTRIBUTING.md` with:
- How to fork and branch
- Code style guide (PEP8, type hints encouraged)
- How to run tests
- PR checklist

Add two issue templates in `.github/ISSUE_TEMPLATE/`:
- `bug_report.md`
- `feature_request.md`

**Acceptance criteria:**
- [ ] Both templates appear in the GitHub "New Issue" dropdown
- [ ] `CONTRIBUTING.md` reviewed and merged via PR'
echo "  ✓ Issue 42 created"

gh issue create \
  --title "Add GitHub Actions CI workflow for linting and tests" \
  --label "software,documentation" \
  --milestone "$M8" \
  --body 'Create `.github/workflows/ci.yml`. On every push and PR to `main`:

1. Run `flake8 modules/ main.py` for PEP8 compliance
2. Run `pytest tests/` with GPIO and hardware mocked

Use `ubuntu-latest` runner.

**Acceptance criteria:**
- [ ] CI passes on a clean branch with no linting errors
- [ ] CI badge added to the top of `README.md`
- [ ] Any linting failure or test failure blocks the PR from merging'
echo "  ✓ Issue 43 created"

gh issue create \
  --title "Record demo video and create animated GIF for README" \
  --label "documentation" \
  --milestone "$M8" \
  --body 'Record a 60–90 second video of the assembled prototype detecting:
1. A parked car
2. A doorway obstacle
3. A simulated fall

Extract a 10-second GIF of obstacle detection for the README header using `ffmpeg`. Upload the full video to YouTube and link from `README.md`.

**Acceptance criteria:**
- [ ] GIF under 5 MB committed to `docs/demo.gif`
- [ ] Full video linked in `README.md`
- [ ] Demo covers all three detection modes'
echo "  ✓ Issue 44 created"

gh issue create \
  --title "Write module docstrings and inline code comments" \
  --label "documentation,good first issue" \
  --milestone "$M8" \
  --body 'Every public function in every module must have a Google-style docstring covering: purpose, args, returns, raises. Every non-obvious line should have an inline comment.

Example:
```python
def get_distance() -> float | None:
    """Measure the distance to the nearest object.

    Returns:
        Distance in centimetres, or None if no echo received within timeout.

    Raises:
        RuntimeError: If GPIO has not been initialised via setup().
    """
```

Validate with: `pydocstyle modules/`

**Acceptance criteria:**
- [ ] `pydocstyle modules/` exits with no errors
- [ ] Every public function in `modules/` has a compliant docstring'
echo "  ✓ Issue 45 created"

echo ""
echo "✅ All 45 issues created successfully in $REPO"
