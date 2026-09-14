## huskylens2_ros2

Python (`ament_python`) ROS 2 package for HuskyLens 2.
The node starts and spins; hardware communication and publishers are TODOs.
Set the maintainer and license in `package.xml` and `setup.py` before distribution.

### Build and run

Place this package in your ROS 2 workspace's `src` directory. From the workspace
root, with your ROS 2 environment sourced:

```bash
colcon build --packages-select huskylens2_ros2 --symlink-install
source install/setup.bash
ros2 launch huskylens2_ros2 huskylens2.launch.py
```

To run the I2C node on Raspberry Pi directly:

```bash
ros2 run huskylens2_ros2 huskylens2_i2c_node
```

To use another parameter file:

```bash
ros2 launch huskylens2_ros2 huskylens2.launch.py params_file:=/absolute/path/to/config.yaml
```

To run the MCP Server client node on Raspberry Pi or Workstation directly:

```bash
ros2 run huskylens2_ros2 huskylens2_mcp_node
```

To use another parameter file:

```bash
ros2 launch huskylens2_ros2 huskylens2.launch.py params_file:=/absolute/path/to/config.yaml
```
