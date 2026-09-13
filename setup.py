from glob import glob
from setuptools import find_packages, setup


package_name = 'huskylens2_ros2'

setup(
    name=package_name,
    version='0.0.1',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        ('share/' + package_name + '/launch', glob('launch/*.launch.py')),
        ('share/' + package_name + '/config', glob('config/*.yaml')),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='TODO Maintainer',
    maintainer_email='maintainer@example.com',
    description='Python ROS 2 node for HuskyLens 2 integration.',
    license='TODO',
    entry_points={
        'console_scripts': [
            'huskylens2_node = huskylens2_ros2.huskylens2_node:main',
        ],
    },
)
