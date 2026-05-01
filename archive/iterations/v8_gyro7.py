import cv2
import time
import threading
from collections import Counter
from picamera2 import Picamera2
from ultralytics import YOLO
from gtts import gTTS
import pygame
import os
from gpiozero import DistanceSensor, OutputDevice
from time import sleep
import smbus2

# ===========================
# PIN CONNECTIONS SUMMARY
# ===========================
# Top Ultrasonic Sensor (Head Level)
#   VCC  -> Pi 5V (Pin 2 or 4)
#   GND  -> Pi GND (Pin 6 or 9)
#   Trig -> GPIO17 (Pin 11)
#   Echo -> GPIO27 (Pin 13)
# Bottom Ultrasonic Sensor (Ground Level)
#   VCC  -> Pi 5V (shared)
#   GND  -> Pi GND (shared)
#   Trig -> GPIO22 (Pin 15)
#   Echo -> GPIO24 (Pin 18)
# MPU6050 Gyroscope (I2C)
#   VCC  -> Pi 3.3V (Pin 1)
#   GND  -> Pi GND (Pin 6)
#   SDA  -> GPIO2 (Pin 3)
#   SCL  -> GPIO3 (Pin 5)
# Buzzer (via BC557 PNP transistor)
#   Emitter   -> Pi 3.3V (Pin 1)
#   Collector -> Buzzer (+)
#   Buzzer (–) -> Pi GND
#   Base      -> GPIO4 (Pin 7)
# ===========================

# Detection classes (COCO indices)
DETECTION_CLASSES = [
    0, 1, 2, 3, 5, 7, 11, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 56, 58, 60,
    62, 63, 64, 65, 66, 67, 68, 69, 70, 72
]
CLASS_CATEGORIES = {
    'person': [0],
    'vehicles': [1, 2, 3, 5, 7],
    'electronics': [62, 63, 64, 65, 66, 67, 68, 69, 70, 72],
    'furniture': [56, 60],
    'animals': [14, 15, 16, 17, 18, 19, 20, 21, 22, 23],
    'plants': [58],
    'signs': [11]
}

# Gyroscope (MPU6050) setup
MPU6050_ADDR = 0x68
PWR_MGMT_1 = 0x6B
GYRO_XOUT_H = 0x43
GYRO_YOUT_H = 0x45
GYRO_ZOUT_H = 0x47
try:
    bus = smbus2.SMBus(1)
    bus.write_byte_data(MPU6050_ADDR, PWR_MGMT_1, 0)
    gyroscope_available = True
except Exception as e:
    print(f"Gyroscope initialization failed: {e}")
    gyroscope_available = False

# Initialize sensors and peripherals
sensor_top = DistanceSensor(echo=27, trigger=17)      # Top (head-level)
sensor_bottom = DistanceSensor(echo=24, trigger=22)   # Bottom (ground-level)
buzzer = OutputDevice(4, active_high=False, initial_value=True)  # GPIO4, active-low for PNP

picam2 = Picamera2()
picam2.preview_configuration.main.size = (1280, 720)
picam2.preview_configuration.main.format = "RGB888"
picam2.preview_configuration.align()
picam2.configure("preview")
picam2.start()
pygame.mixer.init()
model = YOLO("yolov8n.pt")

# Parameters
detection_threshold = 1.0
confidence_threshold = 0.5
buzzer_duration = 3
last_detection_time = 0
last_elevation_time = 0
elevation_cooldown = 2

# Elevation detection thresholds
elevation_thresholds = {
    'small_step': 0.025,
    'large_step': 0.10,
    'uneven_terrain': 0.015,
    'steep_slope': 10.0
}
prev_distance_top = None
prev_distance_bottom = None
distance_history_top = []
distance_history_bottom = []
gyro_print_counter = 0

def read_raw_data(addr):
    try:
        high = bus.read_byte_data(MPU6050_ADDR, addr)
        low = bus.read_byte_data(MPU6050_ADDR, addr+1)
        value = ((high << 8) | low)
        if value > 32768:
            value = value - 65536
        return value
    except Exception as e:
        print(f"Error reading gyroscope data: {e}")
        return 0

def get_gyro_data():
    if not gyroscope_available:
        return 0, 0, 0
    try:
        gx = read_raw_data(GYRO_XOUT_H) / 131.0
        gy = read_raw_data(GYRO_YOUT_H) / 131.0
        gz = read_raw_data(GYRO_ZOUT_H) / 131.0
        return gx, gy, gz
    except Exception as e:
        print(f"Error getting gyroscope data: {e}")
        return 0, 0, 0

