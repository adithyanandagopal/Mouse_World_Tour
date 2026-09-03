"""GlobeVisualizer: embeds the Cesium.js globe in a Qt widget and drives it
from Python by injecting small JavaScript calls.
"""
import json
import os

from PyQt6.QtCore import QUrl
from PyQt6.QtWebEngineCore import QWebEngineSettings
from PyQt6.QtWebEngineWidgets import QWebEngineView

WEB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")


class GlobeVisualizer(QWebEngineView):
    def __init__(self, parent=None):
        super().__init__(parent)
        index_path = os.path.join(WEB_DIR, "index.html")
        self._ready = False
        self._pending = []
        # index.html is loaded from file:// but pulls Cesium.js and its
        # imagery from a remote CDN -- Chromium blocks that by default for
        # local documents, which silently leaves the globe stuck "Loading".
        self.settings().setAttribute(
            QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True
        )
        self.loadFinished.connect(self._on_load_finished)
        self.load(QUrl.fromLocalFile(index_path))

    def _on_load_finished(self, ok):
        self._ready = ok
        pending, self._pending = self._pending, []
        for script in pending:
            self.page().runJavaScript(script)

    def _run(self, script):
        if self._ready:
            self.page().runJavaScript(script)
        else:
            self._pending.append(script)

    def init_route(self, home_lat, home_lon, waypoints):
        """waypoints: list of {'lat':..,'lon':..,'direction':..} in order."""
        payload = json.dumps({"home": [home_lat, home_lon], "waypoints": waypoints})
        self._run(f"window.initJourney({payload});")

    def add_waypoint(self, lat, lon, direction):
        d = direction or ""
        self._run(f"window.addWaypoint({lat}, {lon}, '{d}');")

    def update_position(self, lat, lon, direction):
        d = direction or ""
        self._run(f"window.updateCurrentPosition({lat}, {lon}, '{d}');")

    def update_overlay_stats(self, distance_km, city, time_str):
        self._run(
            f"window.updateOverlayStats({distance_km}, {json.dumps(city)}, {json.dumps(time_str)});"
        )

    def clear(self):
        self._run("window.clearJourney();")

    def replay_reset(self, home_lat, home_lon):
        self._run(f"window.replayReset({home_lat}, {home_lon});")

    def replay_step(self, lat, lon, direction):
        d = direction or ""
        self._run(f"window.replayStep({lat}, {lon}, '{d}');")
