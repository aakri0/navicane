import cv2
import time
import threading
from collections import Counter
from picamera2 import Picamera2
from ultralytics import YOLO
from gtts import gTTS
import pygame
import os
from gpiozero import DistanceSensor, Buzzer
from time import sleep
import smbus2
import math

# MPU6050 Gyroscope setup
MPU6050_ADDR = 0x68
PWR_MGMT_1 = 0x6B
GYRO_XOUT_H = 0x43
GYRO_YOUT_H = 0x45
GYRO_ZOUT_H = 0x47

# Initialize I2C bus for gyroscope
try:
    bus = smbus2.SMBus(1)
    bus.write_byte_data(MPU6050_ADDR, PWR_MGMT_1, 0)  # Wake up MPU6050
    gyroscope_available = True
    print("MPU6050 gyroscope initialized successfully")
except Exception as e:
    print(f"Gyroscope initialization failed: {e}")
    gyroscope_available = False

# Initialize hardware components
sensor = DistanceSensor(echo=27, trigger=17)
buzzer = Buzzer(23)

# Initialize camera
picam2 = Picamera2()
picam2.preview_configuration.main.size = (1280, 720)
picam2.preview_configuration.main.format = "RGB888"
picam2.preview_configuration.align()
picam2.configure("preview")
picam2.start()

# Load YOLO model
print("Loading YOLO model...")
model = YOLO("yolov8n.pt")

# Initialize pygame for audio playback
pygame.mixer.init()

# Detection parameters
detection_threshold = 1.0  # 1 meter
confidence_threshold = 0.5
buzzer_duration = 3  # seconds
last_detection_time = 0
detection_cooldown = 5  # seconds between detections

# Enhanced Elevation Detection Parameters (based on your table)
elevation_thresholds = {
    'small_step': 0.025,      # 2.5 cm vertical change
    'large_step': 0.10,       # 10 cm vertical change  
    'uneven_terrain': 0.015,  # 1.5 cm sudden difference
    'steep_slope': 10.0       # 10° pitch via gyroscope
}

# Elevation detection state
prev_distance = None
distance_history = []
last_elevation_time = 0
elevation_cooldown = 2  # seconds between elevation alerts
prev_gy = 0
gyro_history = []

# Terminal output control
gyro_print_counter = 0

def read_raw_data(addr):
    """Read raw data from MPU6050"""
    try:
        high = bus.read_byte_data(MPU6050_ADDR, addr)
        low = bus.read_byte_data(MPU6050_ADDR, addr+1)
        value = ((high << 8) | low)
        if(value > 32768):
            value = value - 65536
        return value
    except Exception as e:
        print(f"Error reading gyroscope data: {e}")
        return 0

def get_gyro_data():
    """Get gyroscope data in degrees/sec"""
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

def detect_elevation_changes(current_distance, gx, gy, gz):
    """Comprehensive elevation change detection based on your specifications"""
    global prev_distance, distance_history, gyro_history
    
    elevation_type = None
    alert_type = None
    
    # Update distance history (keep last 10 readings)
    distance_history.append(current_distance)
    if len(distance_history) > 10:
        distance_history.pop(0)
    
    # Update gyroscope history
    if gyroscope_available:
        gyro_history.append(gy)  # Track pitch changes
        if len(gyro_history) > 10:
            gyro_history.pop(0)
    
    if prev_distance is not None and len(distance_history) >= 3:
        
        # 1. Small step/drop detection (≥ 2.5 cm vertical change)
        vertical_change = abs(current_distance - prev_distance)
        if vertical_change >= elevation_thresholds['small_step']:
            elevation_type = "Small step/drop detected"
            alert_type = "short_buzzer"
            
        # 2. Large step/drop detection (≥ 10 cm vertical change)
        if vertical_change >= elevation_thresholds['large_step']:
            elevation_type = "Large step/drop detected"
            alert_type = "vibration_voice"
            
        # 3. Uneven terrain detection (≥ 1.5 cm sudden difference)
        if len(distance_history) >= 3:
            recent_changes = [abs(distance_history[i] - distance_history[i-1]) 
                            for i in range(1, len(distance_history))]
            if any(change >= elevation_thresholds['uneven_terrain'] for change in recent_changes[-3:]):
                if elevation_type is None:  # Don't override larger detections
                    elevation_type = "Uneven terrain detected"
                    alert_type = "mild_vibration"
    
    # 4. Steep slope detection (≥ 10° pitch via gyroscope)
    if gyroscope_available and abs(gy) >= elevation_thresholds['steep_slope']:
        elevation_type = "Steep slope detected"
        alert_type = "voice_alert"
        
    prev_distance = current_distance
    return elevation_type, alert_type

