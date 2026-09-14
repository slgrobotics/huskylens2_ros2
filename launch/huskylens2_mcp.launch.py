#!/usr/bin/env python3
"""
huskylens2_mcp.launch.py - launch the LAN-based HuskyLens 2 MCP node

Examples:
    ros2 launch huskylens2_ros2 huskylens2_mcp.launch.py
    ros2 launch huskylens2_ros2 huskylens2_mcp.launch.py mcp_server:=http://huskylens.local:3000
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

    algorithm_id_arg = DeclareLaunchArgument(
        'algorithm_id', default_value='2',
        description='HuskyLens application ID passed to the MCP tool')

    mcp_server_arg = DeclareLaunchArgument(
        'mcp_server', default_value='http://huskylens.local:3000',
        description='HuskyLens MCP server base URL, without /sse')

    poll_rate_arg = DeclareLaunchArgument(
        'poll_rate', default_value='10.0',
        description='MCP request frequency in Hz')

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
                'algorithm_id': LaunchConfiguration('algorithm_id'),
                'mcp_server': LaunchConfiguration('mcp_server'),
                'poll_rate':  LaunchConfiguration('poll_rate'),
            },
        ],
    )

    return LaunchDescription([
        algorithm_arg,
        algorithm_id_arg,
        mcp_server_arg,
        poll_rate_arg,
        config_arg,
        huskylens_node,
    ])
