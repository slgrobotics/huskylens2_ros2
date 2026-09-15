#!/usr/bin/env python3
"""Publish HuskyLens 2 MCP recognition results and camera frames over ROS 2."""

import base64
import json
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
from sensor_msgs.msg import CompressedImage, Image
from std_msgs.msg import String
from vision_msgs.msg import Detection2D, Detection2DArray, ObjectHypothesisWithPose


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
        if self._sse_response is not None:
            self._sse_response.close()
        self._session.close()
        self._session = requests.Session()
        self.events = queue.Queue()
        self._endpoint = None

        response = self._session.get(
            f'{self.server_url}/sse', stream=True,
            timeout=(self.timeout, None))
        response.raise_for_status()
        self._sse_response = response
        events = self.events
        threading.Thread(
            target=self._read_events, args=(response, events), daemon=True).start()

        kind, value = events.get(timeout=self.timeout)
        if kind != 'endpoint':
            raise RuntimeError(f'Expected MCP endpoint, received {kind}: {value}')
        self._endpoint = urljoin(f'{self.server_url}/sse', value)
        self.request('initialize', {
            'protocolVersion': '2024-11-05',
            'capabilities': {},
            'clientInfo': {'name': 'huskylens2-ros2', 'version': '1.0'},
        })
        self.notify('notifications/initialized', {})

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
        payload = {'jsonrpc': '2.0', 'method': method, 'params': params}
        if request_id is not None:
            payload['id'] = request_id
        response = self._session.post(
            self._endpoint, json=payload, timeout=self.timeout)
        response.raise_for_status()

    def notify(self, method, params):
        self._post(method, params)

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
        self.declare_parameter('mcp_server', 'http://huskylens.local:3000')
        self.declare_parameter('algorithm', 'object_recognition')
        self.declare_parameter('algorithm_id', 2)
        self.declare_parameter('poll_rate', 10.0)
        self.declare_parameter('frame_id', 'huskylens2_link')
        self.declare_parameter('image_width', 640)
        self.declare_parameter('image_height', 480)
        self.declare_parameter('mcp_timeout', 15.0)

        server = self.get_parameter('mcp_server').value
        self._algorithm = self.get_parameter('algorithm').value
        self._algorithm_id = int(self.get_parameter('algorithm_id').value)
        self._poll_rate = float(self.get_parameter('poll_rate').value)
        self._frame_id = self.get_parameter('frame_id').value
        self._img_w = int(self.get_parameter('image_width').value)
        self._img_h = int(self.get_parameter('image_height').value)
        timeout = float(self.get_parameter('mcp_timeout').value)

        self._det_pub = self.create_publisher(
            Detection2DArray, 'huskylens/detections', 10)
        self._point_pub = self.create_publisher(
            Point, 'huskylens/tracked_object', 10)
        self._algo_pub = self.create_publisher(
            String, 'huskylens/algorithm', 10)
        self._image_pub = self.create_publisher(
            CompressedImage, 'huskylens/image/compressed', 10)
        self._marked_image_pub = self.create_publisher(
            Image, 'huskylens/image/marked', 10)
        self._bridge = CvBridge()

        self._responses = queue.Queue(maxsize=2)
        self._stop_event = threading.Event()
        self._client = McpClient(server, timeout)
        self.get_logger().info(f'Connecting to HuskyLens MCP server at {server}')
        self._client.connect()
        self.get_logger().info('HuskyLens MCP session established')

        self._worker = threading.Thread(target=self._request_loop, daemon=True)
        self._worker.start()
        self.create_timer(0.05, self._publish_latest)

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
                try:
                    self._responses.put_nowait(result)
                except queue.Full:
                    self._responses.get_nowait()
                    self._responses.put_nowait(result)
            except Exception as exc:
                self.get_logger().warn(
                    f'MCP request failed: {exc}', throttle_duration_sec=5.0)
                try:
                    self.get_logger().info('Reconnecting to HuskyLens MCP server')
                    self._client.connect()
                except Exception as reconnect_exc:
                    self.get_logger().warn(
                        f'MCP reconnect failed: {reconnect_exc}',
                        throttle_duration_sec=5.0)
                    self._stop_event.wait(2.0)
            self._stop_event.wait(max(0.0, period - (time.monotonic() - started)))

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
        algorithm.data = self._algorithm
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

                # Draw a white outline first so the red cross remains visible
                # over both dark and bright parts of the camera image.
                cv2.drawMarker(
                    frame, point, (255, 255, 255), cv2.MARKER_CROSS,
                    markerSize=arm * 2, thickness=arm // 3 + 3)
                cv2.drawMarker(
                    frame, point, (0, 0, 255), cv2.MARKER_CROSS,
                    markerSize=arm * 2, thickness=max(2, arm // 3))

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
