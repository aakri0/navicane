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

# Define the specific classes you want to detect[3]
DETECTION_CLASSES = [
    0,   # person
    1,   # bicycle
    2,   # car
    3,   # motorcycle
    5,   # bus
    7,   # truck
    11,  # stop sign
    14,  # bird
    15,  # cat
    16,  # dog
    17,  # horse
    18,  # sheep
    19,  # cow
    20,  # elephant
    21,  # bear
    22,  # zebra
    23,  # giraffe
    56,  # chair
    58,  # potted plant
    60,  # dining table
    62,  # tv
    63,  # laptop
    64,  # mouse
    65,  # remote
    66,  # keyboard
    67,  # cell phone
    68,  # microwave
    69,  # oven
    70,  # toaster
    72,  # refrigerator
]

# Create class categories for better announcements
CLASS_CATEGORIES = {
    'person': [0],
    'vehicles': [1, 2, 3, 5, 7],
    'electronics': [62, 63, 64, 65, 66, 67, 68, 69, 70, 72],
    'furniture': [56, 60],
    'animals': [14, 15, 16, 17, 18, 19, 20, 21, 22, 23],
    'plants': [58],
    'signs': [11]
}

# MPU6050 Gyroscope setup
MPU6050_ADDR = 0x68
PWR_MGMT_1 = 0x6B
GYRO_XOUT_H = 0x43
GYRO_YOUT_H = 0x45
GYRO_ZOUT_H = 0x47

# Initialize I2C bus for gyroscope
try:
    bus = smbus2.SMBus(1)
    bus.write_byte_data(MPU6050_ADDR, PWR_MGMT_1, 0)
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

# Print available classes for reference[3]
print("Available YOLO classes:")
for class_id in DETECTION_CLASSES:
    print(f"  {class_id}: {model.names[class_id]}")
print()

# Initialize pygame for audio playback
pygame.mixer.init()

# Detection parameters
detection_threshold = 1.0
confidence_threshold = 0.5
buzzer_duration = 3
last_detection_time = 0
detection_cooldown = 5

# Enhanced Elevation Detection Parameters
elevation_thresholds = {
    'small_step': 0.025,
    'large_step': 0.10,
    'uneven_terrain': 0.015,
    'steep_slope': 10.0
}

# Elevation detection state
prev_distance = None
distance_history = []
last_elevation_time = 0
elevation_cooldown = 2
prev_gy = 0
gyro_history = []
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

def categorize_detected_objects(detected_objects):
    """Categorize detected objects for better announcements"""
    categorized = {}
    
    for obj_name in detected_objects:
        # Find which category this object belongs to
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

def detect_elevation_changes(current_distance, gx, gy, gz):
    """Comprehensive elevation change detection"""
    global prev_distance, distance_history, gyro_history
    
    elevation_type = None
    alert_type = None
    
    distance_history.append(current_distance)
    if len(distance_history) > 10:
        distance_history.pop(0)
    
    if gyroscope_available:
        gyro_history.append(gy)
        if len(gyro_history) > 10:
            gyro_history.pop(0)
    
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
        
    prev_distance = current_distance
    return elevation_type, alert_type

