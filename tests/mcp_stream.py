import base64
import json
import queue
import threading
import time
from urllib.parse import urljoin

import cv2
import numpy as np
import requests

"""
This is a simple caller for the HuskyLens 2 MCP Server.
It uses very standard Python libraries (requests, json, base64) to avoid installing additional dependencies.
It connects to the server, initializes the session, and sends requests to retrieve the recognition result (including the image).
It displays the image in a window, marking centers of recognized objects with a red cross, with the "name" label.

How to run:

python3 mcp_stream.py

"""


BASE_URL = 'http://huskylens.local:3000'
SSE_URL = f'{BASE_URL}/sse'
ALGORITHM_ID = 2

def read_events(events):
    try:
        with requests.get(SSE_URL, stream=True, timeout=(10, 60)) as response:
            response.raise_for_status()
            kind, data = '', []
            for line in response.iter_lines(chunk_size=1, decode_unicode=True):
                if not line:
                    if data:
                        events.put((kind, '\n'.join(data)))
                        kind, data = '', []
                elif line.startswith('event:'):
                    kind = line[6:].strip()
                elif line.startswith('data:'):
                    data.append(line[5:].strip())
    except Exception as exc:
        events.put(('error', str(exc)))

def send(session, endpoint, events, method, params, ident=None):
    payload = dict(jsonrpc='2.0', method=method, params=params)
    if ident is not None:
        payload['id'] = ident
    r = session.post(endpoint, json=payload, timeout=15)
    r.raise_for_status()
    if ident is None:
        return
    while True:
        try:
            kind, raw = events.get(timeout=45)
        except queue.Empty as exc:
            raise TimeoutError(f'MCP response timed out for {method}') from exc
        if kind == 'error':
            raise RuntimeError(raw)
        try:
            value = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            continue
        if not isinstance(value, dict):
            continue
        if value.get('id') == ident:
            if 'error' in value:
                raise RuntimeError(value['error'])
            if 'result' not in value:
                continue
            return value['result']


def connect(session):
    events = queue.Queue()
    threading.Thread(target=read_events, args=(events,), daemon=True).start()
    try:
        kind, endpoint_path = events.get(timeout=15)
    except queue.Empty as exc:
        raise TimeoutError('Timed out waiting for the MCP endpoint') from exc
    if kind != 'endpoint':
        raise RuntimeError((kind, endpoint_path))
    endpoint = urljoin(SSE_URL, endpoint_path)
    send(session, endpoint, events, 'initialize', {
        'protocolVersion': '2024-11-05',
        'capabilities': {},
        'clientInfo': {'name': 'camera-stream', 'version': '1.0'},
    }, 1)
    send(session, endpoint, events, 'notifications/initialized', {})
    return endpoint, events


def select_application(session, endpoint, events, requested_name):
    application_names = {
        'object_recognition': 'Object Recognition',
        'object': 'Object Recognition',
    }
    selected = application_names.get(
        str(requested_name).strip().lower(), requested_name)
    send(session, endpoint, events, 'tools/call', {
        'name': 'self.manage_applications.switch_application',
        'arguments': {'algorithm': selected},
    }, 3)
    return selected

def recognition_items(result):
    for item in result.get('content', []):
        if item.get('type') != 'text':
            continue
        try:
            value = json.loads(item.get('text', ''))
        except (TypeError, json.JSONDecodeError):
            continue
        if isinstance(value, list):
            return value
    return []


def draw_markers(frame, items):
    height, width = frame.shape[:2]
    scale_x = width / 640.0
    scale_y = height / 480.0
    for item in items:
        center = (
            round(float(item.get('xCenter', 0)) * scale_x),
            round(float(item.get('yCenter', 0)) * scale_y),
        )
        arm = max(12, round(min(width, height) * 0.035))
        cv2.drawMarker(
            frame, center, (255, 255, 255), cv2.MARKER_CROSS,
            markerSize=arm * 2, thickness=arm // 3 + 3)
        cv2.drawMarker(
            frame, center, (0, 0, 255), cv2.MARKER_CROSS,
            markerSize=arm * 2, thickness=max(2, arm // 3))

        name = str(item.get('name', '')).strip()
        if not name:
            continue
        text_size, baseline = cv2.getTextSize(
            name, cv2.FONT_HERSHEY_SIMPLEX, 0.7, 2)
        text_x = min(center[0] + arm + 6, width - text_size[0] - 8)
        text_y = max(center[1] - arm - 6, text_size[1] + baseline + 8)
        cv2.rectangle(
            frame,
            (text_x - 4, text_y - text_size[1] - baseline - 4),
            (text_x + text_size[0] + 4, text_y + 4),
            (255, 255, 255), -1)
        cv2.putText(
            frame, name, (text_x, text_y), cv2.FONT_HERSHEY_SIMPLEX,
            0.7, (0, 0, 0), 2, cv2.LINE_AA)


def main():
    with requests.Session() as session:
        endpoint, events = connect(session)
        print(
            f'Switching HuskyLens to {ALGORITHM_ID} / object_recognition...',
            flush=True)
        selected = select_application(
            session, endpoint, events, 'object_recognition')
        print(f'Active HuskyLens application: {selected}', flush=True)

        last_time = None
        fps = 0.0
        while True:
            try:
                result = send(session, endpoint, events, 'tools/call', {
                    'name': 'self.get_recognition_result',
                    'arguments': {'algorithm': ALGORITHM_ID},
                }, 2)
            except (OSError, requests.RequestException, RuntimeError, TimeoutError) as exc:
                print(f'MCP call failed: {exc}; reconnecting...', flush=True)
                time.sleep(2)
                try:
                    endpoint, events = connect(session)
                    selected = select_application(
                        session, endpoint, events, 'object_recognition')
                    print(
                        f'Active HuskyLens application: {selected}', flush=True)
                except Exception as reconnect_exc:
                    print(
                        f'MCP reconnect failed: {reconnect_exc}; retrying...',
                        flush=True)
                    time.sleep(2)
                continue

            if not isinstance(result, dict):
                print(f'Ignoring unexpected MCP result: {result!r}', flush=True)
                continue
            image_item = next(
                (item for item in result.get('content', [])
                 if item.get('type') == 'image' and item.get('data')),
                None)
            if image_item is None:
                continue

            image_bytes = base64.b64decode(image_item['data'])
            frame = cv2.imdecode(
                np.frombuffer(image_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
            if frame is None:
                continue
            draw_markers(frame, recognition_items(result))

            now = time.monotonic()
            if last_time is not None and now > last_time:
                measured = 1.0 / (now - last_time)
                fps = measured if fps == 0.0 else 0.8 * fps + 0.2 * measured
            last_time = now
            fps_text = f'FPS: {fps:.1f}'
            text_size, baseline = cv2.getTextSize(
                fps_text, cv2.FONT_HERSHEY_SIMPLEX, 0.8, 2)
            text_x = frame.shape[1] - text_size[0] - 14
            text_y = text_size[1] + baseline + 10
            cv2.rectangle(
                frame,
                (text_x - 6, text_y - text_size[1] - baseline - 6),
                (frame.shape[1] - 6, text_y + 6),
                (255, 255, 255), -1)
            cv2.putText(
                frame, fps_text, (text_x, text_y), cv2.FONT_HERSHEY_SIMPLEX,
                0.8, (0, 0, 0), 2, cv2.LINE_AA)

            cv2.imshow('HuskyLens 2 MCP stream', frame)
            if cv2.waitKey(1) & 0xFF in (ord('q'), 27):
                break

    cv2.destroyAllWindows()


if __name__ == '__main__':
    main()

