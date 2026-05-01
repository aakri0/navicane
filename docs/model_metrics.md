# Model Evaluation — Indian Roads Detection (YOLOv8s)

> Evaluated on the validation split (436 images, 869 instances).
> Training was performed on a Tesla T4 GPU via Google Colab.

## Overall Metrics

| Metric | Value |
|---|---|
| **Precision** | 0.854 |
| **Recall** | 0.616 |
| **mAP50** | 0.731 |
| **mAP50-95** | 0.454 |
| **Fitness** | 0.482 |

## Per-Class Breakdown

| Class | Images | Instances | Precision | Recall | mAP50 | mAP50-95 |
|---|---|---|---|---|---|---|
| **Ambulance** | 24 | 27 | 0.769 | 0.741 | 0.770 | 0.679 |
| **Bus** | 63 | 71 | 0.872 | 0.549 | 0.695 | 0.393 |
| **Car** | 245 | 463 | 0.893 | 0.758 | 0.849 | 0.439 |
| **Tempo** | 97 | 120 | 0.821 | 0.342 | 0.568 | 0.312 |
| **Tractor** | 22 | 27 | 0.916 | 0.630 | 0.722 | 0.393 |
| **Truck** | 128 | 161 | 0.851 | 0.675 | 0.781 | 0.510 |

## Model Architecture

| Parameter | Value |
|---|---|
| Base model | YOLOv8s |
| Fused layers | 72 |
| Parameters | 11,127,906 |
| GFLOPs | 28.4 |
| Training image size | 800×800 |
| Training epochs | 50 (patience=20) |
| Batch size | 8 |

## Inference Speed (Tesla T4 GPU)

| Stage | Time (ms) |
|---|---|
| Preprocess | 1.48 |
| Inference | 14.61 |
| Postprocess | 1.55 |
| **Total** | **~17.6** |

> **Note:** Inference on Raspberry Pi 4 (CPU) is significantly slower
> (~4000 ms at 1280×720). Downscaling to 320×240 is recommended
> for real-time use (see Issue #40).

## Dataset

- **Source:** [Indian Roads Detection v7](https://universe.roboflow.com/indian-road-dataset/indian-roads-detection) (Roboflow)
- **Training images:** ~1,700
- **Validation images:** 436
- **Classes:** 6 (Ambulance, Bus, Car, Tempo, Tractor, Truck)
- **Format:** YOLOv8 annotation format

## Analysis

### Strengths
- **Cars** have the best detection rate (mAP50 = 0.849) — largest class with 463 instances
- **Precision is high across all classes** (> 0.77) — few false positives
- **Ambulance** detection is strong (mAP50 = 0.770) despite only 27 training instances

### Weaknesses
- **Tempo** has the lowest recall (0.342) and mAP50 (0.568) — likely due to visual similarity with trucks and buses
- **Overall recall is moderate** (0.616) — the model misses ~38% of objects
- **Dataset imbalance**: Car has 17× more instances than Ambulance/Tractor

### Recommendations
1. Increase training epochs to 75–100 (current patience=20 may have caused early stopping)
2. Apply data augmentation (mosaic, mixup) specifically for underrepresented classes
3. Consider adding more Tempo and Tractor training images via Roboflow augmentation
4. Export to ONNX or TFLite for faster RPi inference
