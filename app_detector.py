"""ApplicationDetector: finds the active window and extracts a compass direction.

Direction rule: scan the active window's title bar text left-to-right and
return the first letter (case-insensitive) that is one of N/E/S/W. If no
such letter appears, there is no direction ("No movement") for this tick.
This is a deterministic, documented rule -- real window titles vary a lot
(document names, tab titles, etc.) so the resulting letter will vary too.
"""
import win32gui
import win32process

try:
    import psutil
except ImportError:  # psutil is optional; only used for a friendlier app name
    psutil = None

COMPASS_LETTERS = {"N", "E", "S", "W"}
COMPASS_NAMES = {"N": "North", "E": "East", "S": "South", "W": "West"}


class ApplicationDetector:
    def get_active_info(self):
        """Returns (window_title, process_name)."""
        try:
            hwnd = win32gui.GetForegroundWindow()
            if not hwnd:
                return "Unknown", "Unknown"
            title = win32gui.GetWindowText(hwnd) or "Unknown"
            process_name = "Unknown"
            if psutil is not None:
                try:
                    _, pid = win32process.GetWindowThreadProcessId(hwnd)
                    process_name = psutil.Process(pid).name()
                    if process_name.lower().endswith(".exe"):
                        process_name = process_name[:-4]
                except (psutil.NoSuchProcess, psutil.AccessDenied, Exception):
                    pass
            return title, process_name
        except Exception:
            return "Unknown", "Unknown"

    def extract_direction(self, window_title):
        for ch in window_title:
            up = ch.upper()
            if up in COMPASS_LETTERS:
                return up
        return None
