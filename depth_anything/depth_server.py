#!/usr/bin/env python3

import io
import time

import cv2
import numpy as np
import torch

from PIL import Image
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import Response
from transformers import AutoImageProcessor, AutoModelForDepthEstimation


"""
Depth Anything V2 HTTP Server

This script creates a server for depth estimation using the Depth-Anything V2
model.

It must be run in an environment with a GPU (CUDA) - normally a Python
"sandboxed" virtual environment with PyTorch installed.

A ROS2 node or any other program can issue an HTTP POST request to this server
with an image.

The server loads the model once at startup, processes each input image,
performs inference, and returns the depth map as a 16-bit PNG image.

    
     ROS 2 node / other client
                 │
                 │ HTTP POST
                 │ image/jpeg or image/png
                 ▼
    ┌──────────────────────────┐
    │ Depth Anything V2 server │
    │                          │
    │ decode image             │
    │ preprocess               │
    │ CUDA inference           │
    │ resize to input size     │
    │ meters → uint16 mm       │
    │ encode PNG               │
    └────────────┬─────────────┘
                 │
                 │ HTTP response
                 │ image/png
                 ▼
          16-bit depth map


Run:

    See:
    https://github.com/slgrobotics/articubot_one/wiki/Depth-Anything-V2

    Install additional dependencies (in the venv):
        pip install fastapi uvicorn

    (venv) sergei@sergeiu7:~/husky_ws/src/huskylens2_ros2/depth_anything$ ./depth_server.py
       -- a short wait here ---
    MODEL_NAME: depth-anything/Depth-Anything-V2-Metric-Indoor-Base-hf
    Device: cuda
    GPU: NVIDIA GeForce RTX 3060 Ti
    Loading model...
    ==================================================
    Processor size    : SizeDict(height=518, width=518, longest_edge=None, shortest_edge=None,
                                 max_height=None, max_width=None, min_pixels=None, max_pixels=None)
    keep_aspect_ratio : True
    ensure_multiple_of: 14
    ==================================================
    Loading weights: 100%|██████████████| 287/287 [00:00<00:00, 1293.94it/s]
    Model loaded.
    Warming up GPU...
    GPU warm-up complete.

    Starting Depth Anything V2 server at http://127.0.0.1:5001

    INFO:     Started server process [1760635]
    INFO:     Waiting for application startup.
    INFO:     Application startup complete.
    INFO:     Uvicorn running on http://127.0.0.1:5001 (Press CTRL+C to quit)
    INFO:     127.0.0.1:34628 - "GET / HTTP/1.1" 200 OK   <- I opened http://127.0.0.1:5001/ in the browser
    INFO:     127.0.0.1:34628 - "GET /favicon.ico HTTP/1.1" 404 Not Found
    2129x1602  inference=88.1 ms  total=538.3 ms  depth=1.45-17.55 m  png=2672.8 KiB  <- I ran the test below with large test.png image
    INFO:     127.0.0.1:51672 - "POST /depth HTTP/1.1" 200 OK


Test:

    run "../tests/test_depth_server.py"

  or:  

    curl \
        -X POST \
        -H "Content-Type: image/jpeg" \
        --data-binary @test.jpeg \
        http://127.0.0.1:5001/depth \
        --output depth_16.png

    The returned PNG contains uint16 depth values in millimeters.

        1743 -> 1.743 meters

    A value of 0 is reserved for invalid depth.
"""


# ----------------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------------

MODEL_NAME = "depth-anything/Depth-Anything-V2-Metric-Indoor-Base-hf"

# MODEL_NAME = "depth-anything/Depth-Anything-V2-Metric-Outdoor-Base-hf"
# MODEL_NAME = "depth-anything/Depth-Anything-V2-Base-hf"

HOST = "127.0.0.1"
PORT = 5001

# experimental scale factor for depth values:
#DEPTH_MULTIPLIER = 1.15   # for HuskyLens 2 stock camera module
DEPTH_MULTIPLIER = 0.5  # for HuskyLens 2 wide-angle camera module


# ----------------------------------------------------------------------
# Initialize model
# ----------------------------------------------------------------------

print(f"DEPTH_MULTIPLIER: {DEPTH_MULTIPLIER}")
print(f"MODEL_NAME: {MODEL_NAME}", flush=True)

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


# ----------------------------------------------------------------------
# Warm up GPU
# ----------------------------------------------------------------------

if device == "cuda":

    print("Warming up GPU...")

    # A dummy image is sufficient to initialize CUDA kernels and allocate
    # the buffers used by the model.

    warmup_image = Image.new(
        "RGB",
        (640, 480),
        color=(0, 0, 0)
    )

    warmup_inputs = processor(
        images=warmup_image,
        return_tensors="pt"
    )

    warmup_inputs = {
        k: v.to(device)
        for k, v in warmup_inputs.items()
    }

    with torch.no_grad():
        _ = model(**warmup_inputs)

    torch.cuda.synchronize()

    print("GPU warm-up complete.")


# ----------------------------------------------------------------------
# Depth inference
# ----------------------------------------------------------------------

