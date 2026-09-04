"""Mouse World Tour -- your mouse is secretly circling the globe.

Entry point. Runs as a background tray app: mouse tracking, direction
detection, geography updates, and storage all keep running whether or not
the window is open. Opening the window ("World Tour") shows a full-bleed
3D globe with a small corner stats card; the detailed dashboard (per-
direction breakdown, app-change counters, etc.) lives in its own dialog.
"""
import sys
from datetime import datetime

from PyQt6.QtCore import QEvent, Qt, QCoreApplication, QSharedMemory, QTimer
from PyQt6.QtGui import QFont, QIcon, QPainter, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QFileDialog,
    QInputDialog,
    QMainWindow,
    QMenu,
    QMessageBox,
    QSystemTrayIcon,
    QVBoxLayout,
)

# Must be set before QApplication is constructed for QtWebEngine to behave.
QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)

from app_detector import ApplicationDetector, COMPASS_NAMES
from city_lookup import nearest_city
from config import Config
from dashboard_ui import HistoryDialog, ReplayDialog, SettingsDialog, StatsPanel, WelcomeDialog
from geography_engine import GeographyEngine
from globe_visualizer import GlobeVisualizer
from gpx_export import write_gpx
from journey_storage import JourneyStorage
from milestone_manager import MilestoneManager
from mouse_tracker import MouseTracker

try:
    import winsound
except ImportError:
    winsound = None

DARK_QSS = """
QMainWindow, QWidget, QDialog { background-color: #12151f; color: #e8e8ec; font-family: 'Segoe UI'; }
QGroupBox { border: 1px solid #2a2f3d; border-radius: 8px; margin-top: 10px; padding-top: 8px; font-weight: 600; }
QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 4px; color: #c7cede; }
QPushButton { background-color: #1e2330; border: 1px solid #333a4d; border-radius: 6px; padding: 6px 10px; }
QPushButton:hover { background-color: #2a3145; }
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QTableWidget { background-color: #1a1e2a; border: 1px solid #333a4d; border-radius: 4px; padding: 3px; }
QMenuBar { background-color: #12151f; }
QMenuBar::item:selected { background-color: #2a3145; }
QMenu { background-color: #1a1e2a; }
QMenu::item:selected { background-color: #2a3145; }
"""

LIGHT_QSS = """
QMainWindow, QWidget, QDialog { background-color: #f4f5f8; color: #202430; font-family: 'Segoe UI'; }
QGroupBox { border: 1px solid #d6d9e2; border-radius: 8px; margin-top: 10px; padding-top: 8px; font-weight: 600; }
QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 4px; }
QPushButton { background-color: #ffffff; border: 1px solid #c7cbd6; border-radius: 6px; padding: 6px 10px; }
QPushButton:hover { background-color: #e8eaf0; }
"""


def format_duration(total_seconds):
    total_seconds = int(total_seconds)
    days, rem = divmod(total_seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, seconds = divmod(rem, 60)
    if days:
        return f"{days}d {hours:02d}h {minutes:02d}m"
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def make_emoji_icon(emoji, size=64):
    pix = QPixmap(size, size)
    pix.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pix)
    font = QFont()
    font.setPointSize(int(size * 0.55))
    painter.setFont(font)
    painter.drawText(pix.rect(), Qt.AlignmentFlag.AlignCenter, emoji)
    painter.end()
    return QIcon(pix)


