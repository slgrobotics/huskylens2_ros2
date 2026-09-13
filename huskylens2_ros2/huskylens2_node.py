#!/usr/bin/env python3
"""
huskylens_node.py
ROS 2 node for the HuskyLens 2 (DFRobot SEN0638 / Product 3118 Plus Kit).

Original (and credits to): https://github.com/irayfuego/robotica/blob/main/src/huskylens2_ros2/huskylens2_ros2/huskylens_node.py

Publishes the camera detections as standard ROS messages.

Subscriptions:
    /huskylens/set_algorithm  (std_msgs/String)  - changes the algorithm at runtime
                               Values: 'face', 'object', 'line', 'color',
                                        'tag', 'gesture', 'pose', 'qrcode', etc.

Publications:
    /huskylens/detections     (vision_msgs/Detection2DArray)  - results
    /huskylens/tracked_object (geometry_msgs/Point)           - center of the main object
    /huskylens/algorithm      (std_msgs/String)               - active algorithm

Parameters:
    i2c_bus      (int)    1        - I2C bus (usually 1 on RPi4)
    i2c_address  (int)    0x32     - camera I2C address
    algorithm    (string) 'object_recognition'
    poll_rate    (float)  10.0     - camera read rate in Hz
    frame_id     (string) 'camera_link'
    image_width  (int)    320      - reference resolution for normalization
    image_height (int)    240

Notes about the MCP Server (HuskyLens 2 Plus Kit with Wi-Fi):
    This node uses the I2C connection to publish to ROS 2.
    The MCP server is built into the device firmware and is accessed
    over Wi-Fi directly from Claude Desktop or other LLM clients.

    MCP setup on the device:
        1. Settings -> WiFi -> connect to your network
        2. Settings -> MCP Server -> Enable
        3. Note the IP shown on the screen
        4. In Claude Desktop, add the following to claude_desktop_config.json:
           {
             "mcpServers": {
               "huskylens": {
                 "url": "http://<CAMERA_IP>/mcp"
               }
             }
           }

    Available MCP tools:
        - get_recognition_result  -> live photo + labels
        - manage_applications     -> list/switch algorithms
        - multimedia_control      -> take a photo
        - task_scheduler          -> schedule actions by trigger
"""

import math
from types import SimpleNamespace

import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node

from geometry_msgs.msg import Point
from std_msgs.msg import String
from vision_msgs.msg import Detection2D, Detection2DArray, ObjectHypothesisWithPose

try:
    import pyhuskylens as pyhuskylens_module
    from pyhuskylens import HuskyLens
    _HAS_PYHUSKYLENS = True
except ImportError:  # pragma: no cover - fallback only for environments without the library
    pyhuskylens_module = None
    HuskyLens = None
    _HAS_PYHUSKYLENS = False

if _HAS_PYHUSKYLENS:
    _ALGO_MAP = {
        'face': getattr(pyhuskylens_module, 'ALGORITHM_FACE_RECOGNITION', None),
        'face_recognition': getattr(pyhuskylens_module, 'ALGORITHM_FACE_RECOGNITION', None),
        'object': getattr(pyhuskylens_module, 'ALGORITHM_OBJECT_RECOGNITION', None),
        'object_recognition': getattr(pyhuskylens_module, 'ALGORITHM_OBJECT_RECOGNITION', None),
        'tracking': getattr(pyhuskylens_module, 'ALGORITHM_OBJECT_TRACKING', None),
        'object_tracking': getattr(pyhuskylens_module, 'ALGORITHM_OBJECT_TRACKING', None),
        'line': getattr(pyhuskylens_module, 'ALGORITHM_LINE_TRACKING', None),
        'line_tracking': getattr(pyhuskylens_module, 'ALGORITHM_LINE_TRACKING', None),
        'color': getattr(pyhuskylens_module, 'ALGORITHM_COLOR_RECOGNITION', None),
        'color_recognition': getattr(pyhuskylens_module, 'ALGORITHM_COLOR_RECOGNITION', None),
        'tag': getattr(pyhuskylens_module, 'ALGORITHM_TAG_RECOGNITION', None),
        'tag_recognition': getattr(pyhuskylens_module, 'ALGORITHM_TAG_RECOGNITION', None),
        'gesture': getattr(pyhuskylens_module, 'ALGORITHM_GESTURE_RECOGNITION', None),
        'gesture_recognition': getattr(pyhuskylens_module, 'ALGORITHM_GESTURE_RECOGNITION', None),
        'pose': getattr(pyhuskylens_module, 'ALGORITHM_POSE_RECOGNITION', None),
        'pose_recognition': getattr(pyhuskylens_module, 'ALGORITHM_POSE_RECOGNITION', None),
        'hand': getattr(pyhuskylens_module, 'ALGORITHM_HAND_RECOGNITION', None),
        'hand_recognition': getattr(pyhuskylens_module, 'ALGORITHM_HAND_RECOGNITION', None),
        'ocr': getattr(pyhuskylens_module, 'ALGORITHM_OCR_RECOGNITION', None),
        'ocr_recognition': getattr(pyhuskylens_module, 'ALGORITHM_OCR_RECOGNITION', None),
        'qr': getattr(pyhuskylens_module, 'ALGORITHM_QRCODE_RECOGNITION', None),
        'qrcode': getattr(pyhuskylens_module, 'ALGORITHM_QRCODE_RECOGNITION', None),
        'qrcode_recognition': getattr(pyhuskylens_module, 'ALGORITHM_QRCODE_RECOGNITION', None),
        'barcode': getattr(pyhuskylens_module, 'ALGORITHM_BARCODE_RECOGNITION', None),
        'barcode_recognition': getattr(pyhuskylens_module, 'ALGORITHM_BARCODE_RECOGNITION', None),
    }
    _ALGO_MAP = {k: v for k, v in _ALGO_MAP.items() if v is not None}
    ALGO_NAMES = {v: k for k, v in _ALGO_MAP.items()}
