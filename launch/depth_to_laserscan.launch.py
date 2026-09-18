#!/usr/bin/env python3

"""
depth_to_laserscan.launch.py - launch the node converting depth images to LaserScan messages.

Examples:
    ros2 launch huskylens2_ros2 depth_to_laserscan.launch.py

    or

  ros2 launch huskylens2_ros2 depth_to_laserscan.launch.py \
    input_topic:=huskylens/depth/image \
    camera_info_topic:=huskylens/depth/camera_info \
    output_topic:=huskylens/scan \
    target_frame:=huskylens2_link_optical \
    num_scan_bins:=160 \
    min_height:=-0.1 \
    max_height:=0.1 \
    range_min:= 0.2 \
    range_max:=10.0 \
    scan_time:= 0.1

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
    default_config  = os.path.join(pkg_dir, 'config', 'huskylens2.yaml')

    input_topic_arg = DeclareLaunchArgument(
        'input_topic', default_value='huskylens/depth/image',
        description='Depth image topic')

    camera_info_topic_arg = DeclareLaunchArgument(
        'camera_info_topic', default_value='huskylens/depth/camera_info',
        description='CameraInfo topic')

    num_scan_bins_arg = DeclareLaunchArgument(
        'num_scan_bins', default_value='160',
        description='Number of LaserScan bins (must be at least 10)')

    output_topic_arg = DeclareLaunchArgument(
        'output_topic', default_value='huskylens/scan',
        description='LaserScan output topic')

    target_frame_arg = DeclareLaunchArgument(
        'target_frame', default_value='huskylens2_link',
        description='Frame ID for the published LaserScan')

    min_height_arg = DeclareLaunchArgument(
        'min_height', default_value='-0.1',
        description='Minimum accepted camera height in meters')

    max_height_arg = DeclareLaunchArgument(
        'max_height', default_value='0.1',
        description='Maximum accepted camera height in meters')

    range_min_arg = DeclareLaunchArgument(
        'range_min', default_value='0.2',
        description='Minimum accepted scan range in meters')

    range_max_arg = DeclareLaunchArgument(
        'range_max', default_value='10.0',
        description='Maximum accepted scan range in meters')

    scan_time_arg = DeclareLaunchArgument(
        'scan_time', default_value='0.1',
        description='Time between scans in seconds')

    config_arg = DeclareLaunchArgument(
        'params_file',
        default_value=default_config,
        description='Path to the ROS 2 parameter YAML file.')

    depth_node = Node(
        package='huskylens2_ros2',
        executable='depth_to_laserscan_node',
        name='depth_to_laserscan_node',
        output='screen',
        parameters=[
            LaunchConfiguration('params_file'),
            {
                'input_topic': LaunchConfiguration('input_topic'),
                'camera_info_topic': LaunchConfiguration('camera_info_topic'),
                'output_topic': LaunchConfiguration('output_topic'),
                'target_frame': LaunchConfiguration('target_frame'),
                'min_height': ParameterValue(
                    LaunchConfiguration('min_height'), value_type=float),
                'max_height': ParameterValue(
                    LaunchConfiguration('max_height'), value_type=float),
                'range_min': ParameterValue(
                    LaunchConfiguration('range_min'), value_type=float),
                'range_max': ParameterValue(
                    LaunchConfiguration('range_max'), value_type=float),
                'scan_time': ParameterValue(
                    LaunchConfiguration('scan_time'), value_type=float),
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
                        '--roll',  '3.14159265359',  # Roll in radians
                        '--pitch', '0.0', # Pitch in radians
                        '--yaw',   '3.14159265359',   # Yaw in radians (e.g., 1.57079632679 = 90 degrees)
                        '--frame-id', 'map', # Parent frame ID
                        '--child-frame-id', 'huskylens2_link' # Child frame ID
                    ]
    )

    return LaunchDescription([
        input_topic_arg,
        camera_info_topic_arg,
        num_scan_bins_arg,
        output_topic_arg,
        target_frame_arg,
        min_height_arg,
        max_height_arg,
        range_min_arg,
        range_max_arg,
        scan_time_arg,
        config_arg,
        tf_camera_to_map,
        depth_node,
    ])