def categorize_detected_objects(detected_objects):
    categorized = {}
    for obj_name in detected_objects:
        obj_class_id = None
        for class_id, class_name in model.names.items():
            if class_name == obj_name:
                obj_class_id = class_id
                break
        if obj_class_id is not None:
            for category, class_ids in CLASS_CATEGORIES.items():
                if obj_class_id in class_ids:
                    if category not in categorized:
                        categorized[category] = []
                    categorized[category].append(obj_name)
                    break
    return categorized

def detect_elevation_changes(current_distance, prev_distance, distance_history, gx, gy, gz):
    elevation_type = None
    alert_type = None
    distance_history.append(current_distance)
    if len(distance_history) > 10:
        distance_history.pop(0)
    if prev_distance is not None and len(distance_history) >= 3:
        vertical_change = abs(current_distance - prev_distance)
        if vertical_change >= elevation_thresholds['small_step']:
            elevation_type = "Small step/drop detected"
            alert_type = "short_buzzer"
        if vertical_change >= elevation_thresholds['large_step']:
            elevation_type = "Large step/drop detected"
            alert_type = "vibration_voice"
        if len(distance_history) >= 3:
            recent_changes = [abs(distance_history[i] - distance_history[i-1])
                              for i in range(1, len(distance_history))]
            if any(change >= elevation_thresholds['uneven_terrain'] for change in recent_changes[-3:]):
                if elevation_type is None:
                    elevation_type = "Uneven terrain detected"
                    alert_type = "mild_vibration"
    if gyroscope_available and abs(gy) >= elevation_thresholds['steep_slope']:
        elevation_type = "Steep slope detected"
        alert_type = "voice_alert"
    return elevation_type, alert_type

def handle_elevation_alert(elevation_type, alert_type, level):
    # level: "head" or "ground"
    def speak_thread():
        try:
            if level == "head":
                prefix = "Warning: Obstacle ahead at head level. "
            else:
                prefix = "Warning: Obstacle ahead at ground level. "
            if "steep slope" in elevation_type.lower():
                text = prefix + "Steep slope ahead. Proceed with caution."
            elif "large step" in elevation_type.lower():
                text = prefix + "Large elevation change detected. Watch your step."
            elif "small step" in elevation_type.lower():
                text = prefix + "Small step detected."
            elif "uneven terrain" in elevation_type.lower():
                text = prefix + "Uneven terrain ahead. Be careful."
            else:
                text = prefix + elevation_type
            print(f"🔊 Speaking elevation: {text}")
            tts = gTTS(text=text, lang='en', slow=False)
            tts.save("elevation_alert.mp3")
            pygame.mixer.music.load("elevation_alert.mp3")
            pygame.mixer.music.play()
            while pygame.mixer.music.get_busy():
                time.sleep(0.1)
            os.remove("elevation_alert.mp3")
        except Exception as e:
            print(f"Elevation speech error: {e}")

    def short_buzzer():
        for _ in range(3):
            buzzer.on()
            sleep(0.2)
            buzzer.off()
            sleep(0.1)

    def vibration_voice():
        for _ in range(5):
            buzzer.on()
            sleep(0.1)
            buzzer.off()
            sleep(0.1)
        speak_thread()

    def mild_vibration():
        for _ in range(2):
            buzzer.on()
            sleep(0.3)
            buzzer.off()
            sleep(0.2)

    if alert_type == "short_buzzer":
        threading.Thread(target=short_buzzer, daemon=True).start()
    elif alert_type == "vibration_voice":
        threading.Thread(target=vibration_voice, daemon=True).start()
    elif alert_type == "voice_alert":
        threading.Thread(target=speak_thread, daemon=True).start()
    elif alert_type == "mild_vibration":
        threading.Thread(target=mild_vibration, daemon=True).start()

def print_gyro_values_terminal(gx, gy, gz, distance_top, distance_bottom):
    global gyro_print_counter
    if gyro_print_counter % 10 == 0:
        timestamp = time.strftime("%H:%M:%S", time.localtime())
        gyro_status = "ACTIVE" if gyroscope_available else "DISABLED"
        print(f"[{timestamp}] Top: {distance_top:6.2f}m | Bottom: {distance_bottom:6.2f}m | "
              f"Gyro ({gyro_status}): X: {gx:7.2f}°/s, Y: {gy:7.2f}°/s, Z: {gz:7.2f}°/s")
        print("-" * 80)
    gyro_print_counter += 1