else:
    from huskylens2_ros2.dfrobot_huskylens_i2c import (
        HuskyLensI2C, ALGO_NAMES,
        ALGO_FACE_RECOGNITION, ALGO_OBJECT_TRACKING, ALGO_OBJECT_RECOGNITION,
        ALGO_LINE_TRACKING, ALGO_COLOR_RECOGNITION, ALGO_TAG_RECOGNITION,
        ALGO_GESTURE_RECOGNITION, ALGO_POSE_RECOGNITION, ALGO_HAND_RECOGNITION,
        ALGO_OCR_RECOGNITION, ALGO_QRCODE_RECOGNITION, ALGO_BARCODE_RECOGNITION,
    )

    _ALGO_MAP = {
        'face':         ALGO_FACE_RECOGNITION,
        'face_recognition': ALGO_FACE_RECOGNITION,
        'object':       ALGO_OBJECT_RECOGNITION,
        'object_recognition': ALGO_OBJECT_RECOGNITION,
        'tracking':     ALGO_OBJECT_TRACKING,
        'object_tracking': ALGO_OBJECT_TRACKING,
        'line':         ALGO_LINE_TRACKING,
        'line_tracking': ALGO_LINE_TRACKING,
        'color':        ALGO_COLOR_RECOGNITION,
        'color_recognition': ALGO_COLOR_RECOGNITION,
        'tag':          ALGO_TAG_RECOGNITION,
        'tag_recognition': ALGO_TAG_RECOGNITION,
        'gesture':      ALGO_GESTURE_RECOGNITION,
        'gesture_recognition': ALGO_GESTURE_RECOGNITION,
        'pose':         ALGO_POSE_RECOGNITION,
        'pose_recognition': ALGO_POSE_RECOGNITION,
        'hand':         ALGO_HAND_RECOGNITION,
        'hand_recognition': ALGO_HAND_RECOGNITION,
        'ocr':          ALGO_OCR_RECOGNITION,
        'ocr_recognition': ALGO_OCR_RECOGNITION,
        'qr':           ALGO_QRCODE_RECOGNITION,
        'qrcode':       ALGO_QRCODE_RECOGNITION,
        'qrcode_recognition': ALGO_QRCODE_RECOGNITION,
        'barcode':      ALGO_BARCODE_RECOGNITION,
        'barcode_recognition': ALGO_BARCODE_RECOGNITION,
    }


