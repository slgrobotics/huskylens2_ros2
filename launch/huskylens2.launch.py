"""Launch the HuskyLens 2 node with a configurable parameter file."""

from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    default_config = str(
        Path(get_package_share_directory('huskylens2_ros2'))
        / 'config' / 'huskylens2.yaml'
    )
    return LaunchDescription([
        DeclareLaunchArgument(
            'params_file',
            default_value=default_config,
            description='Path to the ROS 2 parameter YAML file.',
        ),
        Node(
            package='huskylens2_ros2',
            executable='huskylens2_node',
            name='huskylens2_node',
            output='screen',
            parameters=[LaunchConfiguration('params_file')],
        ),
    ])
