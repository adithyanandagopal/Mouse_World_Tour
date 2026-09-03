"""User-adjustable settings: calibration, start location, theme.

Persisted to data/config.json so calibration survives restarts.
"""
import json
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
CONFIG_FILE = os.path.join(DATA_DIR, "config.json")

DEFAULT_CONFIG = {
    # How many screen pixels of mouse movement equal one virtual kilometre.
    # Lower value = faster virtual travel for the same physical mouse movement.
    "pixel_to_km": 100.0,
    # A new route waypoint is recorded every time this many virtual km accumulate.
    "waypoint_interval_km": 0.1,
    # How often (ms) the mouse position is sampled.
    "poll_interval_ms": 50,
    "start_lat": 9.9312,
    "start_lon": 76.2673,
    "start_name": "Kochi, India",
    "theme": "dark",
    "sound_enabled": True,
}

START_PRESETS = [
    ("Kochi, India", 9.9312, 76.2673),
    ("New York, USA", 40.7128, -74.0060),
    ("London, UK", 51.5074, -0.1278),
    ("Tokyo, Japan", 35.6762, 139.6503),
    ("Sydney, Australia", -33.8688, 151.2093),
    ("Cairo, Egypt", 30.0444, 31.2357),
    ("Rio de Janeiro, Brazil", -22.9068, -43.1729),
]


class Config:
    """Loads/saves settings as a flat JSON dict."""

    def __init__(self):
        os.makedirs(DATA_DIR, exist_ok=True)
        self.data = dict(DEFAULT_CONFIG)
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                self.data.update(loaded)
            except (json.JSONDecodeError, OSError):
                pass

    def save(self):
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2)

    def __getattr__(self, name):
        # Only called when normal attribute lookup fails.
        try:
            return self.data[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    def set(self, name, value):
        self.data[name] = value