def extract_detected_objects(results):
    detected_objects = []
    if len(results) > 0 and results[0].boxes is not None:
        for box in results[0].boxes:
            class_id = int(box.cls[0])
            if class_id in DETECTION_CLASSES:
                class_name = model.names[class_id]
                confidence = float(box.conf[0])
                if confidence >= confidence_threshold:
                    detected_objects.append(class_name)
    return detected_objects

def speak_detection_results(objects_list, level):
    if not objects_list:
        return
    try:
        categorized = categorize_detected_objects(objects_list)
        if not categorized:
            return
        category_announcements = []
        for category, objects in categorized.items():
            object_counts = Counter(objects)
            if len(object_counts) == 1:
                obj, count = list(object_counts.items())[0]
                if count == 1:
                    category_announcements.append(f"1 {obj}")
                else:
                    category_announcements.append(f"{count} {obj}s")
            else:
                obj_descriptions = []
                for obj, count in object_counts.items():
                    if count == 1:
                        obj_descriptions.append(obj)
                    else:
                        obj_descriptions.append(f"{count} {obj}s")
                category_announcements.append(f"{category}: {', '.join(obj_descriptions)}")
        if level == "head":
            prefix = "At head level: "
        else:
            prefix = "At ground level: "
        speech_text = prefix + f"Detected: {', '.join(category_announcements)}"
        print(f"🔊 Speaking objects: {speech_text}")
        tts = gTTS(text=speech_text, lang='en', slow=False)
        tts.save("detection_result.mp3")
        pygame.mixer.music.load("detection_result.mp3")
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            pygame.time.wait(100)
        os.remove("detection_result.mp3")
    except Exception as e:
        print(f"Speech error: {e}")

def main():
    global prev_distance_top, prev_distance_bottom, last_detection_time, last_elevation_time
    global gyro_print_counter
    try:
        while True:
            distance_top = sensor_top.distance
            distance_bottom = sensor_bottom.distance
            current_time = time.time()
            gx, gy, gz = get_gyro_data() if gyroscope_available else (0, 0, 0)
            print_gyro_values_terminal(gx, gy, gz, distance_top, distance_bottom)

            # Elevation detection (priority: top sensor)
            elevation_type_top, alert_type_top = detect_elevation_changes(
                distance_top, prev_distance_top, distance_history_top, gx, gy, gz)
            elevation_type_bottom, alert_type_bottom = detect_elevation_changes(
                distance_bottom, prev_distance_bottom, distance_history_bottom, gx, gy, gz)
            prev_distance_top = distance_top
            prev_distance_bottom = distance_bottom

            elevation_detected = False
            elevation_level = None

            if elevation_type_top and (current_time - last_elevation_time) > elevation_cooldown:
                print(f"Elevation alert (head level): {elevation_type_top}")
                handle_elevation_alert(elevation_type_top, alert_type_top, "head")
                last_elevation_time = current_time
                elevation_detected = True
                elevation_level = "head"
            elif elevation_type_bottom and (current_time - last_elevation_time) > elevation_cooldown:
                print(f"Elevation alert (ground level): {elevation_type_bottom}")
                handle_elevation_alert(elevation_type_bottom, alert_type_bottom, "ground")
                last_elevation_time = current_time
                elevation_detected = True
                elevation_level = "ground"

            # Object detection
            frame = picam2.capture_array()
            results = model(frame, classes=DETECTION_CLASSES, conf=confidence_threshold)
            annotated_frame = results[0].plot()

            cv2.putText(annotated_frame, f"Top: {distance_top:.2f}m", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
            cv2.putText(annotated_frame, f"Bottom: {distance_bottom:.2f}m", (10, 70), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 200, 255), 2)

            # Proximity and alert logic (priority: top sensor)
            if (distance_top <= detection_threshold or distance_bottom <= detection_threshold) and (current_time - last_detection_time) > 5:
                detected_objects = extract_detected_objects(results)
                if detected_objects:
                    print(f"Detected objects: {detected_objects}")
                    # If elevation alert active, wait before object announcement
                    if elevation_detected:
                        time.sleep(2)
                    if distance_top <= detection_threshold:
                        speak_detection_results(detected_objects, "head")
                    elif distance_bottom <= detection_threshold:
                        speak_detection_results(detected_objects, "ground")
                    last_detection_time = current_time

            if elevation_detected:
                cv2.putText(annotated_frame, "ELEVATION ALERT ACTIVE", (10, 110), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)

            cv2.imshow("Blind Stick Object Detection", annotated_frame)

            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
            time.sleep(0.05)
    except KeyboardInterrupt:
        print("Exiting...")
    finally:
        buzzer.off()
        picam2.stop()
        pygame.mixer.quit()
        cv2.destroyAllWindows()

if __name__ == '__main__':
    main()
