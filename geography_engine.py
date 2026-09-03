"""GeographyEngine: converts direction + virtual distance into lat/lon movement."""
import math

# 1 km of north/south travel is ~0.00899 degrees of latitude everywhere on Earth.
LAT_DEG_PER_KM = 0.00899


class GeographyEngine:
    def __init__(self, lat, lon):
        self.lat = lat
        self.lon = lon

    def _lon_deg_per_km(self):
        # Longitude degrees per km shrink toward the poles (meridians converge).
        cos_lat = max(math.cos(math.radians(self.lat)), 1e-6)
        return LAT_DEG_PER_KM / cos_lat

    def move(self, direction, distance_km):
        """Advance the virtual position. direction is 'N'/'E'/'S'/'W' or None."""
        if distance_km <= 0 or direction is None:
            return
        if direction == "N":
            self.lat += distance_km * LAT_DEG_PER_KM
        elif direction == "S":
            self.lat -= distance_km * LAT_DEG_PER_KM
        elif direction == "E":
            self.lon += distance_km * self._lon_deg_per_km()
        elif direction == "W":
            self.lon -= distance_km * self._lon_deg_per_km()

        self.lat = max(-90.0, min(90.0, self.lat))
        self.lon = ((self.lon + 180.0) % 360.0) - 180.0

    def position(self):
        return self.lat, self.lon

    def set_position(self, lat, lon):
        self.lat = lat
        self.lon = lon
