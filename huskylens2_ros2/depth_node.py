#!/usr/bin/env python3

"""ROS 2 bridge from HuskyLens compressed images to an HTTP depth server."""

import queue
import threading
from copy import deepcopy

import cv2
import numpy as np
import requests
import rclpy
from cv_bridge import CvBridge
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from sensor_msgs.msg import CameraInfo, CompressedImage, Image

"""

This node subscribes to a compressed image topic, sends the images to an HTTP depth server,
 and publishes the resulting depth maps as 16-bit single-channel images.

ros2 launch huskylens2_ros2 depth_node.launch.py

  or

ros2 run huskylens2_ros2 depth_node --ros-args -p depth_server:=http://127.0.0.1:5001/depth

"""

class DepthNode(Node):

    def __init__(self):
        super().__init__('depth_node')

        self.get_logger().info('Starting depth_node')

        self.declare_parameter(
            'input_topic', 'huskylens/image/compressed')
        self.declare_parameter(
            'camera_info_topic', 'huskylens/camera_info')
        self.declare_parameter(
            'output_topic', 'huskylens/depth/image')
        self.declare_parameter(
            'camera_info_output_topic', 'huskylens/depth/camera_info')
        self.declare_parameter(
            'depth_server', 'http://127.0.0.1:5001/depth')
        self.declare_parameter('request_timeout', 5.0)
        self.declare_parameter('queue_size', 1)

        input_topic = self.get_parameter('input_topic').value
        camera_info_topic = self.get_parameter('camera_info_topic').value
        output_topic = self.get_parameter('output_topic').value
        camera_info_output_topic = self.get_parameter(
            'camera_info_output_topic').value
        self._depth_server = self.get_parameter('depth_server').value
        self._request_timeout = float(
            self.get_parameter('request_timeout').value)
        queue_size = max(1, int(self.get_parameter('queue_size').value))

        self._depth_pub = self.create_publisher(Image, output_topic, 10)
        self._camera_info_pub = self.create_publisher(
            CameraInfo, camera_info_output_topic, 10)
        self.create_subscription(
            CompressedImage, input_topic, self._on_image, 10)
        self.create_subscription(
            CameraInfo, camera_info_topic, self._on_camera_info, 10)

        self._frames = queue.Queue(maxsize=queue_size)
        self._stop_event = threading.Event()
        self._session = requests.Session()
        self._bridge = CvBridge()
        self._camera_info_lock = threading.Lock()
        self._camera_info = None
        self._worker = threading.Thread(
            target=self._process_frames, daemon=True)
        self._worker.start()

        self.get_logger().info('Pipeline:')
        self.get_logger().info(f' - subscribing to:                  {input_topic}')
        self.get_logger().info(
            f' - subscribing to camera info:      {camera_info_topic}')
        self.get_logger().info(f' - converting via server at:        {self._depth_server}')
        self.get_logger().info(f' - publishing depth images to:      {output_topic}')
        self.get_logger().info(
            f' - re-publishing depth camera info: {camera_info_output_topic}')


    def _on_image(self, message):
        try:
            self._frames.put_nowait(message)
        except queue.Full:
            try:
                self._frames.get_nowait()
                self._frames.put_nowait(message)
            except queue.Empty:
                pass


    def _on_camera_info(self, message):
        with self._camera_info_lock:
            self._camera_info = message


    def _process_frames(self):
        while not self._stop_event.is_set():
            try:
                message = self._frames.get(timeout=0.2)
            except queue.Empty:
                continue

            try:
                response = self._session.post(
                    self._depth_server,
                    data=bytes(message.data),
                    headers={
                        'Content-Type': (
                            f'image/{message.format}'
                            if message.format else 'image/jpeg')
                    },
                    timeout=self._request_timeout,
                )
                response.raise_for_status()
                depth = cv2.imdecode(
                    np.frombuffer(response.content, dtype=np.uint8),
                    cv2.IMREAD_UNCHANGED,
                )
                if depth is None:
                    raise RuntimeError('depth server returned undecodable data')
                if depth.dtype != np.uint16 or depth.ndim != 2:
                    raise RuntimeError(
                        f'expected a single-channel uint16 depth map, got '
                        f'{depth.dtype} with shape {depth.shape}')

                depth_message = self._bridge.cv2_to_imgmsg(
                    depth, encoding='16UC1')
                depth_message.header = message.header
                self._depth_pub.publish(depth_message)
                with self._camera_info_lock:
                    camera_info = deepcopy(self._camera_info)
                if camera_info is not None:
                    camera_info.header.stamp = depth_message.header.stamp
                    self._camera_info_pub.publish(camera_info)
                else:
                    self.get_logger().warning(
                        'No camera info received yet; skipping depth camera info',
                        throttle_duration_sec=5.0)
            except requests.RequestException as exc:
                self.get_logger().warning(
                    f'Depth server request failed: {exc}',
                    throttle_duration_sec=5.0)
            except (RuntimeError, cv2.error, ValueError) as exc:
                self.get_logger().warning(
                    f'Invalid depth response: {exc}',
                    throttle_duration_sec=5.0)


    def destroy_node(self):
        self._stop_event.set()
        self._session.close()
        self._worker.join(timeout=1.0)
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = None
    try:
        node = DepthNode()
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
