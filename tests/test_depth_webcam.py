#!/usr/bin/env python3

import time

import cv2
import numpy as np
import requests


"""
Test client for the Depth Anything V2 HTTP server.

Captures images from a webcam, encodes them as JPEG, sends them to the
depth server, receives a 16-bit PNG depth map, and displays a colorized
depth image.

The client waits for each server response before sending the next image,
so requests cannot accumulate in a queue.

Press:
    q or ESC    Quit
"""


SERVER = "http://127.0.0.1:5001/depth"

CAMERA_ID = 0

CAMERA_WIDTH = 1280
CAMERA_HEIGHT = 720

JPEG_QUALITY = 90

# Maximum time to wait for the complete HTTP response.
REQUEST_TIMEOUT = 5.0


def colorize_depth(depth_mm):
    """
    Convert a uint16 depth image in millimeters to an 8-bit color
    visualization.

    Zero is treated as invalid depth.
    """

    valid = depth_mm > 0

    if not np.any(valid):
        return np.zeros(
            (depth_mm.shape[0], depth_mm.shape[1], 3),
            dtype=np.uint8
        )

    min_depth = depth_mm[valid].min()
    max_depth = depth_mm[valid].max()

    depth_normalized = np.zeros(
        depth_mm.shape,
        dtype=np.float32
    )

    if max_depth > min_depth:
        depth_normalized[valid] = (
            depth_mm[valid].astype(np.float32) - min_depth
        ) / (max_depth - min_depth)

    depth_u8 = (
        depth_normalized * 255.0
    ).astype(np.uint8)

    return cv2.applyColorMap(
        depth_u8,
        cv2.COLORMAP_INFERNO
    )


