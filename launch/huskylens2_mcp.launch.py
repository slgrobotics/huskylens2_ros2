#!/usr/bin/env python3
"""
huskylens2_mcp.launch.py - launch the LAN-based HuskyLens 2 MCP node

Examples:
    ros2 launch huskylens2_ros2 huskylens2_mcp.launch.py
    ros2 launch huskylens2_ros2 huskylens2_mcp.launch.py mcp_server:=http://huskylens.local:3000
    ros2 launch huskylens2_ros2 huskylens2_mcp.launch.py camera_module:="92,79"

    Note: - the "92,79" was the best I found for HuskyLens 2 wide-angle camera module.
          - depth_server.py has DEPTH_MULTIPLIER = 0.5  # experimental scale factor for depth values
"""

import os
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue

def generate_launch_description():
    pkg_dir = get_package_share_directory('huskylens2_ros2')
    default_config = os.path.join(pkg_dir, 'config', 'huskylens2.yaml')

    # default values here override the YAML file, but can be overridden by launch arguments

    camera_module_arg = DeclareLaunchArgument(
        'camera_module',
        default_value='wide_angle',
        description='Camera module: stock, wide_angle, or HFOV,VFOV')

    algorithm_id_arg = DeclareLaunchArgument(
        'algorithm_id',
        default_value='2',
        description=(
            'HuskyLens application ID passed to the MCP tool: '
            '1=Face Recognition, 2=Object Recognition, 3=Line Tracking, '
            '4=Color Recognition, 5=Tag Recognition, 6=Gesture Recognition, '
            '7=Pose Recognition, 8=Hand Tracking, 9=OCR, 10=QR Code, 11=Barcode'
        )        
    )

    mcp_server_arg = DeclareLaunchArgument(
        'mcp_server', 
        default_value='http://huskylens.local:3000',
        description='HuskyLens MCP server base URL, without /sse')

    poll_rate_arg = DeclareLaunchArgument(
        'poll_rate',
        default_value='10.0',
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
                'camera_module': LaunchConfiguration('camera_module'),
                'algorithm_id': ParameterValue(
                    LaunchConfiguration('algorithm_id'),
                    value_type=int
                ),
                'mcp_server': LaunchConfiguration('mcp_server'),
                'poll_rate': ParameterValue(
                    LaunchConfiguration('poll_rate'),
                    value_type=float
                ),
            },
        ],
    )

    # static transform publisher for RViz2:
    tf_camera_to_map = Node(package = "tf2_ros", 
                    executable = "static_transform_publisher",
                    arguments=[
                        '--x', '5.0',     # X translation in meters
                        '--y', '0.0',     # Y translation in meters
                        '--z', '0.57',    # Z translation in meters (camera height above ground)
                        '--roll', '-1.57079632679',  # Roll in radians
                        '--pitch', '0.0', # Pitch in radians
                        '--yaw', '1.57079632679',   # Yaw in radians (e.g., 1.57079632679 = 90 degrees)
                        '--frame-id', 'map', # Parent frame ID
                        '--child-frame-id', 'huskylens2_link' # Child frame ID
                    ]
    )


    return LaunchDescription([
        camera_module_arg,
        algorithm_id_arg,
        mcp_server_arg,
        poll_rate_arg,
        config_arg,
        huskylens_node,
        tf_camera_to_map
    ])
