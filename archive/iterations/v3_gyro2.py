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

# Gyroscope parameters
elevation_threshold = 15  # degrees/sec for elevation change detection
last_elevation_time = 0
elevation_cooldown = 3  # seconds between elevation announcements
prev_gy = 0  # Previous gyroscope Y-axis reading

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

def test_gyroscope_movement():
    """Test gyroscope response to movement and rotation"""
    print("=== GYROSCOPE MOVEMENT TEST ===")
    print("Instructions:")
    print("1. Keep device still for 5 seconds")
    print("2. Then rotate/move the device")
    print("3. Watch for changes in readings")
    print("4. Test will run automatically")
    print()
    
    if not gyroscope_available:
        print("❌ Gyroscope not available!")
        return False
    
    try:
        baseline_readings = []
        
        # Phase 1: Baseline readings (device still)
        print("Phase 1: Keep device PERFECTLY STILL for 5 seconds...")
        for i in range(50):  # 5 seconds of readings
            gx, gy, gz = get_gyro_data()
            baseline_readings.append([gx, gy, gz])
            print(f"\rStill test {i+1}/50 - X: {gx:6.1f}°/s, Y: {gy:6.1f}°/s, Z: {gz:6.1f}°/s", end="")
            time.sleep(0.1)
        
        # Calculate baseline averages
        avg_gx = sum(r[0] for r in baseline_readings) / len(baseline_readings)
        avg_gy = sum(r[1] for r in baseline_readings) / len(baseline_readings)
        avg_gz = sum(r[2] for r in baseline_readings) / len(baseline_readings)
        
        print(f"\n\nBaseline (stationary) averages:")
        print(f"X: {avg_gx:.2f}°/s, Y: {avg_gy:.2f}°/s, Z: {avg_gz:.2f}°/s")
        
        # Check if baseline is reasonable (should be close to 0)
        if abs(avg_gx) > 5 or abs(avg_gy) > 5 or abs(avg_gz) > 5:
            print("⚠️  WARNING: High baseline readings - gyroscope may need calibration")
        else:
            print("✅ Baseline readings look good")
        
        print("\nPhase 2: Now MOVE and ROTATE the device for 10 seconds...")
        print("Expected changes:")
        print("- X-axis: Roll left/right")
        print("- Y-axis: Pitch forward/backward") 
        print("- Z-axis: Yaw turn left/right")
        print()
        
        # Phase 2: Movement detection
        movement_detected = False
        max_readings = [0, 0, 0]  # Track maximum readings per axis
        
        for i in range(100):  # 10 seconds of movement testing
            gx, gy, gz = get_gyro_data()
            
            # Check for significant movement (deviation from baseline)
            delta_gx = abs(gx - avg_gx)
            delta_gy = abs(gy - avg_gy) 
            delta_gz = abs(gz - avg_gz)
            
            # Update maximum readings
            max_readings[0] = max(max_readings[0], delta_gx)
            max_readings[1] = max(max_readings[1], delta_gy)
            max_readings[2] = max(max_readings[2], delta_gz)
            
            # Detect significant movement (threshold: 10°/s change from baseline)
            if delta_gx > 10 or delta_gy > 10 or delta_gz > 10:
                movement_detected = True
                status = "🟢 MOVEMENT DETECTED!"
            else:
                status = "🔴 No significant movement"
            
            print(f"\rMovement test {i+1}/100 - X: {gx:6.1f}°/s, Y: {gy:6.1f}°/s, Z: {gz:6.1f}°/s - {status}", end="")
            time.sleep(0.1)
        
        print(f"\n\n=== TEST RESULTS ===")
        print(f"Movement detected: {'✅ YES' if movement_detected else '❌ NO'}")
        print(f"Maximum deviations from baseline:")
        print(f"X-axis: {max_readings[0]:.1f}°/s")
        print(f"Y-axis: {max_readings[1]:.1f}°/s") 
        print(f"Z-axis: {max_readings[2]:.1f}°/s")
        
        # Evaluation
        if movement_detected and max(max_readings) > 20:
            print("✅ GYROSCOPE IS WORKING PROPERLY!")
            print("   - Responds to movement")
            print("   - Good sensitivity")
            return True
        elif movement_detected:
            print("⚠️  GYROSCOPE IS WORKING BUT MAY HAVE LOW SENSITIVITY")
            print("   - Detected some movement but values are low")
            return True
        else:
            print("❌ GYROSCOPE APPEARS TO NOT BE WORKING")
            print("   - No response to movement detected")
            print("   - Check wiring and connections")
            return False
            
    except KeyboardInterrupt:
        print(f"\n\nTest stopped by user")
        return False
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        return False

def detect_elevation_change(prev_gy, threshold=15):
    """Detect elevation change based on gyroscope Y-axis (pitch) changes"""
    if not gyroscope_available:
        return False, prev_gy
    
    gx, gy, gz = get_gyro_data()
    delta_gy = abs(gy - prev_gy)
    
    if delta_gy > threshold:
        return True, gy
    else:
        return False, gy

def speak_elevation_change():
    """Provide voice feedback for elevation change"""
    def speak_thread():
        try:
            text = "Elevation change detected. Watch your step."
            print(f"Speaking: {text}")
            tts = gTTS(text=text, lang='en', slow=False)
            tts.save("elevation_change.mp3")
            pygame.mixer.music.load("elevation_change.mp3")
            pygame.mixer.music.play()
            while pygame.mixer.music.get_busy():
                time.sleep(0.1)
            os.remove("elevation_change.mp3")
        except Exception as e:
            print(f"Elevation speech error: {e}")
    
    threading.Thread(target=speak_thread, daemon=True).start()