class HuskyLens2Node(Node):

    def __init__(self):
        super().__init__('huskylens_node')

        # --- Parameters ------------------------------------------------------
        self.declare_parameter('i2c_bus',     1)
        self.declare_parameter('i2c_address', 0x32)
        self.declare_parameter('algorithm',   'object_recognition')
        self.declare_parameter('poll_rate',   10.0)
        self.declare_parameter('frame_id',    'camera_link')
        self.declare_parameter('image_width',  640)
        self.declare_parameter('image_height', 480)

        bus      = self.get_parameter('i2c_bus').value
        addr     = self.get_parameter('i2c_address').value
        algo_str = self.get_parameter('algorithm').value
        rate     = self.get_parameter('poll_rate').value
        self._frame_id = self.get_parameter('frame_id').value
        self._img_w    = self.get_parameter('image_width').value
        self._img_h    = self.get_parameter('image_height').value

        self.get_logger().info(f'HuskyLens 2 ROS 2 node starting with algorithm: "{algo_str}" @ {rate:.0f} Hz')
        self.get_logger().info(f'I2C bus: {bus}, address: 0x{addr:02X}, frame_id: {self._frame_id}, image size: {self._img_w}x{self._img_h}')

        # --- I2C connection ---------------------------------------------------
        self.get_logger().info(f'Connecting to HuskyLens 2 on I2C bus={bus} addr=0x{addr:02X}...')
        try:
            if _HAS_PYHUSKYLENS:
                self._hl = HuskyLens(bus)
                self._using_pyhuskylens = True
            else:
                self._hl = HuskyLensI2C(bus, addr)
                self._using_pyhuskylens = False
                if not self._hl.begin():
                    self.get_logger().error('Could not communicate with the HuskyLens 2. '
                                            'Check the I2C wiring and address.')
                    raise RuntimeError('HuskyLens init failed')
            self.get_logger().info('[OK] HuskyLens 2 connected')
        except Exception as e:
            self.get_logger().error(f'[ERROR] Connection error: {e}')
            raise

        # --- Initial algorithm -------------------------------------------------
        self._current_algo_id   = _ALGO_MAP.get(algo_str, ALGO_OBJECT_RECOGNITION)
        self._current_algo_name = algo_str
        self._set_algorithm(self._current_algo_id)

        # --- Publishers --------------------------------------------------------
        self._det_pub   = self.create_publisher(
            Detection2DArray, 'huskylens/detections', 10)
        self._point_pub = self.create_publisher(
            Point, 'huskylens/tracked_object', 10)
        self._algo_pub  = self.create_publisher(
            String, 'huskylens/algorithm', 1)

        # --- Subscribers -------------------------------------------------------
        self.create_subscription(
            String, 'huskylens/set_algorithm', self._on_set_algorithm, 5)

        # --- Polling timer -----------------------------------------------------
        self.create_timer(1.0 / rate, self._poll)

        self.get_logger().info(
            f'huskylens_node active - algorithm: {algo_str} @ {rate:.0f} Hz')
        self.get_logger().info(
            'MCP Server (via Wi-Fi): configure it on the device -> Settings -> MCP Server')

    def _set_algorithm(self, algo_id: int) -> bool:
        if self._using_pyhuskylens:
            try:
                self._hl.set_alg(algo_id)
                ok = True
            except Exception:
                ok = False
        else:
            ok = self._hl.set_algorithm(algo_id)

        name = ALGO_NAMES.get(algo_id, str(algo_id))
        if ok:
            self._current_algo_id   = algo_id
            self._current_algo_name = name
            self.get_logger().info(f'Active algorithm: {name}')
        else:
            self.get_logger().warn(f'Could not change the algorithm to: {name}')
        return ok

    def _on_set_algorithm(self, msg: String):
        """Changes the algorithm from a ROS topic."""
        algo_str = msg.data.strip().lower()
        algo_id  = _ALGO_MAP.get(algo_str)
        if algo_id is None:
            self.get_logger().warn(
                f'Unknown algorithm: "{algo_str}". '
                f'Available: {list(_ALGO_MAP.keys())}')
            return
        self._set_algorithm(algo_id)

    def _block_to_legacy_result(self, block):
        result = SimpleNamespace()
        result.is_block = True
        result.x_center = float(getattr(block, 'x', 0))
        result.y_center = float(getattr(block, 'y', 0))
        result.width = float(getattr(block, 'width', 0))
        result.height = float(getattr(block, 'height', 0))
        result.id = int(getattr(block, 'ID', getattr(block, 'id', 0)))
        return result

    def _poll(self):
        """Requests results and publishes them."""
        try:
            if self._using_pyhuskylens:
                blocks = self._hl.get_blocks()
                results = [self._block_to_legacy_result(block) for block in blocks]
            else:
                results = self._hl.get_results()
        except Exception as e:
            self.get_logger().warn(f'Error reading HuskyLens: {e}', throttle_duration_sec=5.0)
            return

        now = self.get_clock().now().to_msg()

        # --- Detection2DArray --------------------------------------------------
        det_array = Detection2DArray()
        det_array.header.stamp    = now
        det_array.header.frame_id = self._frame_id

        for r in results:
            if not r.is_block:
                continue
            d = Detection2D()
            d.header = det_array.header
            d.bbox.center.position.x = float(r.x_center)
            d.bbox.center.position.y = float(r.y_center)
            d.bbox.size_x = float(r.width)
            d.bbox.size_y = float(r.height)

            hyp = ObjectHypothesisWithPose()
            hyp.hypothesis.class_id = str(r.id)
            hyp.hypothesis.score    = 1.0
            d.results.append(hyp)
            det_array.detections.append(d)

        self._det_pub.publish(det_array)

        # --- Main object point (lowest ID or first one) ------------------------
        if results:
            primary = min((r for r in results if r.is_block),
                          key=lambda r: r.id, default=None)
            if primary is not None:
                pt = Point()
                # Normalize to [-1, 1] centered on the image
                pt.x = (primary.x_center - self._img_w / 2.0) / (self._img_w / 2.0)
                pt.y = (primary.y_center - self._img_h / 2.0) / (self._img_h / 2.0)
                pt.z = 0.0
                self._point_pub.publish(pt)

        # --- Publish active algorithm -------------------------------------------
        algo_msg = String()
        algo_msg.data = self._current_algo_name
        self._algo_pub.publish(algo_msg)


def main(args=None):
    rclpy.init(args=args)
    node = None
    try:
        node = HuskyLens2Node()
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
