#!/usr/bin/env python3
"""Publish HuskyLens 2 MCP recognition results and camera frames over ROS 2."""

import base64
import json
import math
import queue
import threading
import time
from urllib.parse import urljoin

import requests
import rclpy
import cv2
from cv_bridge import CvBridge
from geometry_msgs.msg import Point
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from sensor_msgs.msg import CameraInfo, CompressedImage, Image
from std_msgs.msg import String
from vision_msgs.msg import Detection2D, Detection2DArray, ObjectHypothesisWithPose

algorithm_id_to_name = {
            1: 'Face Recognition',
            2: 'Object Recognition',
            3: 'Line Tracking',
            4: 'Color Recognition',
            5: 'Tag Recognition',
            6: 'Gesture Recognition',
            7: 'Pose Recognition',
            8: 'Hand Tracking',
            9: 'OCR',
            10: 'QR Code',
            11: 'Barcode',
        }

camera_module_fov = {
    'stock': (49.12, 38.69),
    'wide_angle': (107.6, 72.6),
}

class McpClient:
    """Small requests-based MCP client using the server's SSE transport."""

    def __init__(self, server_url, timeout):
        self.server_url = server_url.rstrip('/')
        self.timeout = timeout
        self.events = queue.Queue()
        self._next_id = 1
        self._session = requests.Session()
        self._sse_response = None
        self._endpoint = None

    def connect(self):
        self.close()
        session = requests.Session()
        events = queue.Queue()
        response = None
        try:
            # Bound both phases: connecting and waiting for the SSE headers.
            response = session.get(
                f'{self.server_url}/sse', stream=True,
                timeout=(self.timeout, self.timeout))
            response.raise_for_status()
            self._session = session
            self.events = events
            self._sse_response = response
            self._endpoint = None
            self._next_id = 1
            threading.Thread(
                target=self._read_events,
                args=(response, events),
                daemon=True,
            ).start()

            kind, value = events.get(timeout=self.timeout)
            if kind != 'endpoint':
                raise RuntimeError(
                    f'Expected MCP endpoint, received {kind}: {value}')
            self._endpoint = urljoin(f'{self.server_url}/sse', value)
            self.request('initialize', {
                'protocolVersion': '2024-11-05',
                'capabilities': {},
                'clientInfo': {'name': 'huskylens2-ros2', 'version': '1.0'},
            })
            self.notify('notifications/initialized', {})
        except Exception:
            response.close() if response is not None else None
            session.close()
            self._sse_response = None
            self._endpoint = None
            raise

    def _read_events(self, response, events):
        kind = ''
        data = []
        try:
            for line in response.iter_lines(
                    chunk_size=1, decode_unicode=True):
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

    def _post(self, method, params, request_id=None):
        if self._endpoint is None:
            raise RuntimeError('MCP session is not connected')
        payload = {'jsonrpc': '2.0', 'method': method, 'params': params}
        if request_id is not None:
            payload['id'] = request_id
        response = self._session.post(
            self._endpoint, json=payload, timeout=self.timeout)
        response.raise_for_status()

    def notify(self, method, params):
        self._post(method, params)

    def select_application(self, algorithm_id):
        self.request(
            'tools/call', {
                'name': 'self.manage_applications.switch_application',
                'arguments': {'algorithm': algorithm_id},
            })
        # Determine the algorithm name from the ID for publishing to the ROS 2 topic.
        algorithm_name = algorithm_id_to_name.get(algorithm_id, f'Unknown algorithm ({algorithm_id})')
        return algorithm_name

    def request(self, method, params):
        request_id = self._next_id
        self._next_id += 1
        self._post(method, params, request_id)
        deadline = time.monotonic() + self.timeout
        while time.monotonic() < deadline:
            kind, raw = self.events.get(
                timeout=max(0.1, deadline - time.monotonic()))
            if kind == 'error':
                raise RuntimeError(raw)
            if kind != 'message':
                continue
            value = json.loads(raw)
            if value.get('id') != request_id:
                continue
            if 'error' in value:
                raise RuntimeError(value['error'])
            return value.get('result', {})
        raise TimeoutError(f'MCP request {request_id} timed out')

    def close(self):
        if self._sse_response is not None:
            self._sse_response.close()
        self._session.close()
        self._sse_response = None
        self._endpoint = None