def handle_elevation_alert(elevation_type, alert_type):
    """Handle different types of elevation alerts based on your specifications"""
    
    if alert_type == "short_buzzer":
        # Short buzzer pulse for small steps
        def short_buzzer():
            try:
                print(f"🔔 Short buzzer pulse: {elevation_type}")
                for _ in range(3):  # 3 short pulses
                    buzzer.on()
                    sleep(0.2)
                    buzzer.off()
                    sleep(0.1)
            except Exception as e:
                print(f"Short buzzer error: {e}")
        threading.Thread(target=short_buzzer, daemon=True).start()
        
    elif alert_type == "vibration_voice":
        # Vibration + Voice alert for large steps
        def vibration_voice():
            try:
                print(f"🚨 Large elevation change: {elevation_type}")
                # Simulate vibration with rapid buzzer pulses
                for _ in range(5):
                    buzzer.on()
                    sleep(0.1)
                    buzzer.off()
                    sleep(0.1)
                
                # Voice alert
                speak_elevation_alert(elevation_type)
            except Exception as e:
                print(f"Vibration+voice error: {e}")
        threading.Thread(target=vibration_voice, daemon=True).start()
        
    elif alert_type == "voice_alert":
        # Voice alert for steep slopes
        print(f"🎤 Voice alert: {elevation_type}")
        speak_elevation_alert(elevation_type)
        
    elif alert_type == "mild_vibration":
        # Mild vibration for uneven terrain
        def mild_vibration():
            try:
                print(f"⚡ Mild vibration: {elevation_type}")
                for _ in range(2):  # 2 gentle pulses
                    buzzer.on()
                    sleep(0.3)
                    buzzer.off()
                    sleep(0.2)
            except Exception as e:
                print(f"Mild vibration error: {e}")
        threading.Thread(target=mild_vibration, daemon=True).start()

def speak_elevation_alert(elevation_type):
    """Provide voice feedback for elevation changes"""
    def speak_thread():
        try:
            if "steep slope" in elevation_type.lower():
                text = "Warning: Steep slope ahead. Proceed with caution."
            elif "large step" in elevation_type.lower():
                text = "Caution: Large elevation change detected. Watch your step."
            elif "small step" in elevation_type.lower():
                text = "Small step detected."
            elif "uneven terrain" in elevation_type.lower():
                text = "Uneven terrain ahead. Be careful."
            else:
                text = f"{elevation_type}. Watch your step."
                
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
    
    threading.Thread(target=speak_thread, daemon=True).start()

def print_gyro_values_terminal(gx, gy, gz, distance):
    """Print gyroscope values and distance in terminal with formatting"""
    global gyro_print_counter
    
    if gyro_print_counter % 10 == 0:
        timestamp = time.strftime("%H:%M:%S", time.localtime())
        gyro_status = "ACTIVE" if gyroscope_available else "DISABLED"
        
        print(f"[{timestamp}] Distance: {distance:6.2f}m | "
              f"Gyro ({gyro_status}): X: {gx:7.2f}°/s, Y: {gy:7.2f}°/s, Z: {gz:7.2f}°/s")
        
        if gyroscope_available:
            if abs(gx) > 5 or abs(gy) > 5 or abs(gz) > 5:
                print(f"    >> MOVEMENT: Roll: {gx:.1f}°/s, Pitch: {gy:.1f}°/s, Yaw: {gz:.1f}°/s")
            
            if abs(gy) > elevation_thresholds['steep_slope']:
                print(f"    >> STEEP SLOPE THRESHOLD EXCEEDED: Pitch = {gy:.1f}°/s")
        
        if distance <= detection_threshold:
            print(f"    >> PROXIMITY ALERT: Object at {distance:.2f}m")
        
        print("-" * 80)
    
    gyro_print_counter += 1

def get_distance():
    """Get distance from ultrasonic sensor in meters"""
    try:
        distance = sensor.distance
        return distance
    except Exception as e:
        print(f"Error reading sensor: {e}")
        return float('inf')

def extract_detected_objects(results):
    """Extract object names from YOLO results"""
    detected_objects = []
    if len(results) > 0 and results[0].boxes is not None:
        for box in results[0].boxes:
            class_id = int(box.cls[0])
            class_name = model.names[class_id]
            confidence = float(box.conf[0])
            if confidence >= confidence_threshold:
                detected_objects.append(class_name)
    return detected_objects

