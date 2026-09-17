Back to [Main Project Home](https://github.com/slgrobotics/articubot_one/wiki)

## A ROS 2 package for HuskyLens 2

Uses Python (`ament_python`).

> Original I2C node (and credits for it to): https://github.com/irayfuego/robotica/blob/main/src/huskylens2_ros2/huskylens2_ros2/huskylens_node.py

Contents:
- [Device setup](https://github.com/slgrobotics/huskylens2_ros2/blob/main/README.md#device-setup)
- [Build and run](https://github.com/slgrobotics/huskylens2_ros2#build-and-run)
- [Camera FOV Specifications (HUSKYLENS 2 Plus Kit)](https://github.com/slgrobotics/huskylens2_ros2#camera-fov-specifications-huskylens-2-plus-kit)
- [Depth Anything V2 HTTP Server](https://github.com/slgrobotics/huskylens2_ros2#depth-anything-v2-http-server)
- [Depth node](https://github.com/slgrobotics/huskylens2_ros2#depth-node)
- [Producing PointCloud2 from Depth topic](https://github.com/slgrobotics/huskylens2_ros2#producing-pointcloud2-from-depth-topic)

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

Place this package in your ROS 2 workspace's `src` directory:
```
mkdir -p ~/husky_ws/src
cd ~/husky_ws/src
git clone https://github.com/slgrobotics/huskylens2_ros2.git
```

> **Check out** *~/husky_ws/src/huskylens2_ros2/tests* directory

From the workspace root, with your ROS 2 environment sourced:
```bash
cd ~/husky_ws/src

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

### Depth Anything V2 HTTP Server

See this [guide](https://github.com/slgrobotics/articubot_one/wiki/Depth-Anything-V2) for information.

The *Depth Anything V2 HTTP Server* in the `depth_anything` directory takes an image and returns a depth map (as a .png image).

It must be run in an environment with a GPU (CUDA) - normally a Python
"sandboxed" *virtual environment* with PyTorch installed.

Make sure you install additional dependencies (in the `venv`):
```
pip install fastapi uvicorn
```

A ROS2 node or any other program can issue an HTTP POST request to this server
with an image.

The server loads the model once at startup, processes each input image,
performs inference, and returns the depth map as a 16-bit PNG image.

```    
     ROS 2 node / other client
                 │
                 │ HTTP POST
                 │ image/jpeg or image/png
                 ▼
    ┌──────────────────────────┐
    │ Depth Anything V2 server │
    │                          │
    │ decode image             │
    │ preprocess               │
    │ CUDA inference           │
    │ resize to input size     │
    │ meters → uint16 mm       │
    │ encode PNG               │
    └────────────┬─────────────┘
                 │
                 │ HTTP response
                 │ image/png
                 ▼
          16-bit depth map
```

The following tests interact with the server:
- `tests/test_depth_server.py`
- `tests/test_depth_server_gui.py`
- `tests/test_depth_webcam.py`

A stand-alone `tests/test_depth.py` can directly call Depth Anything V2 model (while running under a [virtual environment](https://github.com/slgrobotics/articubot_one/wiki/Depth-Anything-V2)).

### Depth node

A universal *depth_node* is included in the package. It subscribes to an image topic and queries the *Depth Anything V2 server*, publishing its response as depth maps/images.

This node works with the *HuskyLens 2 MCP node* (`launch/huskylens2_mcp.launch.py`), or any other node publishing compressed images.

Make sure that the Depth Anything V2 server is running, e.g.:
```
  cd ~/husky_ws/src/huskylens2_ros2/depth_anything
  ... activate your Python 3 virtual environment ...
  ./depth_server.py
```

Run it (on the same machine as *Depth Anything V2 server* to minimize image traffic):
```
ros2 run huskylens2_ros2 depth_node

  or

ros2 run huskylens2_ros2 depth_node --ros-args -p depth_server:=http://127.0.0.1:5001/depth
```

```    
     ROS 2 HuskyLens 2 MCP node
                    │
                    │ huskylens/image/compressed topic
                    ▼
     ROS 2 depth_node -----┐
                           │ HTTP POST
                           ▼
                        ┌──────────────────────────┐
                        │ Depth Anything V2 server │
                        └──┬───────────────────────┘
                           ▼ HTTP response -  16-bit depth map
     ROS 2 depth_node -----┘
                 │  `huskylens/depth/image` topic
                 ▼
        Any ROS2 subscribers
```

This is how an image from HuskyLens 2 is transferred:

`huskylens/image/compressed` as came from *HuskyLens 2 MCP Server*:

<img width="757" height="567" alt="Screenshot from 2026-09-15 17-08-00" src="https://github.com/user-attachments/assets/866af907-b61e-4dff-a46e-b22270b31044" />

Depth image returned by *Depth Anything V2 server* and published by *depth_node* as `huskylens/depth/image`:

<img width="757" height="567" alt="Screenshot from 2026-09-15 17-07-47" src="https://github.com/user-attachments/assets/bb1fea82-c46f-45af-97d7-a5b0faf03fe5" />

### Producing PointCloud2 from Depth topic

The standard ROS 2 package for this is [depth_image_proc](https://github.com/ros-perception/image_pipeline), specifically its *PointCloudXyzNode*. 
It takes a metric depth *sensor_msgs/Image* plus the corresponding *sensor_msgs/CameraInfo* and publishes *sensor_msgs/PointCloud2*.
The implementation supports 16UC1 depth images.

There is fair amount of [documentation](https://docs.ros.org/en/rolling/p/image_pipeline/) available.

The package can be installed from the binaries:
```
sudo apt install ros-${ROS_DISTRO}-image-pipeline
```

When using Depth Anything pipeline, the intended flow is:
```
     Camera Publisher Node ──────┐
             │                   │
             ▼                   │
       sensor_msgs/Image         │
             ↓                   │
     ROS 2 client (depth_node)   │
             ↓ HTTP POST         │
       Depth Anything server     │
             ↓                   │
       16-bit PNG, millimeters   │
             ↓ HTTP              │
     ROS 2 client (depth_node)   │
             │                   │
             ▼                   ▼
      sensor_msgs/Image    sensor_msgs/CameraInfo
      (encoding: 16UC1)          ↓
             ↓                   ↓
      depth_image_proc::PointCloudXyzNode
             │
             ▼
      sensor_msgs/PointCloud2
```
**Note:**
- you don't need *HuskyLens 2* to implement this pipeline. Regular cameras and even webcams with their ROS2 drivers nodes produce images and *CloudInfo* to feed the pipeline.
- you need *CameraInfo*, not just the depth image. The conversion needs the *camera intrinsics fx, fy, cx, cy* to back-project each depth pixel (distance from camera) *(u,v,Z)* into 3D space *XYZ*
- If you also want an *XYZRGB colored point cloud*, *depth_image_proc* has a *PointCloudXyzrgbNode*, which combines depth with the RGB image.

For HuskyLens 2 run conversion as follows:
```
ros2 launch huskylens2_ros2 point_cloud_node.launch.py
```

<img alt="PointCloud2 in RViz" src="https://github.com/user-attachments/assets/646f6037-8f22-4a00-a85c-cb862e898007" />

<img alt="PointCloud2 in RViz axis color" src="https://github.com/user-attachments/assets/752ef786-574f-41e9-82d1-50686b1652a9" />

----------------------

And, with *PointCloudXyzrgbNode*:
```
ros2 launch huskylens2_ros2 point_cloud_rgb_node.launch.py
```

<img alt="PointCloud2 in RViz RGB color" src="https://github.com/user-attachments/assets/39f565d6-7001-4ee3-a5ed-700c432bca81" />

<img alt="RQT_graph" src="https://github.com/user-attachments/assets/b4ccc447-899f-492b-885b-fa089bcce340" />


-------------------------

Back to [Main Project Home](https://github.com/slgrobotics/articubot_one/wiki)