class HuskyLens2McpNode(Node):

    def __init__(self):
        super().__init__('huskylens_mcp_node')
        self.declare_parameter('camera_module', 'stock')  # stock or wide_angle
        self.declare_parameter('mcp_server', 'http://huskylens.local:3000')
        self.declare_parameter('algorithm_id', 2)
        self.declare_parameter('poll_rate', 10.0)  # actual MCP response rate: about 1 Hz
        self.declare_parameter('frame_id', 'huskylens2_link')
        self.declare_parameter('image_width', 640)
        self.declare_parameter('image_height', 480)
        self.declare_parameter('mcp_timeout', 5.0)

        self._camera_module = str(
            self.get_parameter('camera_module').value).strip().lower()
        server = self.get_parameter('mcp_server').value
        self._algorithm_id = int(self.get_parameter('algorithm_id').value)
        self._poll_rate = float(self.get_parameter('poll_rate').value)
        self._frame_id = self.get_parameter('frame_id').value
        self._img_w = int(self.get_parameter('image_width').value)
        self._img_h = int(self.get_parameter('image_height').value)
        timeout = float(self.get_parameter('mcp_timeout').value)
        self._status_timeout = max(timeout, 0.1)

        if self._camera_module not in camera_module_fov:
            valid_modules = ', '.join(camera_module_fov)
            raise ValueError(
                f'Unknown camera_module {self._camera_module!r}; '
                f'expected one of: {valid_modules}')

        self.get_logger().info(f'Camera module configured: {self._camera_module}'
                               f' (FOV: {camera_module_fov[self._camera_module][0]}°W x {camera_module_fov[self._camera_module][1]}°H)')

        self._det_pub = self.create_publisher(
            Detection2DArray, 'huskylens/detections', 10)
        self._point_pub = self.create_publisher(
            Point, 'huskylens/tracked_object', 10)
        self._algo_pub = self.create_publisher(
            String, 'huskylens/algorithm', 10)
        self._status_pub = self.create_publisher(
            String, 'huskylens/status', 10)
        self._image_pub = self.create_publisher(
            CompressedImage, 'huskylens/image/compressed', 10)
        self._marked_image_pub = self.create_publisher(
            Image, 'huskylens/image/marked', 10)
        self._camera_info_pub = self.create_publisher(
            CameraInfo, 'huskylens/camera_info', 10)
        self._bridge = CvBridge()
        self._last_marked_time = None
        self._marked_fps = 0.0
        self._last_request_success = None

        self._responses = queue.Queue(maxsize=2)
        self._stop_event = threading.Event()
        self._client = McpClient(server, timeout)
        self.get_logger().info(f'Connecting to HuskyLens MCP server at {server}')
        self._client.connect()
        self._algorithm_name = self._client.select_application(self._algorithm_id)
        self.get_logger().info(f'Active HuskyLens application: {self._algorithm_name}')
        self.get_logger().info('HuskyLens MCP session established')

        self._worker = threading.Thread(target=self._request_loop, daemon=True)
        self._worker.start()
        self.create_timer(0.05, self._publish_latest)
        self.create_timer(0.5, self._publish_status)
        self._camera_info = self._create_camera_info()

    def _create_camera_info(self):
        horizontal_fov, vertical_fov = camera_module_fov[self._camera_module]
        focal_x = (self._img_w / 2.0) / math.tan(
            math.radians(horizontal_fov / 2.0))
        focal_y = (self._img_h / 2.0) / math.tan(
            math.radians(vertical_fov / 2.0))
        center_x = self._img_w / 2.0
        center_y = self._img_h / 2.0

        camera_info = CameraInfo()
        camera_info.header.frame_id = self._frame_id
        camera_info.width = self._img_w
        camera_info.height = self._img_h
        camera_info.distortion_model = 'plumb_bob'
        camera_info.d = [0.0] * 5
        camera_info.k = [
            focal_x, 0.0, center_x,
            0.0, focal_y, center_y,
            0.0, 0.0, 1.0,
        ]
        camera_info.r = [
            1.0, 0.0, 0.0,
            0.0, 1.0, 0.0,
            0.0, 0.0, 1.0,
        ]
        camera_info.p = [
            focal_x, 0.0, center_x, 0.0,
            0.0, focal_y, center_y, 0.0,
            0.0, 0.0, 1.0, 0.0,
        ]
        return camera_info

    def _request_loop(self):
        period = 1.0 / max(self._poll_rate, 0.1)
        while not self._stop_event.is_set():
            started = time.monotonic()
            try:
                result = self._client.request(
                    'tools/call', {
                        'name': 'self.get_recognition_result',
                        'arguments': {'algorithm': self._algorithm_id},
                    })
                self._last_request_success = time.monotonic()
                try:
                    self._responses.put_nowait(result)
                except queue.Full:
                    self._responses.get_nowait()
                    self._responses.put_nowait(result)
            except Exception as exc:
                self.get_logger().warn(
                    f'MCP request failed: {exc}', throttle_duration_sec=5.0)
                self._reconnect()
            self._stop_event.wait(max(0.0, period - (time.monotonic() - started)))

    def _publish_status(self):
        status = String()
        last_success = self._last_request_success
        status.data = (
            'up'
            if last_success is not None
            and time.monotonic() - last_success <= self._status_timeout
            else 'down'
        )
        self._status_pub.publish(status)

    def _reconnect(self):
        self.get_logger().info('Reconnecting to HuskyLens MCP server')
        delay = 1.0
        while not self._stop_event.is_set():
            try:
                self._client.connect()
                self._algorithm_name = self._client.select_application(
                    self._algorithm_id)
                self.get_logger().info(
                    f'Active HuskyLens application: {self._algorithm_name}')
                self.get_logger().info('HuskyLens MCP session re-established')
                return
            except Exception as exc:
                self.get_logger().warn(
                    f'MCP reconnect failed: {exc}; retrying in {delay:.1f}s',
                    throttle_duration_sec=5.0)
                self._stop_event.wait(delay)
                delay = min(delay * 2.0, 10.0)

    @staticmethod
    def _json_items(result):
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

    def _publish_latest(self):
        latest = None
        while True:
            try:
                latest = self._responses.get_nowait()
            except queue.Empty:
                break
        if latest is None:
            return

        stamp = self.get_clock().now().to_msg()
        self._camera_info.header.stamp = stamp
        self._camera_info_pub.publish(self._camera_info)
        detections = self._json_items(latest)
        det_array = Detection2DArray()
        det_array.header.stamp = stamp
        det_array.header.frame_id = self._frame_id
        primary = None

        for item in detections:
            x = float(item.get('xCenter', 0))
            y = float(item.get('yCenter', 0))
            detection = Detection2D()
            detection.header = det_array.header
            detection.bbox.center.position.x = x
            detection.bbox.center.position.y = y
            detection.bbox.size_x = float(item.get('width', 0))
            detection.bbox.size_y = float(item.get('height', 0))
            detection.id = str(item.get('id', 0))
            hypothesis = ObjectHypothesisWithPose()
            hypothesis.hypothesis.class_id = str(item.get('name', ''))
            hypothesis.hypothesis.score = 1.0
            detection.results.append(hypothesis)
            det_array.detections.append(detection)
            if primary is None or int(item.get('id', 0)) < int(primary.get('id', 0)):
                primary = item
        self._det_pub.publish(det_array)

        if primary is not None:
            point = Point()
            point.x = (float(primary.get('xCenter', 0)) - self._img_w / 2) / (self._img_w / 2)
            point.y = (float(primary.get('yCenter', 0)) - self._img_h / 2) / (self._img_h / 2)
            self._point_pub.publish(point)

        algorithm = String()
        algorithm.data = self._algorithm_name
        self._algo_pub.publish(algorithm)
        self._publish_image(latest, stamp)
        self._publish_marked_image(latest, stamp, detections)

    def _publish_image(self, result, stamp):
        for item in result.get('content', []):
            if item.get('type') != 'image' or not item.get('data'):
                continue
            image = CompressedImage()
            image.header.stamp = stamp
            image.header.frame_id = self._frame_id
            image.format = item.get('mimeType', 'image/jpeg').split('/')[-1]
            image.data = base64.b64decode(item['data'])
            self._image_pub.publish(image)
            break

    def _publish_marked_image(self, result, stamp, detections):
        for item in result.get('content', []):
            if item.get('type') != 'image' or not item.get('data'):
                continue
            compressed = CompressedImage()
            compressed.header.stamp = stamp
            compressed.header.frame_id = self._frame_id
            compressed.format = item.get('mimeType', 'image/jpeg').split('/')[-1]
            compressed.data = base64.b64decode(item['data'])

            try:
                frame = self._bridge.compressed_imgmsg_to_cv2(
                    compressed, desired_encoding='bgr8')
            except Exception as exc:
                self.get_logger().warn(
                    f'Could not decode image for marked topic: {exc}',
                    throttle_duration_sec=10.0)
                return

            frame_height, frame_width = frame.shape[:2]
            scale_x = frame_width / float(self._img_w)
            scale_y = frame_height / float(self._img_h)
            for detection in detections:
                center_x = round(float(detection.get('xCenter', 0)) * scale_x)
                center_y = round(float(detection.get('yCenter', 0)) * scale_y)
                arm = max(12, round(min(frame_width, frame_height) * 0.035))
                point = (center_x, center_y)
                name = str(detection.get('name', '')).strip()

                # Draw a white outline first so the red cross remains visible
                # over both dark and bright parts of the camera image.
                cv2.drawMarker(
                    frame, point, (255, 255, 255), cv2.MARKER_CROSS,
                    markerSize=arm * 2, thickness=arm // 3 + 3)
                cv2.drawMarker(
                    frame, point, (0, 0, 255), cv2.MARKER_CROSS,
                    markerSize=arm * 2, thickness=max(2, arm // 3))

                if name:
                    label_origin = (center_x + arm + 6, center_y - arm - 6)
                    label_size, label_baseline = cv2.getTextSize(
                        name, cv2.FONT_HERSHEY_SIMPLEX, 0.7, 2)
                    label_x, label_y = label_origin
                    label_x = min(label_x, frame_width - label_size[0] - 8)
                    label_y = max(label_y, label_size[1] + label_baseline + 8)
                    cv2.rectangle(
                        frame,
                        (label_x - 4, label_y - label_size[1] - label_baseline - 4),
                        (label_x + label_size[0] + 4, label_y + 4),
                        (255, 255, 255), -1)
                    cv2.putText(
                        frame, name, (label_x, label_y),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 2,
                        cv2.LINE_AA)

            now = time.monotonic()
            if self._last_marked_time is not None:
                interval = now - self._last_marked_time
                if interval > 0:
                    measured_fps = 1.0 / interval
                    if self._marked_fps == 0.0:
                        self._marked_fps = measured_fps
                    else:
                        self._marked_fps = (
                            0.8 * self._marked_fps + 0.2 * measured_fps)
            self._last_marked_time = now

            fps_text = f'FPS: {self._marked_fps:.1f}'
            fps_size, fps_baseline = cv2.getTextSize(
                fps_text, cv2.FONT_HERSHEY_SIMPLEX, 0.8, 2)
            fps_x = frame_width - fps_size[0] - 14
            fps_y = fps_size[1] + fps_baseline + 10
            cv2.rectangle(
                frame,
                (fps_x - 6, fps_y - fps_size[1] - fps_baseline - 6),
                (frame_width - 6, fps_y + 6),
                (255, 255, 255), -1)
            cv2.putText(
                frame, fps_text, (fps_x, fps_y),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 0), 2,
                cv2.LINE_AA)

            marked = self._bridge.cv2_to_imgmsg(frame, encoding='bgr8')
            marked.header = compressed.header
            self._marked_image_pub.publish(marked)
            break

    def destroy_node(self):
        self._stop_event.set()
        self._client.close()
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = None
    try:
        node = HuskyLens2McpNode()
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        if node is not None:
            node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