def speak_detection_results(objects_list):
    """Convert detection results to speech using gTTS"""
    if not objects_list:
        return
    
    try:
        object_counts = Counter(objects_list)
        unique_objects = list(object_counts.keys())
        total_objects = len(objects_list)

        if total_objects == 1:
            speech_text = f"Object detected: {unique_objects[0]}"
        else:
            object_descriptions = []
            for obj, count in object_counts.items():
                if count == 1:
                    object_descriptions.append(obj)
                else:
                    object_descriptions.append(f"{count} {obj}s")

            if len(unique_objects) == 1:
                speech_text = f"Objects detected: {object_descriptions[0]}"
            else:
                speech_text = f"{total_objects} objects detected: {', '.join(object_descriptions)}"

        print(f"🔊 Speaking objects: {speech_text}")

        # Wait a moment to ensure elevation alert finishes first
        time.sleep(0.5)
        
        tts = gTTS(text=speech_text, lang='en', slow=False)
        tts.save("detection_result.mp3")
        pygame.mixer.music.load("detection_result.mp3")
        pygame.mixer.music.play()

        while pygame.mixer.music.get_busy():
            pygame.time.wait(100)

        os.remove("detection_result.mp3")

    except Exception as e:
        print(f"Speech error: {e}")

print("\n" + "="*80)
print("Enhanced Elevation Detection System with Priority Alerts")
print("Elevation Detection Thresholds:")
print(f"- Small step/drop: ≥ {elevation_thresholds['small_step']*100:.1f} cm")
print(f"- Large step/drop: ≥ {elevation_thresholds['large_step']*100:.1f} cm") 
print(f"- Steep slope: ≥ {elevation_thresholds['steep_slope']:.1f}° pitch")
print(f"- Uneven terrain: ≥ {elevation_thresholds['uneven_terrain']*100:.1f} cm sudden change")
print("Priority: Elevation alerts → Object detection alerts")
print("Press 'q' to exit.")
print("="*80)

try:
    while True:
        # Get current readings
        distance = get_distance()
        current_time = time.time()
        gx, gy, gz = get_gyro_data() if gyroscope_available else (0, 0, 0)

        # Print sensor values
        print_gyro_values_terminal(gx, gy, gz, distance)

        # Priority 1: Check for elevation changes FIRST
        elevation_detected = False
        elevation_type, alert_type = detect_elevation_changes(distance, gx, gy, gz)
        
        if elevation_type and (current_time - last_elevation_time) > elevation_cooldown:
            print(f"🚨 PRIORITY ALERT: {elevation_type}")
            handle_elevation_alert(elevation_type, alert_type)
            last_elevation_time = current_time
            elevation_detected = True

        # Capture frame and run object detection
        frame = picam2.capture_array()
        results = model(frame)
        annotated_frame = results[0].plot()

        # Add enhanced display information
        cv2.putText(annotated_frame, f"Distance: {distance:.2f}m", 
                   (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)

        if gyroscope_available:
            cv2.putText(annotated_frame, f"Pitch: {gy:.1f}° Gyro: ACTIVE", 
                       (10, 70), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 0), 2)
        else:
            cv2.putText(annotated_frame, "Gyro: DISABLED", 
                       (10, 70), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)

        # Priority 2: Object detection (only if no recent elevation alert)
        if distance <= detection_threshold:
            cv2.putText(annotated_frame, "OBJECT DETECTED", 
                       (10, 110), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)

            if (current_time - last_detection_time) > detection_cooldown:
                detected_objects = extract_detected_objects(results)

                if detected_objects:
                    print(f"🎯 Object detection: {detected_objects}")
                    
                    # If elevation was just detected, add delay before object announcement
                    if elevation_detected:
                        print("⏳ Waiting for elevation alert to complete before object announcement...")
                        time.sleep(2)  # Wait for elevation alert to finish
                    
                    speak_detection_results(detected_objects)
                    last_detection_time = current_time

        # Add priority indicator to display
        if elevation_detected:
            cv2.putText(annotated_frame, "ELEVATION PRIORITY ACTIVE", 
                       (10, 150), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)

        cv2.imshow("Enhanced Elevation & Object Detection", annotated_frame)

        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

        time.sleep(0.05)

except KeyboardInterrupt:
    print("\nStopping enhanced detection system...")
finally:
    try:
        buzzer.off()
        picam2.stop()
        pygame.mixer.quit()
        cv2.destroyAllWindows()
        print("System stopped successfully.")
    except:
        pass
