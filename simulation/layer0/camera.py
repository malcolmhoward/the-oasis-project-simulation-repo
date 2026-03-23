"""
Layer 0: Camera metadata simulator.

Returns metadata dicts rather than actual image data.
No external runtime dependencies (numpy not required for this module).
"""

import time
import random
import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)


from simulation.hal.device import CameraInterface


class MockCamera(CameraInterface):
    """
    Mock camera that returns metadata dicts instead of pixel data.

    Implements :class:`~simulation.hal.device.CameraInterface`.

    Each ``capture()`` call returns a dict with the same keys a real camera
    driver would provide (frame number, timestamp, resolution, simulated
    statistics). The ``data`` field is a descriptive placeholder string.

    Example::

        with MockCamera(device_id=0, width=1920, height=1080, fps=30) as cam:
            frame = cam.capture()
            print(frame["frame_number"], frame["brightness"])
    """

    def __init__(
        self,
        device_id: int = 0,
        width: int = 1920,
        height: int = 1080,
        fps: int = 30,
    ):
        self.device_id   = device_id
        self.width       = width
        self.height      = height
        self.fps         = fps
        self.frame_count = 0
        self.is_open     = True
        self.start_time  = time.time()
        logger.info("MockCamera initialized (device %d, %dx%d @ %dfps)",
                    device_id, width, height, fps)

    def capture(self) -> Dict[str, Any]:
        """Return a simulated frame metadata dict."""
        if not self.is_open:
            raise RuntimeError("Camera is not open")
        self.frame_count += 1
        now = time.time()
        return {
            "frame_number": self.frame_count,
            "timestamp":    now,
            "elapsed_time": now - self.start_time,
            "width":        self.width,
            "height":       self.height,
            "device_id":    self.device_id,
            "fps":          self.fps,
            "brightness":   round(random.uniform(0.3, 0.8), 3),
            "contrast":     round(random.uniform(0.5, 1.0), 3),
            "data":         f"<simulated_frame_{self.frame_count}>",
        }

    def set_resolution(self, width: int, height: int):
        self.width  = width
        self.height = height

    def set_fps(self, fps: int):
        self.fps = fps

    def get_properties(self) -> Dict[str, Any]:
        return {
            "device_id":   self.device_id,
            "width":       self.width,
            "height":      self.height,
            "fps":         self.fps,
            "is_open":     self.is_open,
            "frame_count": self.frame_count,
        }

    def release(self):
        self.is_open = False
        logger.info("MockCamera released (device %d, %d frames captured)",
                    self.device_id, self.frame_count)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.release()

    def __repr__(self):
        return (f"MockCamera(device_id={self.device_id}, "
                f"{self.width}x{self.height} @ {self.fps}fps)")
