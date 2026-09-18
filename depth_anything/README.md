
## Running HTTP Depth Server 

Install *Python virtual environment*:

```
sudo apt install python3.14-venv

cd husky_ws/src/huskylens2_ros2/depth_anything/
python3 -m venv venv
source venv/bin/activate
```

With the virtual environment activated install *PyTorch*:

```
python -m pip install --upgrade pip
pip install torch torchvision
```

Check *PyTorch* installation:
```
python -c "import torch; print('PyTorch:', torch.__version__); print('CUDA:', torch.cuda.is_available()); print('GPU:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'NONE')"
   PyTorch: 2.14.0+cu130
   CUDA: True
   GPU: NVIDIA GeForce RTX 3060 Ti
```

More installs:
```
pip install "transformers>=4.45" pillow opencv-python
pip install fastapi uvicorn

```

Run the server:
```
./depth_server.py

```

It should be ready to take HTTP/POST images and will return depth maps/images in PNG uint_16 format, ready for ROS2 processing.

-------------------------

Back to [Package README](https://github.com/slgrobotics/huskylens2_ros2/blob/main/README.md)

Back to [Main Project Home](https://github.com/slgrobotics/articubot_one/wiki)
