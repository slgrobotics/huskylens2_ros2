#!/usr/bin/env python3

"""
point_cloud_node.launch.py - launch the depth -> point cloud conversion node

Install prerequisites:
  sudo apt install ros-${ROS_DISTRO}-image-pipeline

Examples:
    ros2 launch huskylens2_ros2 point_cloud_node.launch.py
"""

from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description():
    return LaunchDescription([
        Node(
            package='depth_image_proc',
            executable='point_cloud_xyz_node',
            name='depth_point_cloud',
            output='screen',
            remappings=[
                ('camera_info', '/huskylens/depth/camera_info'),  # must be synchronized with depth image 
                ('image_rect', '/huskylens/depth/image'),
                ('points', '/huskylens/depth/points'),
            ],
        ),
    ])
