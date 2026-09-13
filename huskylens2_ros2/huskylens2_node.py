"""Minimal HuskyLens 2 node; hardware communication is not implemented yet."""

import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node


class HuskyLens2Node(Node):
    """Placeholder for device connection, polling, and ROS publishers."""

    def __init__(self):
        super().__init__('huskylens2_node')
        self.declare_parameter('frame_id', 'huskylens2_link')

        # TODO: Declare transport parameters and connect to the device.
        # TODO: Create publishers and a timer to read and publish device data.
        self.get_logger().info('HuskyLens 2 node started (stub).')


def main(args=None):
    rclpy.init(args=args)
    node = None
    try:
        node = HuskyLens2Node()
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        if node is not None:
            node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
