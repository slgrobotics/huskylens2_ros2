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
MOUSE_LEAVE_EVENT = getattr(cv2, "EVENT_MOUSELEAVE", -1)


def colorize_depth(depth_mm):
    valid = depth_mm > 0
    if not np.any(valid):
        return np.zeros((*depth_mm.shape, 3), dtype=np.uint8)

    min_depth = depth_mm[valid].min()
    max_depth = depth_mm[valid].max()
    normalized = np.zeros(depth_mm.shape, dtype=np.float32)
    if max_depth > min_depth:
        normalized[valid] = (
            depth_mm[valid].astype(np.float32) - min_depth
        ) / (max_depth - min_depth)

    return cv2.applyColorMap(
        (normalized * 255.0).astype(np.uint8),
        cv2.COLORMAP_INFERNO,
    )


def update_cursor(event, x, y, _flags, cursor):
    if event == cv2.EVENT_MOUSEMOVE:
        cursor["x"] = x
        cursor["y"] = y
    elif event == MOUSE_LEAVE_EVENT:
        cursor["x"] = None
        cursor["y"] = None

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

depth_vis = colorize_depth(depth_mm)
window_name = "Received depth"
cursor = {"x": None, "y": None}

cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
cv2.resizeWindow(window_name, 1280, 720)
cv2.setMouseCallback(window_name, update_cursor, cursor)

while True:
    display = depth_vis.copy()
    height, width = depth_mm.shape[:2]

    if cursor["x"] is not None and cursor["y"] is not None:
        try:
            _window_x, _window_y, window_width, window_height = (
                cv2.getWindowImageRect(window_name)
            )
        except cv2.error:
            window_width = width
            window_height = height

        if window_width > 0 and window_height > 0:
            depth_x = round(cursor["x"] * width / window_width)
            depth_y = round(cursor["y"] * height / window_height)
            depth_x = int(np.clip(depth_x, 0, width - 1))
            depth_y = int(np.clip(depth_y, 0, height - 1))
            depth_value = int(depth_mm[depth_y, depth_x])

            display_x = round(depth_x * display.shape[1] / width)
            display_y = round(depth_y * display.shape[0] / height)
            cv2.drawMarker(
                display,
                (display_x, display_y),
                (255, 255, 255),
                cv2.MARKER_CROSS,
                20,
                2,
            )

            hover_text = (
                f"Depth: {depth_value / 1000.0:.2f} m"
                if depth_value > 0
                else "Depth: invalid"
            )
            text_size, baseline = cv2.getTextSize(
                hover_text, cv2.FONT_HERSHEY_SIMPLEX, 0.8, 2
            )
            text_x = min(display_x + 14, display.shape[1] - text_size[0] - 10)
            text_y = max(display_y - 14, text_size[1] + baseline + 10)
            cv2.rectangle(
                display,
                (text_x - 6, text_y - text_size[1] - baseline - 6),
                (text_x + text_size[0] + 6, text_y + 6),
                (255, 255, 255),
                -1,
            )
            cv2.putText(
                display,
                hover_text,
                (text_x, text_y),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.8,
                (0, 0, 0),
                2,
                cv2.LINE_AA,
            )

    cv2.putText(
        display,
        "Move cursor to inspect depth | Press q or ESC to exit",
        (20, 35),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        (255, 255, 255),
        2,
        cv2.LINE_AA,
    )
    cv2.imshow(window_name, display)
    key = cv2.waitKey(30) & 0xFF
    if key in (ord("q"), 27):
        break

cv2.destroyAllWindows()

