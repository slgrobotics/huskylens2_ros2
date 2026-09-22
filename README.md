Back to [Main Project Home](https://github.com/slgrobotics/articubot_one/wiki)

## A ROS 2 package for HuskyLens 2

Uses Python (`ament_python`).

> Original I2C node (and credits for it to): https://github.com/irayfuego/robotica/blob/main/src/huskylens2_ros2/huskylens2_ros2/huskylens_node.py

Contents:
- [Published topics](https://github.com/slgrobotics/huskylens2_ros2/blob/main/README.md#published-topics)
- [Device setup](https://github.com/slgrobotics/huskylens2_ros2/blob/main/README.md#device-setup)
- [Build and run](https://github.com/slgrobotics/huskylens2_ros2#build-and-run)
- [Camera FOV Specifications (HUSKYLENS 2 Plus Kit)](https://github.com/slgrobotics/huskylens2_ros2#camera-fov-specifications-huskylens-2-plus-kit)
- [The *Optical* Coordinate System (For Cameras and Sensors)](https://github.com/slgrobotics/huskylens2_ros2/blob/main/README.md#the-optical-coordinate-system-for-cameras-and-sensors)

> **Note:**
> - code and description related to converting monocular camera images to 3D (PointCloud2 etc.) have been moved to:
>   - [image_to_3d package](https://github.com/slgrobotics/image_to_3d)

-----------------------------

### Published topics

| Node | Topic | Message type | Description |
|---|---|---|---|
| `huskylens2_mcp_node` | `camera/camera_info` | `CameraInfo` | Camera calibration information |
| | `camera/image_raw/compressed` | `CompressedImage` | Compressed camera image |
| | `huskylens/image/marked` | `Image` | Image with recognition results marked |
| | `huskylens/detections` | `Detection2DArray` | Object detections |
| | `huskylens/tracked_object` | `Point` | Tracked object position |
| | `huskylens/algorithm` | `String` | Active recognition algorithm |
| | `huskylens/status` | `String` | Connection status (`"up"` or `"down"`) |
| `huskylens2_i2c_node` | `huskylens/detections` | `Detection2DArray` | Object detections |
| | `huskylens/tracked_object` | `Point` | Tracked object position |
| | `huskylens/algorithm` | `String` | Active recognition algorithm |

> **Note:** `huskylens2_i2c_node` does not publish camera images because images cannot be retrieved over I2C.


-----------------------------

### Device setup

See this "[Getting Started](https://wiki.dfrobot.com/sen0638/docs/22599)" guide first. More info [here](https://wiki.dfrobot.com/sen0638/docs/22608).

**Note:** my [HUSKYLENS 2 Plus Kit](https://www.amazon.com/dp/B0H1Q77BTR) was a bit of a pain to set up:
- When you open the case, the thermal pads tear off — be ready to replace them. Spares are not included in the kit.
- The WiFi module doesn't fit easily in its socket, you have to press *really* hard.
- According to [this guide](https://www.makerguides.com/getting-started-with-huskylens-2-and-arduino-esp32/) the camera consumes less than 500 mA at 5V. Use a 5V power supply with at least 2A rating.
- It shipped with firmware v1.2.1, which requires an [upgrade](https://wiki.dfrobot.com/sen0638/docs/22673):
  - Download the firmware image.
  - Download the upgrade tool for Linux. You don't need the *Zadig - Driver Installation Tool* - that's for Windows.
  - Connect the device to your PC using a high-quality USB-C cable while holding the A button.
  - Running `lsusb` should display:
    - `ID 29f1:0230 Canaan Creative Co., Ltd K230 USB Boot Device`
  - Run the upgrade tool with `sudo`, otherwise it will fail to connect.
  - After rebooting, set up the Wi-Fi connection and enable the MCP server in the on-screen menu.
- You don't need I2C connection to use MCP Server over the WiFi, just connect a 5V source to USB-C power.
- The I2C (a.k.a. *Gravity*) interface on the [power board](https://wiki.dfrobot.com/sen0638/docs/22601) is 3.3V.
Connect it to Raspberry Pi header pins:
  - Ground marked as "-" to any Ground pin (e.g. 06 or 09)
  - VCC marked as "+" leave not connected. It measures 0V.
  - SCL marked as "C/R" to pin 05 (GPIO03, SCL1)
  - SDA marked as "D/T" to pin 03 (GPIO02, SDA1)
  - Run `i2cdetect -y 1` - the device shows on address 0x50

> **Important:** camera images/frames are not retrievable via I2C interface. You have to use MCP Server over WiFi for this.

Here is DFRobot's guide on [MCP Server use](https://wiki.dfrobot.com/sen0638/docs/22605).

Check out this [guide](https://github.com/slgrobotics/articubot_one/wiki/ROS2-and-AI-Experiments#querying-mcp-server-for-its-capabilities-as-a-ros2-tool) for querying MCP Server using AI/LLM tools 

> **Note:**
> - You must use the actual IP address instead of *"huskylens.local"*, unless you add it to your `/etc/hosts` file.
> - There is no way to set a *static IP address* using the HuskyLens 2 on-screen menus.
> - You can find the DHCP-assigned IP address in the *"MCP Server"* section of on-screen menu.

Most routers allow you to assign a reserved IP address to a device based on its MAC address.
To find the MAC address for your HuskyLens 2:
```
ping -c <actual IP addr>
ip neigh show
<actual IP addr> dev eno1 lladdr 88:31:39:65:34:64 REACHABLE
```
The `88:31:39:65:34:64` will be the MAC address you can use in your router's *"Reserve addresses"* (or similar) setup.

### Build and run

Place this package and the related *image_to_3d* package in your ROS 2 workspace's `src` directory:
```
mkdir -p ~/robot_ws/src
cd ~/robot_ws/src
git clone https://github.com/slgrobotics/huskylens2_ros2.git

# If you want 3D package:
git clone https://github.com/slgrobotics/image_to_3d.git
```

> **Check out** *~/robot_ws/src/huskylens2_ros2/tests* directory

From the workspace root, with your ROS 2 environment sourced:
```bash
cd ~/robot_ws

colcon build
  or
colcon build --packages-select huskylens2_ros2 --symlink-install

source install/setup.bash
ros2 launch huskylens2_ros2 huskylens2.launch.py
```

To run the **_I2C node_** on Raspberry Pi:

```bash
ros2 run huskylens2_ros2 huskylens2_i2c_node

  or, using another parameter file:

ros2 launch huskylens2_ros2 huskylens2.launch.py params_file:=/absolute/path/to/config.yaml
```

To run the **_MCP Server client node_** on Raspberry Pi or Workstation:

```bash
ros2 run huskylens2_ros2 huskylens2_mcp_node

  or

ros2 launch huskylens2_ros2 huskylens2_mcp.launch.py \
  mcp_server:=http://huskylens.local:3000 algorithm_id:=2
```

### Camera FOV Specifications (HUSKYLENS 2 Plus Kit)

The *[HUSKYLENS 2 Plus Kit](https://www.amazon.com/dp/B0H1Q77BTR)* (SKU: KIT0222) includes two separate camera configurations to accommodate different computer vision and robotic tracking setups.

#### 1. Standard Stock Camera Module
The default baseline 2MP GC2093 image sensor comes pre-installed on the main HUSKYLENS 2 board.

*   *Horizontal FOV (HFOV):* ~49.12°
*   *Vertical FOV (VFOV):* ~38.69°

#### 2. Included Wide-Angle Camera Module
This modular accessory replaces the standard lens to expand the viewing area, making it ideal for mobile robotics, obstacle avoidance, and multi-target detection.

*   *Diagonal FOV (DFOV):* 116.6°
*   *Horizontal FOV (HFOV):* 107.6°
*   *Vertical FOV (VFOV):* 72.6°
*   *Effective Focal Length:* 2.02 mm

Unlike WiFi module, cameras are easy to switch. Use `tests/mcp_stream.py` to adjust focus on the wide angle camera.

This is how the `/huskylens/image/marked` topic looks like with *Standard Stock* camera, 640x480 resolution:

<img alt="Huskylens marked image" src="https://github.com/user-attachments/assets/e5156614-6a2c-4331-b7a9-b180e60e3b3d" />

This is how it looks with the *Wide-Angle* camera, included in *Huskylens 2 Plus kit*:

<img alt="Huskylens wide FOV" src="https://github.com/user-attachments/assets/8cc25eaa-5b56-4669-8a06-d5e79aeeeff2" />

**Note:** Huskylens Object Recognition model seems to have difficulty recognizing common objects even in ideal conditions.

### The *Optical* Coordinate System (For Cameras and Sensors)

Cameras view the world from a pixel grid perspective rather than a driving perspective.
Because of this, REP-103 defines a completely different axis standard for optical frames:

When looking out through the camera lens:
- Z-Axis: Points Forward (into the scene, acting as the Depth axis)
- X-Axis: Points Right   (horizontal pixel axis)
- Y-Axis: Points Down    (vertical pixel axis)

It is different from robot's REP-103 Right-Handed, Z-Up coordinate system:
- X-Axis (Red in RViz):   Points Forward (the direction the robot drives)
- Y-Axis (Green in RViz): Points Left
- Z-Axis (Blue in RViz):  Points Up (against gravity)

So, the camera *body* lives in robot's frame, while the messages `frame_id` contains *optical frame* rotated as follows:
```
<origin xyz="0 0 0" rpy="${-pi/2} 0 ${-pi/2}"/>
```
For *HuskyLens 2*, for example, the following frames are present in the TF tree:
- `huskylens2_link` - location of camera body
- `huskylens2_link_optical` - the optical frame

-------------------------

Back to [Main Project Home](https://github.com/slgrobotics/articubot_one/wiki)
