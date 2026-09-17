#!/usr/bin/env python3

"""
point_cloud_rgb_node.launch.py

Decompress the HuskyLens RGB image and generate an XYZRGB point cloud
from the RGB image and metric depth image.

Install prerequisites:
  sudo apt install ros-${ROS_DISTRO}-image-pipeline
  sudo apt install ros-${ROS_DISTRO}-image-transport-plugins

Run:
  ros2 launch huskylens2_ros2 point_cloud_rgb_node.launch.py
"""

from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description():
    return LaunchDescription([

        # ------------------------------------------------------------------
        # Decompress RGB image:
        #
        #   /huskylens/image/compressed
        #       sensor_msgs/msg/CompressedImage
        #
        #              ↓
        #
        #   /huskylens/image/raw
        #       sensor_msgs/msg/Image
        #
        # image_transport operates on base topic names. The "compressed"
        # input transport therefore subscribes to:
        #
        #   /huskylens/image/compressed
        #
        # while the "raw" output transport publishes:
        #
        #   /huskylens/image/raw
        # ------------------------------------------------------------------
        Node(
            package='image_transport',
            executable='republish',
            name='huskylens_rgb_decompress',
            output='screen',
            parameters=[{
                'in_transport': 'compressed',
                'out_transport': 'raw',
            }],
            remappings=[
                ('in/compressed', '/huskylens/image/compressed'),
                ('out', '/huskylens/image_decompressed'),
            ],
        ),
        # ------------------------------------------------------------------
        # RGB + depth → XYZRGB point cloud
        #
        # RGB:
        #   /huskylens/image/raw
        #
        # Depth:
        #   /huskylens/depth/image
        #       encoding: 16UC1
        #       units: millimeters
        #
        # Camera calibration:
        #   /huskylens/depth/camera_info
        #
        # Output:
        #   /huskylens/depth/points
        #       sensor_msgs/msg/PointCloud2
        # ------------------------------------------------------------------
        Node(
            package='depth_image_proc',
            executable='point_cloud_xyzrgb_node',
            name='depth_point_cloud_xyzrgb',
            output='screen',
            remappings=[
                (
                    'rgb/image_rect_color',
                    '/huskylens/image_decompressed'
                ),
                (
                    'rgb/camera_info',
                    '/huskylens/depth/camera_info'
                ),
                (
                    'depth_registered/image_rect',
                    '/huskylens/depth/image'
                ),
                (
                    'points',
                    '/huskylens/depth/points'
                ),
            ],
        ),
    ])
