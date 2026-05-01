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

# Initialize hardware components
sensor = DistanceSensor(echo=27, trigger=17)  # Ultrasonic sensor[1]
buzzer = Buzzer(23)  # Buzzer on GPIO 23[1]

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

def get_distance():
    """Get distance from ultrasonic sensor in meters"""[1]
    try:
        distance = sensor.distance  # gpiozero returns distance in meters
        return distance
    except Exception as e:
        print(f"Error reading sensor: {e}")
        return float('inf')

def sound_buzzer(duration=3):
    """Sound the buzzer for specified duration"""[1]
    def buzzer_thread():
        try:
            buzzer.on()
            sleep(duration)
            buzzer.off()
        except Exception as e:
            print(f"Buzzer error: {e}")
    
    # Run buzzer in separate thread to avoid blocking[1]
    threading.Thread(target=buzzer_thread, daemon=True).start()

def extract_detected_objects(results):
    """Extract object names from YOLO results"""
    detected_objects = []
    if len(results) > 0 and results[0].boxes is not None:
        for box in results[0].boxes:
            # Get class name
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
        # Count unique objects
        object_counts = Counter(objects_list)
        unique_objects = list(object_counts.keys())
        total_objects = len(objects_list)
        
        # Create speech text
        if total_objects == 1:
            speech_text = f"I detected 1 object: {unique_objects[0]}"
        else:
            # Create detailed announcement
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
        
        # Generate and play speech
        tts = gTTS(text=speech_text, lang='en', slow=False)
        tts.save("detection_result.mp3")
        
        # Play the audio file
        pygame.mixer.music.load("detection_result.mp3")
        pygame.mixer.music.play()
        
        # Wait for audio to finish
        while pygame.mixer.music.get_busy():
            pygame.time.wait(100)
        
        # Clean up
        os.remove("detection_result.mp3")
        
    except Exception as e:
        print(f"Speech error: {e}")

print("Starting integrated object detection system...")
print("System will detect objects within 1 meter and announce them.")
print("Press 'q' to exit.")

try:
    while True:
        # Get current distance
        distance = get_distance()
        current_time = time.time()
        
        # Capture frame from camera
        frame = picam2.capture_array()
        
        # Run YOLO inference
        results = model(frame)
        
        # Draw bounding boxes, labels, and confidence
        annotated_frame = results[0].plot()
        
        # Add distance information to display
        cv2.putText(annotated_frame, f"Distance: {distance:.2f}m", 
                   (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
        
        # Check if object is within detection range
        if distance <= detection_threshold:
            # Add warning text to display
            cv2.putText(annotated_frame, "OBJECT DETECTED - PROCESSING", 
                       (10, 70), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
            
            # Check cooldown period to avoid repeated detections
            if (current_time - last_detection_time) > detection_cooldown:
                print(f"Object detected at {distance:.2f}m - Starting detection sequence...")
                
                # Extract detected objects
                detected_objects = extract_detected_objects(results)
                
                if detected_objects:
                    print(f"Detected objects: {detected_objects}")
                    
                    # Sound buzzer for 3 seconds
                    print("Sounding buzzer...")
                    sound_buzzer(buzzer_duration)
                    
                    # Wait a moment for buzzer to start, then announce results
                    sleep(0.5)
                    
                    # Announce results via speech
                    speak_detection_results(detected_objects)
                else:
                    # Sound buzzer and announce that something was detected but couldn't identify
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
                
                # Update last detection time
                last_detection_time = current_time
                
                print("Detection sequence complete. Monitoring...")
                print("-" * 50)
        
        # Show the result
        cv2.imshow("YOLO Object Detection with Distance", annotated_frame)
        
        # Break with 'q'
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

except KeyboardInterrupt:
    print("\nStopping detection system...")
finally:
    # Cleanup
    try:
        buzzer.off()
        picam2.stop()
        pygame.mixer.quit()
        cv2.destroyAllWindows()
        print("System stopped successfully.")
    except:
        pass
