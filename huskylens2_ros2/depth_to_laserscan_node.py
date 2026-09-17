#!/usr/bin/env python3

"""Convert HuskyLens depth images into horizontal LaserScan messages."""

import threading
from copy import deepcopy

import cv2
import rclpy
from cv_bridge import CvBridge
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from sensor_msgs.msg import CameraInfo, Image, LaserScan
import numpy as np

"""

This node subscribes to a depth image and CameraInfo topic, then publishes a
horizontal LaserScan. Each scan ray contains the nearest valid depth sample
whose reconstructed camera height is within the configured height limits.

ros2 run huskylens2_ros2 depth_to_laserscan_node

"""

class DepthNode(Node):

    def __init__(self):
        super().__init__('depth_to_laserscan_node')

        self.get_logger().info('Starting depth_to_laserscan_node')

        self.declare_parameter(
            'input_topic', 'huskylens/depth/image')
        self.declare_parameter(
            'camera_info_topic', 'huskylens/camera_info')
        self.declare_parameter(
            'output_topic', 'huskylens/scan')
        self.declare_parameter('target_frame', 'huskylens2_link_optical')
        self.declare_parameter('min_height', 0.03)
        self.declare_parameter('max_height', 2.0)
        self.declare_parameter('range_min', 0.2)
        self.declare_parameter('range_max', 5.0)
        self.declare_parameter('scan_time', 0.1)

        input_topic = self.get_parameter('input_topic').value
        camera_info_topic = self.get_parameter('camera_info_topic').value
        output_topic = self.get_parameter('output_topic').value
        self._target_frame = str(self.get_parameter('target_frame').value)
        self._min_height = float(self.get_parameter('min_height').value)
        self._max_height = float(self.get_parameter('max_height').value)
        self._range_min = float(self.get_parameter('range_min').value)
        self._range_max = float(self.get_parameter('range_max').value)
        self._scan_time = float(self.get_parameter('scan_time').value)

        if self._min_height > self._max_height:
            raise ValueError('min_height must not exceed max_height')
        if not 0.0 < self._range_min < self._range_max:
            raise ValueError('range_min must be positive and below range_max')

        self._scan_pub = self.create_publisher(LaserScan, output_topic, 10)

        self.create_subscription(
            Image, input_topic, self._on_image, 10)
        self.create_subscription(
            CameraInfo, camera_info_topic, self._on_camera_info, 10)

        self._bridge = CvBridge()
        self._camera_info_lock = threading.Lock()
        self._camera_info = None

        self.get_logger().info(
            f' - converting depth from:         {input_topic}')
        self.get_logger().info(
            f' - publishing LaserScan to:       {output_topic}')
        self.get_logger().info(
            f' - height limits:                  '
            f'{self._min_height:.3f}..{self._max_height:.3f} m')


    def _on_image(self, message):
        with self._camera_info_lock:
            camera_info = deepcopy(self._camera_info)
        if camera_info is None:
            self.get_logger().warning(
                'No camera info received yet; skipping depth image',
                throttle_duration_sec=5.0)
            return

        try:
            depth = self._bridge.imgmsg_to_cv2(
                message, desired_encoding='passthrough')
            scan = self._depth_to_scan(depth, camera_info, message.header)
            self._scan_pub.publish(scan)
        except (cv2.error, TypeError, ValueError) as exc:
            self.get_logger().warning(
                f'Could not convert depth image to LaserScan: {exc}',
                throttle_duration_sec=5.0)


    def _on_camera_info(self, message):
        with self._camera_info_lock:
            self._camera_info = message


    def _depth_to_scan(self, depth, camera_info, header):
        if depth.ndim != 2:
            raise ValueError(f'expected single-channel depth, got {depth.shape}')
        if camera_info.k[0] <= 0.0 or camera_info.k[4] <= 0.0:
            raise ValueError('CameraInfo has invalid focal lengths')

        if depth.dtype == np.uint16:
            depth_m = depth.astype(np.float32) * 0.001
        elif depth.dtype == np.float32 or depth.dtype == np.float64:
            depth_m = depth.astype(np.float32)
        else:
            raise ValueError(f'unsupported depth encoding dtype {depth.dtype}')

        height, width = depth_m.shape
        focal_x = float(camera_info.k[0])
        focal_y = float(camera_info.k[4])
        center_x = float(camera_info.k[2])
        center_y = float(camera_info.k[5])

        columns = np.arange(width, dtype=np.float32)
        horizontal_angles = np.arctan2(columns - center_x, focal_x)
        ranges = np.full(width, np.inf, dtype=np.float32)
        row_coordinates = (
            np.arange(height, dtype=np.float32) - center_y) / focal_y

        for row, vertical_factor in enumerate(row_coordinates):
            row_depth = depth_m[row]
            valid = np.isfinite(row_depth) & (row_depth > 0.0)
            if not np.any(valid):
                continue
            camera_height = -vertical_factor * row_depth
            valid &= (
                (camera_height >= self._min_height)
                & (camera_height <= self._max_height)
            )
            candidate_ranges = row_depth / np.cos(horizontal_angles)
            valid &= (
                (candidate_ranges >= self._range_min)
                & (candidate_ranges <= self._range_max)
            )
            ranges[valid] = np.minimum(ranges[valid], candidate_ranges[valid])

        scan = LaserScan()
        scan.header = header
        scan.header.frame_id = self._target_frame
        scan.angle_min = float(horizontal_angles[0])
        scan.angle_max = float(horizontal_angles[-1])
        scan.angle_increment = (
            float(horizontal_angles[1] - horizontal_angles[0])
            if width > 1 else 0.0)
        scan.time_increment = 0.0
        scan.scan_time = self._scan_time
        scan.range_min = self._range_min
        scan.range_max = self._range_max
        scan.ranges = ranges.tolist()
        scan.intensities = []
        return scan


    def destroy_node(self):
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
