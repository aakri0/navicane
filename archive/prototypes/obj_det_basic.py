import cv2
from picamera2 import Picamera2
from ultralytics import YOLO

# Initialize the camera
picam2 = Picamera2()
picam2.preview_configuration.main.size = (1280, 720)
picam2.preview_configuration.main.format = "RGB888"
picam2.preview_configuration.align()
picam2.configure("preview")
picam2.start()

# Load YOLO model (downloads yolov8n.pt or yolo11n.pt if not present)
model = YOLO("yolov8n.pt")  # or "yolo11n.pt"

while True:
    # Capture frame from camera
    frame = picam2.capture_array()
    # Run YOLO inference
    results = model(frame)
    # Draw bounding boxes, labels, and confidence
    annotated_frame = results[0].plot()
    # Show the result
    cv2.imshow("YOLO Object Detection", annotated_frame)
    # Break with 'q'
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cv2.destroyAllWindows()
