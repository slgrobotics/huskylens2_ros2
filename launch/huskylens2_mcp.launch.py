#!/usr/bin/env python3
"""
huskylens2.launch.py - launch HuskyLens 2 node

Examples:
  ros2 launch huskylens2_ros2 huskylens2.launch.py
  ros2 launch huskylens2_ros2 huskylens2.launch.py algorithm:=face
"""

import os
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    pkg_dir = get_package_share_directory('huskylens2_ros2')
    default_config  = os.path.join(pkg_dir, 'config', 'huskylens2.yaml')

    algorithm_arg = DeclareLaunchArgument(
        'algorithm', default_value='object_recognition',
        description='Initial HuskyLens 2 algorithm. '
                    'Values: face, object, tracking, line, color, tag, '
                    'gesture, pose, hand, ocr, qr, barcode')

    poll_rate_arg = DeclareLaunchArgument(
        'poll_rate', default_value='10.0',
        description='I2C read frequency in Hz')

    config_arg = DeclareLaunchArgument(
        'params_file',
        default_value=default_config,
        description='Path to the ROS 2 parameter YAML file.')

    huskylens_node = Node(
        package='huskylens2_ros2',
        executable='huskylens2_mcp_node',
        name='huskylens2_mcp_node',
        output='screen',
        parameters=[
            LaunchConfiguration('params_file'),
            {
                'algorithm':  LaunchConfiguration('algorithm'),
                'poll_rate':  LaunchConfiguration('poll_rate'),
            },
        ],
    )

    return LaunchDescription([
        algorithm_arg,
        poll_rate_arg,
        config_arg,
        huskylens_node,
    ])
