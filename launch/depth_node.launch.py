#!/usr/bin/env python3

"""
depth_node.launch.py - launch the node querying the Depth Anything V2 server for depth maps/images

Works with the HuskyLens 2 MCP node (launch/huskylens2_mcp.launch.py), or any other node publishing compressed images.

Make sure that the Depth Anything V2 server is running, e.g.:
  cd ~/husky_ws/src/huskylens2_ros2/depth_anything
  ... activate your Python 3 virtual environment ...
  ./depth_server.py

Examples:
  ros2 launch huskylens2_ros2 depth_node.launch.py

  ros2 launch huskylens2_ros2 depth_node.launch.py depth_server:=http://127.0.0.1:5001/depth

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

    # default values here override the YAML file, but can be overridden by launch arguments

    depth_server_arg = DeclareLaunchArgument(
        'depth_server',
        default_value='http://127.0.0.1:5001/depth',
        description='Depth Anything V2 server base URL')

    config_arg = DeclareLaunchArgument(
        'params_file',
        default_value=default_config,
        description='Path to the ROS 2 parameter YAML file.')

    depth_node = Node(
        package='huskylens2_ros2',
        executable='depth_node',
        name='depth_node',
        output='screen',
        parameters=[
            LaunchConfiguration('params_file'),
           {
                'depth_server': LaunchConfiguration('depth_server'),
            },
        ],
    )

    return LaunchDescription([
        depth_server_arg,
        config_arg,
        depth_node,
    ])
