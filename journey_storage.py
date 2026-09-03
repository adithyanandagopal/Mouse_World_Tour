"""JourneyStorage: persists journey data locally as JSON.

Layout:
  data/lifetime_stats.json   -- running totals, survives forever
  data/journeys/YYYY-MM-DD.json -- list of waypoints recorded that day
"""
import json
import os
from datetime import date

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
JOURNEYS_DIR = os.path.join(DATA_DIR, "journeys")
LIFETIME_FILE = os.path.join(DATA_DIR, "lifetime_stats.json")

DEFAULT_LIFETIME = {
    "lifetime_distance_km": 0.0,
    "distance_by_direction": {"N": 0.0, "E": 0.0, "S": 0.0, "W": 0.0},
    "application_changes": 0,
    "route_segments": 0,
    "total_tracking_seconds": 0,
    "achieved_milestones": [],
    "last_process": None,
    "current_lat": None,
    "current_lon": None,
    "origin_lat": None,
    "origin_lon": None,
    "origin_name": None,
}


class JourneyStorage:
    def __init__(self):
        os.makedirs(JOURNEYS_DIR, exist_ok=True)
        self.lifetime = self._load_json(LIFETIME_FILE, DEFAULT_LIFETIME)

    @staticmethod
    def _load_json(path, default):
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                merged = dict(default)
                merged.update(data)
                return merged
            except (json.JSONDecodeError, OSError):
                return dict(default)
        return dict(default)

    def save_lifetime(self):
        tmp = LIFETIME_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.lifetime, f, indent=2)
        os.replace(tmp, LIFETIME_FILE)

    @staticmethod
    def _day_path(day_str):
        return os.path.join(JOURNEYS_DIR, f"{day_str}.json")

    def today_str(self):
        return date.today().isoformat()

    def load_day(self, day_str):
        path = self._day_path(day_str)
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError):
                return []
        return []

    def load_today_waypoints(self):
        return self.load_day(self.today_str())

    def append_waypoint(self, waypoint, day_str=None):
        day_str = day_str or self.today_str()
        points = self.load_day(day_str)
        points.append(waypoint)
        tmp = self._day_path(day_str) + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(points, f, indent=2)
        os.replace(tmp, self._day_path(day_str))

    def list_days(self):
        days = []
        for fname in sorted(os.listdir(JOURNEYS_DIR)):
            if fname.endswith(".json"):
                days.append(fname[:-5])
        return days

    def day_distance(self, day_str):
        points = self.load_day(day_str)
        return sum(p.get("distance_km", 0.0) for p in points)

    def all_days_waypoints(self):
        """All waypoints across all days, in chronological order."""
        all_points = []
        for day_str in self.list_days():
            all_points.extend(self.load_day(day_str))
        return all_points

    def reset_all(self):
        """Wipe lifetime stats and every recorded day. Irreversible."""
        self.lifetime = dict(DEFAULT_LIFETIME)
        self.save_lifetime()
        for fname in os.listdir(JOURNEYS_DIR):
            if fname.endswith(".json"):
                try:
                    os.remove(os.path.join(JOURNEYS_DIR, fname))
                except OSError:
                    pass