def estimate_depth(image):
    """
    Run Depth Anything V2 inference.

    Parameters
    ----------
    image : PIL.Image
        RGB input image.

    Returns
    -------
    depth : numpy.ndarray
        Float32 HxW depth map in meters.

    inference_ms : float
        CUDA/model inference time in milliseconds.
    """

    orig_width, orig_height = image.size

    inputs = processor(
        images=image,
        return_tensors="pt"
    )

    inputs = {
        k: v.to(device)
        for k, v in inputs.items()
    }

    if device == "cuda":
        torch.cuda.synchronize()

    start = time.perf_counter()

    with torch.no_grad():
        outputs = model(**inputs)

    if device == "cuda":
        torch.cuda.synchronize()

    inference_ms = (
        time.perf_counter() - start
    ) * 1000.0

    # Keep depth as a torch Tensor while resizing.

    depth_tensor = outputs.predicted_depth.unsqueeze(1)

    # Resize depth back to the dimensions of the original image.

    depth_tensor = torch.nn.functional.interpolate(
        depth_tensor,
        size=(orig_height, orig_width),
        mode="bicubic",
        align_corners=False,
    )

    # Convert to NumPy only after resizing.

    depth = (
        depth_tensor
        .squeeze()
        .cpu()
        .numpy()
    )

    return depth, inference_ms


# ----------------------------------------------------------------------
# Convert metric depth to 16-bit PNG
# ----------------------------------------------------------------------

def encode_depth_png(depth):
    """
    Convert floating-point depth in meters to a 16-bit PNG containing
    depth in millimeters.

    Pixel value 0 is reserved for invalid depth.
    """

    valid = np.isfinite(depth) & (depth > 0.0)

    depth_mm = np.zeros(
        depth.shape,
        dtype=np.uint16
    )

    # uint16 permits 0 ... 65535 mm.
    # Zero is reserved for invalid depth.

    depth_mm[valid] = np.clip(
        np.round(depth[valid] * 1000.0 * DEPTH_MULTIPLIER),
        1,
        65535
    ).astype(np.uint16)

    success, encoded = cv2.imencode(
        ".png",
        depth_mm
    )

    if not success:
        raise RuntimeError(
            "Failed to encode depth image as PNG"
        )

    return encoded.tobytes()


# ----------------------------------------------------------------------
# HTTP server
# ----------------------------------------------------------------------

app = FastAPI(
    title="Depth Anything V2 Server",
    description=(
        "Accepts an RGB image and returns a "
        "16-bit metric depth PNG."
    ),
    version="1.0"
)


@app.get("/")
def root():
    """
    Simple server status endpoint.
    """

    return {
        "service": "Depth Anything V2",
        "model": MODEL_NAME,
        "device": device,
        "endpoint": "/depth",
        "depth_unit": "millimeters",
    }


@app.get("/health")
def health():
    """
    Health check.
    """

    return {
        "status": "ok",
        "model": MODEL_NAME,
        "device": device,
    }


@app.post("/depth")
async def depth_endpoint(request: Request):
    """
    Accept an encoded RGB image and return a 16-bit PNG depth map.

    Request body:
        JPEG or PNG image bytes.

    Response body:
        16-bit single-channel PNG.

    Depth units:
        millimeters.
    """

    request_start = time.perf_counter()

    # --------------------------------------------------------------
    # Read HTTP request body
    # --------------------------------------------------------------

    image_bytes = await request.body()

    if not image_bytes:
        raise HTTPException(
            status_code=400,
            detail="Empty image request"
        )

    # --------------------------------------------------------------
    # Decode image
    # --------------------------------------------------------------

    try:
        image = Image.open(
            io.BytesIO(image_bytes)
        ).convert("RGB")

    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Unable to decode image: {exc}"
        )

    orig_width, orig_height = image.size

    # --------------------------------------------------------------
    # Depth Anything inference
    # --------------------------------------------------------------

    try:
        depth, inference_ms = estimate_depth(image)

    except Exception as exc:
        print(f"Inference failed: {exc}")

        raise HTTPException(
            status_code=500,
            detail=f"Depth inference failed: {exc}"
        )

    # --------------------------------------------------------------
    # Encode 16-bit depth PNG
    # --------------------------------------------------------------

    try:
        png_bytes = encode_depth_png(depth)

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"PNG encoding failed: {exc}"
        )

    total_ms = (
        time.perf_counter() - request_start
    ) * 1000.0

    min_depth = float(
        np.min(depth[np.isfinite(depth)]) * DEPTH_MULTIPLIER
    )

    max_depth = float(
        np.max(depth[np.isfinite(depth)]) * DEPTH_MULTIPLIER
    )

    print(
        f"{orig_width}x{orig_height}  "
        f"inference={inference_ms:.1f} ms  "
        f"total={total_ms:.1f} ms  "
        f"depth={min_depth:.2f} ... {max_depth:.2f} m  "
        f"png={len(png_bytes) / 1024:.1f} KiB"
    )

    # --------------------------------------------------------------
    # Return PNG
    # --------------------------------------------------------------

    return Response(
        content=png_bytes,
        media_type="image/png",
        headers={
            "X-Depth-Unit": "mm",
            "X-Depth-Encoding": "16UC1",
            "X-Image-Width": str(orig_width),
            "X-Image-Height": str(orig_height),
            "X-Inference-Time-Ms": f"{inference_ms:.1f}",
            "X-Total-Time-Ms": f"{total_ms:.1f}",
            "X-Model": MODEL_NAME,
        },
    )


# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------

if __name__ == "__main__":

    import uvicorn

    print()
    print(
        f"Starting Depth Anything V2 server "
        f"at http://{HOST}:{PORT}"
    )
    print()

    uvicorn.run(
        app,
        host=HOST,
        port=PORT,
        log_level="info"
    )