class DashboardDialog(QDialog):

    def __init__(self, stats_panel, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Mouse World Tour -- Dashboard")
        layout = QVBoxLayout(self)
        layout.addWidget(stats_panel)
        self.resize(340, 560)


class MouseWorldTourApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Mouse World Tour")
        self.resize(1400, 850)

        self.config = Config()
        self.storage = JourneyStorage()
        self.detector = ApplicationDetector()

        first_run = self.storage.lifetime.get("origin_lat") is None
        self._run_welcome_dialog(first_run)

        if first_run:
            lat, lon = self.config.start_lat, self.config.start_lon
            self.storage.lifetime["origin_lat"] = lat
            self.storage.lifetime["origin_lon"] = lon
            self.storage.lifetime["origin_name"] = self.config.start_name
            self.storage.lifetime["current_lat"] = lat
            self.storage.lifetime["current_lon"] = lon
            self.storage.save_lifetime()
        else:
            lat = self.storage.lifetime["current_lat"]
            lon = self.storage.lifetime["current_lon"]

        self.geo = GeographyEngine(lat, lon)
        self.milestones = MilestoneManager(self.storage.lifetime.get("achieved_milestones"))

        self.pending_waypoint_km = 0.0
        self.last_process_name = self.storage.lifetime.get("last_process")
        self._today_str = self.storage.today_str()
        self._today_total = self.storage.day_distance(self._today_str)
        self._replay_active = False
        self._window_visible = False
        self._dashboard_open = False
        self._quitting = False
        self._last_direction = None
        self._lifetime_dirty = False

        self._build_ui()
        self._apply_theme(self.config.theme)
        self._load_initial_route()

        self.tracker = MouseTracker(poll_interval_ms=self.config.poll_interval_ms)
        self.tracker.movement.connect(self.on_mouse_moved)
        self.tracker.start()

        # A fixed 2s interval meant up to 2s of progress could vanish if the
        # app was killed (or crashed) before the next tick. Saving only when
        # something actually changed, checked every 300ms, shrinks that
        # window by ~85% without writing to disk on every single mouse tick.
        self.save_timer = QTimer(self)
        self.save_timer.timeout.connect(self._flush_lifetime_if_dirty)
        self.save_timer.start(300)

        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self._refresh_active_app)
        self.refresh_timer.start(500)

        self.clock_timer = QTimer(self)
        self.clock_timer.timeout.connect(self._tick_clock)
        self.clock_timer.start(1000)

        self._update_stats_labels(process_name=self.last_process_name, direction=None)

        # Background tray app: start hidden, tracking silently.
        self.tray.showMessage(
            "Mouse World Tour",
            "Tracking started in the background. Click the tray icon to view your world tour.",
            QSystemTrayIcon.MessageIcon.Information,
            4000,
        )

    #setup 
    def _run_welcome_dialog(self, first_run):
        dlg = WelcomeDialog(self.config)
        dlg.exec()
        values = dlg.result_values()
        self.config.set("pixel_to_km", values["pixel_to_km"])
        if first_run:
            self.config.set("start_name", values["start_name"])
            self.config.set("start_lat", values["start_lat"])
            self.config.set("start_lon", values["start_lon"])
        self.config.save()

    def _build_ui(self):
        # The globe fills the entire window -- it IS the "World Tour" view.
        self.globe = GlobeVisualizer()
        self.setCentralWidget(self.globe)

        # Detailed stats live in a separate, optional dashboard dialog so the
        # globe view itself stays a clean, full-bleed 3D earth.
        self.stats_panel = StatsPanel(
            on_replay=lambda: self.start_replay_for_day(self.storage.today_str()),
            on_settings=self.open_settings,
            on_history=self.open_history,
            on_export=self.export_route,
            on_reset=self.reset_journey,
        )
        self.dashboard_dialog = None

        menu = self.menuBar()
        journey_menu = menu.addMenu("&Journey")
        journey_menu.addAction("Dashboard", self.open_dashboard)
        journey_menu.addAction("Settings", self.open_settings)
        journey_menu.addAction("History", self.open_history)
        journey_menu.addAction("Replay Today", lambda: self.start_replay_for_day(self.storage.today_str()))
        journey_menu.addAction("Export Route", self.export_route)
        journey_menu.addSeparator()
        journey_menu.addAction("Reset", self.reset_journey)
        journey_menu.addSeparator()
        journey_menu.addAction("Minimize to Tray", self.hide_to_tray)
        journey_menu.addAction("Quit", self.quit_app)

        self._build_tray()

    def _build_tray(self):
        self.tray_icon = make_emoji_icon("🐭")
        self.tray = QSystemTrayIcon(self.tray_icon, self)
        self.tray.setToolTip("Mouse World Tour")

        menu = QMenu()
        menu.addAction("Show World Tour", self.show_world_tour)
        menu.addAction("Dashboard", self.open_dashboard)
        menu.addSeparator()
        menu.addAction("Settings", self.open_settings)
        menu.addAction("History", self.open_history)
        menu.addAction("Replay Today", lambda: self.start_replay_for_day(self.storage.today_str()))
        menu.addAction("Export Route", self.export_route)
        menu.addSeparator()
        menu.addAction("Reset", self.reset_journey)
        menu.addSeparator()
        menu.addAction("Quit", self.quit_app)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.show()

    def _on_tray_activated(self, reason):
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            self.show_world_tour()

    def _apply_theme(self, theme):
        self.setStyleSheet(DARK_QSS if theme == "dark" else LIGHT_QSS)

    def _globe_live(self):
        """True when it's OK to push route/position updates to the globe --
        i.e. not while replaying a past day, and not while the stats
        dashboard (with its location-guessing game) is open."""
        return self._window_visible and not self._replay_active and not self._dashboard_open

    def _load_initial_route(self):
        origin_lat = self.storage.lifetime["origin_lat"]
        origin_lon = self.storage.lifetime["origin_lon"]
        waypoints = self.storage.all_days_waypoints()
        self.globe.init_route(origin_lat, origin_lon, waypoints)

    def _mark_lifetime_dirty(self):
        self._lifetime_dirty = True

    def _flush_lifetime_if_dirty(self):
        if self._lifetime_dirty:
            self.storage.save_lifetime()
            self._lifetime_dirty = False

    #  window visibility: show = "World Tour", hide = background tray
    def show_world_tour(self):
        self._window_visible = True
        self.showMaximized()
        self.raise_()
        self.activateWindow()
        self._load_initial_route()  # resync in case anything moved while hidden
        self._push_overlay_stats()

    def hide_to_tray(self):
        self._window_visible = False
        self.hide()
        # This is the moment a user thinks of as "closing the app" -- make
        # sure nothing tracked so far is left sitting unsaved.
        self._flush_lifetime_if_dirty()

    def changeEvent(self, event):
        # Treat a plain OS-level minimize the same as "send to tray", so the
        # window never sits minimized on the taskbar collecting dust.
        if event.type() == QEvent.Type.WindowStateChange and self.isMinimized():
            QTimer.singleShot(0, self.hide_to_tray)
        super().changeEvent(event)

    def closeEvent(self, event):
        if self._quitting:
            super().closeEvent(event)
            return
        # Clicking the X just tucks the app into the tray; tracking continues.
        event.ignore()
        self.hide_to_tray()

    # ---------- live tracking (always runs, regardless of window visibility) ----------
    def on_mouse_moved(self, dist_px):
        dist_km = dist_px / self.config.pixel_to_km
        title, process_name = self.detector.get_active_info()
        direction = self.detector.extract_direction(title)

        if process_name != self.last_process_name:
            self.storage.lifetime["application_changes"] = (
                self.storage.lifetime.get("application_changes", 0) + 1
            )
            self.last_process_name = process_name
            self.storage.lifetime["last_process"] = process_name
            self._mark_lifetime_dirty()

        today = self.storage.today_str()
        if today != self._today_str:
            self._today_str = today
            self._today_total = 0.0

        if direction is not None and dist_km > 0:
            self.geo.move(direction, dist_km)
            lat, lon = self.geo.position()

            dbd = self.storage.lifetime["distance_by_direction"]
            dbd[direction] = dbd.get(direction, 0.0) + dist_km
            self.storage.lifetime["lifetime_distance_km"] = (
                self.storage.lifetime.get("lifetime_distance_km", 0.0) + dist_km
            )
            self.storage.lifetime["current_lat"] = lat
            self.storage.lifetime["current_lon"] = lon
            self._today_total += dist_km
            self._mark_lifetime_dirty()

            self.pending_waypoint_km += dist_km
            if self.pending_waypoint_km >= self.config.waypoint_interval_km:
                waypoint = {
                    "lat": lat,
                    "lon": lon,
                    "timestamp": datetime.now().isoformat(timespec="seconds"),
                    "application": process_name,
                    "direction": direction,
                    "distance_km": self.pending_waypoint_km,
                }
                self.storage.append_waypoint(waypoint)
                self.storage.lifetime["route_segments"] = (
                    self.storage.lifetime.get("route_segments", 0) + 1
                )
                if self._globe_live():
                    self.globe.add_waypoint(lat, lon, direction)
                self.pending_waypoint_km = 0.0

            if self._globe_live():
                self.globe.update_position(lat, lon, direction)

            newly = self.milestones.check(self.storage.lifetime["lifetime_distance_km"])
            if newly:
                self.storage.lifetime["achieved_milestones"] = list(self.milestones.achieved)
                for threshold, name, emoji in newly:
                    self._show_milestone(name, emoji)

        self._last_direction = direction
        self._update_stats_labels(process_name, direction)
        if self._globe_live():
            self._push_overlay_stats()

    def _refresh_active_app(self):
        title, process_name = self.detector.get_active_info()
        direction = self.detector.extract_direction(title)
        self._update_stats_labels(process_name, direction)

    def _tick_clock(self):
        self.storage.lifetime["total_tracking_seconds"] = (
            self.storage.lifetime.get("total_tracking_seconds", 0) + 1
        )
        self._mark_lifetime_dirty()
        if self._globe_live():
            self._push_overlay_stats()

    def _push_overlay_stats(self):
        lat, lon = self.geo.position()
        distance_km = self.storage.lifetime.get("lifetime_distance_km", 0.0)
        city = nearest_city(lat, lon)
        time_str = format_duration(self.storage.lifetime.get("total_tracking_seconds", 0))
        self.globe.update_overlay_stats(distance_km, city, time_str)

    def _update_stats_labels(self, process_name, direction):
        stats = self.storage.lifetime
        lat, lon = self.geo.position()
        self.stats_panel.total_distance.set_value(f"{stats.get('lifetime_distance_km', 0.0):.2f} km")
        self.stats_panel.current_app.set_value(process_name or "--")
        direction_text = COMPASS_NAMES.get(direction, "No movement") if direction else "No movement"
        self.stats_panel.current_direction.set_value(direction_text)
        self.stats_panel.current_location.set_value(f"{lat:.4f}, {lon:.4f}")

        dbd = stats.get("distance_by_direction", {})
        self.stats_panel.dist_n.set_value(f"{dbd.get('N', 0.0):.2f} km")
        self.stats_panel.dist_e.set_value(f"{dbd.get('E', 0.0):.2f} km")
        self.stats_panel.dist_s.set_value(f"{dbd.get('S', 0.0):.2f} km")
        self.stats_panel.dist_w.set_value(f"{dbd.get('W', 0.0):.2f} km")

        self.stats_panel.app_changes.set_value(str(stats.get("application_changes", 0)))
        self.stats_panel.route_segments.set_value(str(stats.get("route_segments", 0)))
        self.stats_panel.today_distance.set_value(f"{self._today_total:.2f} km")
        self.stats_panel.lifetime_distance.set_value(f"{stats.get('lifetime_distance_km', 0.0):.2f} km")

    def _show_milestone(self, name, emoji):
        message = f"{emoji} Milestone unlocked: {name}!"
        self.tray.showMessage("Mouse World Tour", message, QSystemTrayIcon.MessageIcon.Information, 4000)
        if self.config.sound_enabled and winsound is not None:
            try:
                winsound.MessageBeep(winsound.MB_ICONASTERISK)
            except Exception:
                pass

    #  menu / tray actions 
    def open_dashboard(self):
        if not self._window_visible:
            self.show_world_tour()

        if self.dashboard_dialog is None:
            self.dashboard_dialog = DashboardDialog(self.stats_panel, parent=self)
            self.dashboard_dialog.finished.connect(self._on_dashboard_closed)
        self.dashboard_dialog.show()
        self.dashboard_dialog.raise_()
        self.dashboard_dialog.activateWindow()

        # Opening the dashboard freezes the live route on the globe and
        # kicks off a quick "guess the distance" mini-game instead.
        self._dashboard_open = True
        self._run_distance_guess_game()

    def _on_dashboard_closed(self):
        self._dashboard_open = False
        if self._window_visible and not self._replay_active:
            self._load_initial_route()
            self._push_overlay_stats()

    def _set_distance_stats_hidden(self, hidden):
        if hidden:
            placeholder = "❓"
            for row in (
                self.stats_panel.total_distance,
                self.stats_panel.lifetime_distance,
                self.stats_panel.today_distance,
                self.stats_panel.dist_n,
                self.stats_panel.dist_e,
                self.stats_panel.dist_s,
                self.stats_panel.dist_w,
            ):
                row.set_value(placeholder)
        self.globe.set_distance_hidden(hidden)

    @staticmethod
    def _guess_feedback(accuracy):
        if accuracy >= 90:
            return "good job!! 🎉"
        if accuracy >= 70:
            return "not bad!"
        if accuracy >= 40:
            return "eh, could be better."
        return "yikes, way off 😅"

    def _run_distance_guess_game(self):
        actual = self.storage.lifetime.get("lifetime_distance_km", 0.0)
        self._set_distance_stats_hidden(True)

        guess, ok = QInputDialog.getDouble(
            self,
            "🌍 Guess Your Journey!",
            "How many kilometres do you think your mouse has travelled so far?",
            value=0.0,
            min=0.0,
            max=1_000_000.0,
            decimals=1,
        )

        if ok:
            if actual > 0:
                error_pct = abs(guess - actual) / actual * 100.0
                accuracy = max(0.0, 100.0 - error_pct)
            else:
                accuracy = 100.0 if guess == 0 else 0.0
            feedback = self._guess_feedback(accuracy)
            QMessageBox.information(
                self,
                "Guess Results",
                f"Your guess: {guess:.1f} km\n"
                f"Actual distance: {actual:.2f} km\n\n"
                f"You guessed {accuracy:.1f}% correct -- {feedback}",
            )

        # Reveal the real numbers again, whether they answered or cancelled.
        self._update_stats_labels(process_name=self.last_process_name, direction=self._last_direction)
        self._push_overlay_stats()

    def open_settings(self):
        dlg = SettingsDialog(self.config)
        if dlg.exec():
            values = dlg.result_values()
            for key, value in values.items():
                self.config.set(key, value)
            self.config.save()
            self.tracker.set_poll_interval(self.config.poll_interval_ms)
            self._apply_theme(self.config.theme)

    def open_history(self):
        dlg = HistoryDialog(self.storage, on_replay_day=self.start_replay_for_day, parent=self)
        dlg.exec()

    def start_replay_for_day(self, day_str):
        waypoints = self.storage.load_day(day_str)
        if not waypoints:
            QMessageBox.information(self, "Replay", f"No route recorded for {day_str} yet.")
            return
        if not self._window_visible:
            self.show_world_tour()
        self._replay_active = True
        origin_lat = self.storage.lifetime["origin_lat"]
        origin_lon = self.storage.lifetime["origin_lon"]
        dlg = ReplayDialog(self.globe, waypoints, origin_lat, origin_lon, self._restore_live_view, parent=self)
        dlg.exec()

    def _restore_live_view(self):
        self._replay_active = False
        self._load_initial_route()
        self._push_overlay_stats()

    def export_route(self):
        choice = QMessageBox.question(
            self,
            "Export Route",
            "Export today's route only?\n\nYes = Today only, No = Entire lifetime route",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel,
        )
        if choice == QMessageBox.StandardButton.Cancel:
            return
        waypoints = (
            self.storage.load_today_waypoints()
            if choice == QMessageBox.StandardButton.Yes
            else self.storage.all_days_waypoints()
        )
        if not waypoints:
            QMessageBox.information(self, "Export Route", "No route data to export yet.")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export Route as GPX", "mouse_world_tour.gpx", "GPX Files (*.gpx)")
        if not path:
            return
        write_gpx(path, waypoints)
        QMessageBox.information(self, "Export Route", f"Route exported to:\n{path}")

    def reset_journey(self):
        choice = QMessageBox.warning(
            self,
            "Reset Journey",
            "This permanently deletes your lifetime distance, history, and route.\n"
            "This cannot be undone. Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if choice != QMessageBox.StandardButton.Yes:
            return
        self.storage.reset_all()
        lat, lon = self.config.start_lat, self.config.start_lon
        self.storage.lifetime["origin_lat"] = lat
        self.storage.lifetime["origin_lon"] = lon
        self.storage.lifetime["origin_name"] = self.config.start_name
        self.storage.lifetime["current_lat"] = lat
        self.storage.lifetime["current_lon"] = lon
        self.storage.save_lifetime()
        self.geo.set_position(lat, lon)
        self.milestones = MilestoneManager()
        self.pending_waypoint_km = 0.0
        self._today_total = 0.0
        self._today_str = self.storage.today_str()
        self._load_initial_route()
        self._push_overlay_stats()
        self._update_stats_labels(process_name=None, direction=None)

    def quit_app(self):
        self._quitting = True
        self.tracker.stop()
        self.storage.save_lifetime()
        self.config.save()
        self.tray.hide()
        QApplication.instance().quit()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Mouse World Tour")
    app.setQuitOnLastWindowClosed(False)  # closing to tray must not exit the app

    # Refuse to start a second copy -- two instances would both write the
    # same data files (racing each other, and occasionally hitting a
    # WinError 5 when one tries to replace a file the other has open) and
    # would double-count your tracked distance. QSharedMemory.create() fails
    # if another instance already holds this key; Windows frees the key
    # automatically if that instance crashes, so this can't get stuck.
    single_instance_lock = QSharedMemory("MouseWorldTour-SingleInstanceLock-9f3a2b")
    if not single_instance_lock.create(1):
        QMessageBox.information(
            None,
            "Mouse World Tour",
            "Mouse World Tour is already running in the background.\n"
            "Look for the \U0001F42D icon in your system tray.",
        )
        sys.exit(0)

    window = MouseWorldTourApp()

    # Final safety net: catches Windows logoff/shutdown and any other
    # Qt-initiated quit path that doesn't go through quit_app() directly.
    def _final_flush():
        window.storage.save_lifetime()
        window.config.save()

    app.aboutToQuit.connect(_final_flush)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
