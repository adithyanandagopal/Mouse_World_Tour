"""MouseTracker: polls the OS cursor position in a background thread.

Runs as a QThread so it never blocks the UI. Emits a Qt signal carrying the
pixel distance moved since the last sample; Qt marshals the signal onto the
GUI thread automatically.
"""
import math
import time

import win32api
from PyQt6.QtCore import QThread, pyqtSignal


class MouseTracker(QThread):
    movement = pyqtSignal(float)  # pixel distance moved since last sample

    def __init__(self, poll_interval_ms=50, parent=None):
        super().__init__(parent)
        self.poll_interval = poll_interval_ms / 1000.0
        self._running = False
        self._last_pos = None

    def set_poll_interval(self, ms):
        self.poll_interval = max(10, ms) / 1000.0

    def run(self):
        self._running = True
        self._last_pos = win32api.GetCursorPos()
        while self._running:
            time.sleep(self.poll_interval)
            try:
                pos = win32api.GetCursorPos()
            except Exception:
                continue
            if self._last_pos is not None:
                dx = pos[0] - self._last_pos[0]
                dy = pos[1] - self._last_pos[1]
                dist = math.hypot(dx, dy)
                if dist > 0:
                    self.movement.emit(dist)
            self._last_pos = pos

    def stop(self):
        self._running = False
        self.wait(1000)