def get_distance():
    """Get distance from ultrasonic sensor in meters"""
    try:
        distance = sensor.distance
        return distance
    except Exception as e:
        print(f"Error reading sensor: {e}")
        return float('inf')

def sound_buzzer(duration=3):
    """Sound the buzzer for specified duration"""
    def buzzer_thread():
        try:
            buzzer.on()
            sleep(duration)
            buzzer.off()
        except Exception as e:
            print(f"Buzzer error: {e}")
    
    threading.Thread(target=buzzer_thread, daemon=True).start()

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
            speech_text = f"I detected 1 object: {unique_objects[0]}"
        else:
            object_descriptions = []
            for obj, count in object_counts.items():
                if count == 1:
                    object_descriptions.append(obj)
                else:
                    object_descriptions.append(f"{count} {obj}s")

            if len(unique_objects) == 1:
                speech_text = f"I detected {object_descriptions[0]}"
            else:
                speech_text = f"I detected {total_objects} objects: {', '.join(object_descriptions)}"

        print(f"Speaking: {speech_text}")

        tts = gTTS(text=speech_text, lang='en', slow=False)
        tts.save("detection_result.mp3")
        pygame.mixer.music.load("detection_result.mp3")
        pygame.mixer.music.play()

        while pygame.mixer.music.get_busy():
            pygame.time.wait(100)

        os.remove("detection_result.mp3")

    except Exception as e:
        print(f"Speech error: {e}")

# Test gyroscope on startup
if gyroscope_available:
    print("Testing gyroscope functionality...")
    gyro_working = test_gyroscope_movement()
    if not gyro_working:
        print("⚠️  Gyroscope test failed - continuing with object detection only")
        gyroscope_available = False
    else:
        print("✅ Gyroscope test passed - elevation detection enabled")
else:
    print("Gyroscope not available - continuing with object detection only")

print("\n" + "="*60)
print("Starting integrated object detection system with elevation monitoring...")
print("System will detect objects within 1 meter and monitor elevation changes.")
print("Press 'q' to exit.")
print("="*60)

try:
    while True:
        # Get current distance
        distance = get_distance()
        current_time = time.time()

        # Check for elevation changes
        if gyroscope_available:
            elevation_changed, prev_gy = detect_elevation_change(prev_gy, elevation_threshold)
            
            if elevation_changed and (current_time - last_elevation_time) > elevation_cooldown:
                print(f"Elevation change detected! Gyro Y-axis change: {abs(prev_gy):.2f} deg/s")
                speak_elevation_change()
                last_elevation_time = current_time

        # Capture frame from camera
        frame = picam2.capture_array()

        # Run YOLO inference
        results = model(frame)

        # Draw bounding boxes, labels, and confidence
        annotated_frame = results[0].plot()

        # Add distance information to display
        cv2.putText(annotated_frame, f"Distance: {distance:.2f}m", 
                   (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)

        # Add gyroscope status to display
        if gyroscope_available:
            gx, gy, gz = get_gyro_data()
            cv2.putText(annotated_frame, f"Pitch: {gy:.1f} deg/s", 
                       (10, 110), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 0), 2)
            cv2.putText(annotated_frame, "Gyro: ACTIVE", 
                       (10, 140), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        else:
            cv2.putText(annotated_frame, "Gyro: DISABLED", 
                       (10, 110), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)

        # Check if object is within detection range
        if distance <= detection_threshold:
            cv2.putText(annotated_frame, "OBJECT DETECTED - PROCESSING", 
                       (10, 70), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)

            if (current_time - last_detection_time) > detection_cooldown:
                print(f"Object detected at {distance:.2f}m - Starting detection sequence...")

                detected_objects = extract_detected_objects(results)

                if detected_objects:
                    print(f"Detected objects: {detected_objects}")
                    print("Sounding buzzer...")
                    sound_buzzer(buzzer_duration)
                    sleep(0.5)
                    speak_detection_results(detected_objects)
                else:
                    print("Sounding buzzer...")
                    sound_buzzer(buzzer_duration)
                    sleep(0.5)
                    
                    fallback_text = "I detected an object but couldn't identify it clearly"
                    print(f"Speaking: {fallback_text}")
                    try:
                        tts = gTTS(text=fallback_text, lang='en', slow=False)
                        tts.save("fallback.mp3")
                        pygame.mixer.music.load("fallback.mp3")
                        pygame.mixer.music.play()
                        while pygame.mixer.music.get_busy():
                            pygame.time.wait(100)
                        os.remove("fallback.mp3")
                    except:
                        pass

                last_detection_time = current_time
                print("Detection sequence complete. Monitoring...")
                print("-" * 50)

        # Show the result
        cv2.imshow("YOLO Object Detection with Distance and Elevation", annotated_frame)

        # Break with 'q'
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

        # Small delay to prevent excessive CPU usage
        time.sleep(0.05)

except KeyboardInterrupt:
    print("\nStopping detection system...")
finally:
    try:
        buzzer.off()
        picam2.stop()
        pygame.mixer.quit()
        cv2.destroyAllWindows()
        print("System stopped successfully.")
    except:
        pass
