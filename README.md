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

To run the **I2C node on Raspberry Pi** directly:

```bash
ros2 run huskylens2_ros2 huskylens2_i2c_node
```

To use another parameter file:

```bash
ros2 launch huskylens2_ros2 huskylens2.launch.py params_file:=/absolute/path/to/config.yaml
```

To run the **MCP Server client node on Raspberry Pi or Workstation** directly:

```bash
ros2 run huskylens2_ros2 huskylens2_mcp_node

  or

ros2 launch huskylens2_ros2 huskylens2_mcp.launch.py \
  mcp_server:=http://huskylens.local:3000 algorithm_id:=2
```


To use another parameter file:

```bash
ros2 launch huskylens2_ros2 huskylens2.launch.py params_file:=/absolute/path/to/config.yaml
```

**Note:**
- You must use the actual IP address instead of *"huskylens.local"*, unless you add it to your `/etc/hosts` file.
- There is no way to set a *static IP address* using the HuskyLens 2 on-screen menus.
- You can find the DHCP-assigned IP address in the *"MCP Server"* section of on-screen menu.
- Most routers allow you to assign a reserved IP address to a device based on its MAC address.
To find the MAC address for your HuskyLens 2:
```
ping -c <actual IP addr>
ip neigh show
<actual IP addr> dev eno1 lladdr 88:31:39:65:34:64 REACHABLE
```
The `88:31:39:65:34:64` will be the MAC address you can use in your router's *"Reserve addresses"* (or similar) setup.