def handle_elevation_alert(elevation_type, alert_type):
    """Handle different types of elevation alerts"""
    
    if alert_type == "short_buzzer":
        def short_buzzer():
            try:
                print(f"🔔 Short buzzer pulse: {elevation_type}")
                for _ in range(3):
                    buzzer.on()
                    sleep(0.2)
                    buzzer.off()
                    sleep(0.1)
            except Exception as e:
                print(f"Short buzzer error: {e}")
        threading.Thread(target=short_buzzer, daemon=True).start()
        
    elif alert_type == "vibration_voice":
        def vibration_voice():
            try:
                print(f"🚨 Large elevation change: {elevation_type}")
                for _ in range(5):
                    buzzer.on()
                    sleep(0.1)
                    buzzer.off()
                    sleep(0.1)
                speak_elevation_alert(elevation_type)
            except Exception as e:
                print(f"Vibration+voice error: {e}")
        threading.Thread(target=vibration_voice, daemon=True).start()
        
    elif alert_type == "voice_alert":
        print(f"🎤 Voice alert: {elevation_type}")
        speak_elevation_alert(elevation_type)
        
    elif alert_type == "mild_vibration":
        def mild_vibration():
            try:
                print(f"⚡ Mild vibration: {elevation_type}")
                for _ in range(2):
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
    """Print gyroscope values and distance in terminal"""
    global gyro_print_counter
    
    if gyro_print_counter % 10 == 0:
        timestamp = time.strftime("%H:%M:%S", time.localtime())
        gyro_status = "ACTIVE" if gyroscope_available else "DISABLED"
        
        print(f"[{timestamp}] Distance: {distance:6.2f}m | "
              f"Gyro ({gyro_status}): X: {gx:7.2f}°/s, Y: {gy:7.2f}°/s, Z: {gz:7.2f}°/s")
        
        if gyroscope_available and (abs(gx) > 5 or abs(gy) > 5 or abs(gz) > 5):
            print(f"    >> MOVEMENT: Roll: {gx:.1f}°/s, Pitch: {gy:.1f}°/s, Yaw: {gz:.1f}°/s")
        
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
    """Extract object names from YOLO results with class filtering[2][4]"""
    detected_objects = []
    if len(results) > 0 and results[0].boxes is not None:
        for box in results[0].boxes:
            class_id = int(box.cls[0])
            # Only include objects from our specified classes
            if class_id in DETECTION_CLASSES:
                class_name = model.names[class_id]
                confidence = float(box.conf[0])
                if confidence >= confidence_threshold:
                    detected_objects.append(class_name)
    return detected_objects

def speak_detection_results(objects_list):
    """Convert detection results to speech with categorized announcements"""
    if not objects_list:
        return
    
    try:
        # Categorize the objects
        categorized = categorize_detected_objects(objects_list)
        
        if not categorized:
            return
        
        # Create categorized speech
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
        
        speech_text = f"Detected: {', '.join(category_announcements)}"
        print(f"🔊 Speaking objects: {speech_text}")

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
print("Filtered Object Detection System")
print("Detecting only specified categories:")
print("- People, Vehicles, Electronics, Furniture, Animals, Plants, Signs")
print("Total classes monitored:", len(DETECTION_CLASSES))
print("="*80)

try:
    while True:
        distance = get_distance()
        current_time = time.time()
        gx, gy, gz = get_gyro_data() if gyroscope_available else (0, 0, 0)

        print_gyro_values_terminal(gx, gy, gz, distance)

        elevation_detected = False
        elevation_type, alert_type = detect_elevation_changes(distance, gx, gy, gz)
        
        if elevation_type and (current_time - last_elevation_time) > elevation_cooldown:
            print(f"🚨 PRIORITY ALERT: {elevation_type}")
            handle_elevation_alert(elevation_type, alert_type)
            last_elevation_time = current_time
            elevation_detected = True

        # Capture frame and run filtered object detection[2][4]
        frame = picam2.capture_array()
        results = model(frame, classes=DETECTION_CLASSES, conf=confidence_threshold)
        annotated_frame = results[0].plot()

        cv2.putText(annotated_frame, f"Distance: {distance:.2f}m", 
                   (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
        cv2.putText(annotated_frame, f"Filtered Classes: {len(DETECTION_CLASSES)}", 
                   (10, 70), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 0), 2)

        if distance <= detection_threshold:
            cv2.putText(annotated_frame, "OBJECT DETECTED", 
                       (10, 110), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)

            if (current_time - last_detection_time) > detection_cooldown:
                detected_objects = extract_detected_objects(results)

                if detected_objects:
                    print(f"🎯 Filtered object detection: {detected_objects}")
                    
                    if elevation_detected:
                        print("⏳ Waiting for elevation alert to complete...")
                        time.sleep(2)
                    
                    speak_detection_results(detected_objects)
                    last_detection_time = current_time

        if elevation_detected:
            cv2.putText(annotated_frame, "ELEVATION PRIORITY ACTIVE", 
                       (10, 150), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)

        cv2.imshow("Filtered Object Detection System", annotated_frame)

        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

        time.sleep(0.05)

except KeyboardInterrupt:
    print("\nStopping filtered detection system...")
finally:
    try:
        buzzer.off()
        picam2.stop()
        pygame.mixer.quit()
        cv2.destroyAllWindows()
        print("System stopped successfully.")
    except:
        pass
