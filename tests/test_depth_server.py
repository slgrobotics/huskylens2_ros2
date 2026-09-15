#!/usr/bin/env python3

import sys
import cv2
import numpy as np
import requests

"""
A simple test for the Depth-Anything V2 depth server: "../depth_anything/depth_server.py"

Run the server first, then run this test script. It will send a test image to the server and receive the depth map in response:

*@*:~/husky_ws/src/huskylens2_ros2/tests$ ./test_depth_server.py 
HTTP: 200
Inference: 88.1 ms
Total: 538.3 ms
Depth unit: mm
Shape: (1602, 2129)
dtype: uint16
Min: 1446 mm
Max: 17547 mm
Saved received_depth.png

"""

SERVER = "http://127.0.0.1:5001/depth"

filename = sys.argv[1] if len(sys.argv) > 1 else "test.png"

with open(filename, "rb") as f:
    image_data = f.read()

response = requests.post(
    SERVER,
    data=image_data,
    headers={"Content-Type": "image/png"},
    timeout=30,
)

response.raise_for_status()

print("HTTP:", response.status_code)
print("Inference:", response.headers.get("X-Inference-Time-Ms"), "ms")
print("Total:", response.headers.get("X-Total-Time-Ms"), "ms")
print("Depth unit:", response.headers.get("X-Depth-Unit"))

depth_mm = cv2.imdecode(
    np.frombuffer(response.content, np.uint8),
    cv2.IMREAD_UNCHANGED,
)

print("Shape:", depth_mm.shape)
print("dtype:", depth_mm.dtype)
print("Min:", depth_mm[depth_mm > 0].min(), "mm")
print("Max:", depth_mm.max(), "mm")

cv2.imwrite("received_depth.png", depth_mm)

print("Saved received_depth.png")

