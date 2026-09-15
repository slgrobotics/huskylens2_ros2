#!/usr/bin/env python3

import time
import cv2
import numpy as np
import torch
from PIL import Image
from transformers import AutoImageProcessor, AutoModelForDepthEstimation

"""
This script demonstrates how to use the Depth-Anything V2 model for depth estimation on a single image.
It loads the model, processes the input image, performs inference, and saves the depth map in various formats (NumPy array, 16-bit PNG, and a visualized JPEG).
It must be run in an environment with a GPU (CUDA) - normally a Python "sandboxed" virtual environment with PyTorch installed.

See https://github.com/slgrobotics/articubot_one/wiki/Depth-Anything-V2

"""

MODEL_NAME = "depth-anything/Depth-Anything-V2-Metric-Indoor-Base-hf"
#MODEL_NAME = "depth-anything/Depth-Anything-V2-Metric-Outdoor-Base-hf"
#MODEL_NAME = "depth-anything/Depth-Anything-V2-Base-hf"

print(f"MODEL_NAME: {MODEL_NAME}")

device = "cuda" if torch.cuda.is_available() else "cpu"

print(f"Device: {device}")

if device == "cuda":
    print(f"GPU: {torch.cuda.get_device_name(0)}")

print("Loading model...")

processor = AutoImageProcessor.from_pretrained(MODEL_NAME)

print("==================================================")
print("Processor size    :", processor.size)
print("keep_aspect_ratio :", processor.keep_aspect_ratio)
print("ensure_multiple_of:", processor.ensure_multiple_of)
print("==================================================")

model = AutoModelForDepthEstimation.from_pretrained(
    MODEL_NAME
).to(device)

model.eval()

print("Model loaded.")

image = Image.open("test.png").convert("RGB")
#image = Image.open("test.jpeg").convert("RGB")

orig_width, orig_height = image.size
print(f"Original shape: {orig_width}x{orig_height}")

inputs = processor(images=image, return_tensors="pt")
inputs = {k: v.to(device) for k, v in inputs.items()}


# Warm up GPU
with torch.no_grad():
    _ = model(**inputs)

torch.cuda.synchronize() if device == "cuda" else None

start = time.perf_counter()

with torch.no_grad():
    outputs = model(**inputs)

torch.cuda.synchronize() if device == "cuda" else None

elapsed = time.perf_counter() - start

# if not resizing:
#depth = outputs.predicted_depth.squeeze().cpu().numpy()

# Keep it as a torch Tensor for resizing
depth_tensor = outputs.predicted_depth.unsqueeze(1)

print(f"Inference time: {elapsed * 1000:.1f} ms")
print(f"Depth shape: {depth_tensor.shape}")
print(f"Minimum depth: {depth_tensor.min():.2f} m")
print(f"Maximum depth: {depth_tensor.max():.2f} m")

print(f"Resized depth shape: {depth_tensor.shape}")

depth_tensor = torch.nn.functional.interpolate(
    depth_tensor,
    size=(orig_height, orig_width),
    mode="bicubic",
    align_corners=False,
)

# Convert to NumPy only after resizing
depth = depth_tensor.squeeze().cpu().numpy()
print(f"Center depth: {depth[depth.shape[0] // 2, depth.shape[1] // 2]:.2f} m")

# Exact floating-point model result
np.save("depth.npy", depth)
print("Saved depth.npy")

# Machine-readable 16-bit depth image, millimeters (16UC1 - ROS convention)
depth_mm = np.round(depth * 1000.0).astype(np.uint16)
cv2.imwrite("depth_16.png", depth_mm)
print("Saved depth_16.png")

# Produce a visualization.
depth_vis = depth.copy()

depth_vis -= depth_vis.min()

if depth_vis.max() > 0:
    depth_vis /= depth_vis.max()

depth_vis = (depth_vis * 255).astype(np.uint8)
depth_vis = cv2.applyColorMap(depth_vis, cv2.COLORMAP_INFERNO)

cv2.imwrite("depth.jpg", depth_vis)

print("Saved depth.jpg")
