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

class DepthToLaserScanNode(Node):

    def __init__(self):
        super().__init__('depth_to_laserscan_node')

        self.get_logger().info('Starting depth_to_laserscan_node')

        self.declare_parameter(
            'input_topic', 'huskylens/depth/image')
        self.declare_parameter(
            'camera_info_topic', 'huskylens/camera_info')
        self.declare_parameter(
            'output_topic', 'huskylens/scan')
        self.declare_parameter('target_frame', 'huskylens2_link')
        self.declare_parameter('min_height', -0.1)  # relative to camera optical center
        self.declare_parameter('max_height',  0.1)
        self.declare_parameter('range_min',   0.2)
        self.declare_parameter('range_max',  10.0)
        self.declare_parameter('scan_time',   0.1)
        self.declare_parameter('num_scan_bins', 160)

        input_topic = self.get_parameter('input_topic').value
        camera_info_topic = self.get_parameter('camera_info_topic').value
        output_topic = self.get_parameter('output_topic').value
        self._target_frame = str(self.get_parameter('target_frame').value)
        self._min_height = float(self.get_parameter('min_height').value)
        self._max_height = float(self.get_parameter('max_height').value)
        self._range_min = float(self.get_parameter('range_min').value)
        self._range_max = float(self.get_parameter('range_max').value)
        self._scan_time = float(self.get_parameter('scan_time').value)
        self._num_scan_bins = int(self.get_parameter('num_scan_bins').value)

        if self._num_scan_bins < 10:
            raise ValueError('num_scan_bins must be at least 10')

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
            f' - height limits:                 '
            f'{self._min_height:.3f}..{self._max_height:.3f} m')
        self.get_logger().info(
            f' - target frame:                  {self._target_frame}')

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
            raise ValueError(
                f'expected single-channel depth, got {depth.shape}')

        height, width = depth.shape

        if (camera_info.width != width or
                camera_info.height != height):
            raise ValueError(
                f'CameraInfo size '
                f'{camera_info.width}x{camera_info.height} '
                f'does not match depth image {width}x{height}')

        # Prefer P for a rectified image.
        focal_x = float(camera_info.p[0])
        focal_y = float(camera_info.p[5])
        center_x = float(camera_info.p[2])
        center_y = float(camera_info.p[6])

        if focal_x <= 0.0 or focal_y <= 0.0:
            raise ValueError(
                'CameraInfo has invalid focal lengths')

        # Convert depth to meters.
        if depth.dtype == np.uint16:
            depth_m = depth.astype(np.float32) * 0.001
        elif depth.dtype in (np.float32, np.float64):
            depth_m = depth.astype(np.float32)
        else:
            raise ValueError(
                f'unsupported depth dtype {depth.dtype}')

        # True horizontal angle of every camera column.
        columns = np.arange(width, dtype=np.float32)
        horizontal_angles = np.arctan2(
            columns - center_x, focal_x)

        angle_min = float(horizontal_angles[0])
        angle_max = float(horizontal_angles[-1])

        num_bins = self._num_scan_bins
        angle_increment = (
            (angle_max - angle_min) / (num_bins - 1))

        # Map each camera column to a uniform LaserScan bin.
        column_bins = np.rint(
            (horizontal_angles - angle_min)
            / angle_increment
        ).astype(np.int32)

        column_bins = np.clip(
            column_bins, 0, num_bins - 1)

        ranges = np.full(
            num_bins, np.inf, dtype=np.float32)

        # Vertical camera coordinates.
        row_factors = (
            np.arange(height, dtype=np.float32) - center_y
        ) / focal_y

        cos_angles = np.cos(horizontal_angles)

        for row, vertical_factor in enumerate(row_factors):
            row_depth = depth_m[row]

            valid = (
                np.isfinite(row_depth)
                & (row_depth > 0.0)
            )

            if not np.any(valid):
                continue

            # ROS optical frame:
            # X right, Y down, Z forward.
            # Height above optical center is therefore -Y.
            camera_height = -vertical_factor * row_depth

            valid &= (
                (camera_height >= self._min_height)
                & (camera_height <= self._max_height)
            )

            # Horizontal planar range.
            candidate_ranges = row_depth / cos_angles

            valid &= (
                (candidate_ranges >= self._range_min)
                & (candidate_ranges <= self._range_max)
            )

            # Several image pixels can map to the same scan bin.
            # Keep the nearest one.
            np.minimum.at(
                ranges,
                column_bins[valid],
                candidate_ranges[valid]
            )

        scan = LaserScan()
        scan.header = header
        scan.header.frame_id = self._target_frame

        scan.angle_min = angle_min
        scan.angle_max = angle_max
        scan.angle_increment = angle_increment

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
        node = DepthToLaserScanNode()
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