def main():

    print(f"Depth server: {SERVER}")
    print(f"Opening camera {CAMERA_ID}...")

    camera = cv2.VideoCapture(CAMERA_ID)

    if not camera.isOpened():
        raise RuntimeError(
            f"Unable to open camera {CAMERA_ID}"
        )

    camera.set(
        cv2.CAP_PROP_FRAME_WIDTH,
        CAMERA_WIDTH
    )

    camera.set(
        cv2.CAP_PROP_FRAME_HEIGHT,
        CAMERA_HEIGHT
    )

    actual_width = int(
        camera.get(cv2.CAP_PROP_FRAME_WIDTH)
    )

    actual_height = int(
        camera.get(cv2.CAP_PROP_FRAME_HEIGHT)
    )

    actual_fps = camera.get(cv2.CAP_PROP_FPS)

    print(
        f"Camera: {actual_width}x{actual_height} "
        f"@ {actual_fps:.1f} FPS"
    )

    #
    # Reuse the HTTP connection between requests.
    #
    session = requests.Session()

    window_name = "Depth Anything V2"

    cv2.namedWindow(
        window_name,
        cv2.WINDOW_NORMAL
    )

    cv2.resizeWindow(
        window_name,
        1280,
        720
    )

    frame_count = 0

    try:

        while True:

            # ------------------------------------------------------
            # Capture camera image
            # ------------------------------------------------------

            success, frame = camera.read()

            if not success:
                print("Camera capture failed.")
                break

            frame_count += 1

            # ------------------------------------------------------
            # Encode image as JPEG
            # ------------------------------------------------------

            encode_start = time.perf_counter()

            success, jpeg = cv2.imencode(
                ".jpg",
                frame,
                [
                    cv2.IMWRITE_JPEG_QUALITY,
                    JPEG_QUALITY
                ]
            )

            if not success:
                print("JPEG encoding failed.")
                continue

            encode_ms = (
                time.perf_counter() - encode_start
            ) * 1000.0

            # ------------------------------------------------------
            # Send image to server
            # ------------------------------------------------------

            request_start = time.perf_counter()

            try:

                response = session.post(
                    SERVER,
                    data=jpeg.tobytes(),
                    headers={
                        "Content-Type": "image/jpeg"
                    },
                    timeout=REQUEST_TIMEOUT,
                )

                response.raise_for_status()

            except requests.Timeout:

                print(
                    f"Frame {frame_count}: "
                    f"server timeout after "
                    f"{REQUEST_TIMEOUT:.1f} seconds"
                )

                continue

            except requests.RequestException as exc:

                print(
                    f"Frame {frame_count}: "
                    f"HTTP error: {exc}"
                )

                # Don't hammer an unavailable server.
                time.sleep(0.5)

                continue

            round_trip_ms = (
                time.perf_counter() - request_start
            ) * 1000.0

            # ------------------------------------------------------
            # Decode returned 16-bit PNG
            # ------------------------------------------------------

            decode_start = time.perf_counter()

            depth_mm = cv2.imdecode(
                np.frombuffer(
                    response.content,
                    dtype=np.uint8
                ),
                cv2.IMREAD_UNCHANGED,
            )

            decode_ms = (
                time.perf_counter() - decode_start
            ) * 1000.0

            if depth_mm is None:

                print(
                    f"Frame {frame_count}: "
                    "unable to decode server response"
                )

                continue

            if depth_mm.dtype != np.uint16:

                print(
                    f"Frame {frame_count}: "
                    f"unexpected depth type "
                    f"{depth_mm.dtype}"
                )

                continue

            # ------------------------------------------------------
            # Depth statistics
            # ------------------------------------------------------

            valid = depth_mm > 0

            if np.any(valid):

                min_depth = (
                    depth_mm[valid].min() / 1000.0
                )

                max_depth = (
                    depth_mm[valid].max() / 1000.0
                )

                center_depth = (
                    depth_mm[
                        depth_mm.shape[0] // 2,
                        depth_mm.shape[1] // 2
                    ] / 1000.0
                )

            else:

                min_depth = 0.0
                max_depth = 0.0
                center_depth = 0.0

            # ------------------------------------------------------
            # Colorize depth for display
            # ------------------------------------------------------

            depth_vis = colorize_depth(depth_mm)

            # ------------------------------------------------------
            # Display information
            # ------------------------------------------------------

            server_inference = response.headers.get(
                "X-Inference-Time-Ms",
                "?"
            )

            server_total = response.headers.get(
                "X-Total-Time-Ms",
                "?"
            )

            client_fps = (
                1000.0 / round_trip_ms
                if round_trip_ms > 0
                else 0.0
            )

            cv2.putText(
                depth_vis,
                f"HTTP: {round_trip_ms:.1f} ms  "
                f"({client_fps:.1f} FPS)",
                (20, 35),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (255, 255, 255),
                2,
                cv2.LINE_AA,
            )

            cv2.putText(
                depth_vis,
                f"Server inference: {server_inference} ms",
                (20, 65),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (255, 255, 255),
                2,
                cv2.LINE_AA,
            )

            cv2.putText(
                depth_vis,
                f"Server total: {server_total} ms",
                (20, 95),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (255, 255, 255),
                2,
                cv2.LINE_AA,
            )

            cv2.putText(
                depth_vis,
                f"Depth: {min_depth:.2f} - "
                f"{max_depth:.2f} m",
                (20, 125),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (255, 255, 255),
                2,
                cv2.LINE_AA,
            )

            cv2.putText(
                depth_vis,
                f"Center: {center_depth:.2f} m",
                (20, 155),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (255, 255, 255),
                2,
                cv2.LINE_AA,
            )

            # Center marker.
            center_x = depth_vis.shape[1] // 2
            center_y = depth_vis.shape[0] // 2

            cv2.drawMarker(
                depth_vis,
                (center_x, center_y),
                (255, 255, 255),
                cv2.MARKER_CROSS,
                20,
                1,
            )

            cv2.imshow(
                window_name,
                depth_vis
            )

            # ------------------------------------------------------
            # Console statistics
            # ------------------------------------------------------

            print(
                f"{frame_count:5d}  "
                f"JPEG={encode_ms:5.1f} ms  "
                f"HTTP={round_trip_ms:6.1f} ms  "
                f"decode={decode_ms:5.1f} ms  "
                f"inference={server_inference} ms  "
                f"center={center_depth:.2f} m"
            )

            # ------------------------------------------------------
            # Keyboard
            # ------------------------------------------------------

            key = cv2.waitKey(1) & 0xFF

            if key == ord("q") or key == 27:
                break

    finally:

        camera.release()
        session.close()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
