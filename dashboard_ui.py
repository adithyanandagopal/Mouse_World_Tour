import os

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from config import START_PRESETS

DIRECTION_COLORS_QT = {"N": "#4da3ff", "E": "#3ddc84", "S": "#ff5c6c", "W": "#ffd24d"}


class StatRow(QWidget):
    def __init__(self, label, value="--", accent=None):
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 2)
        self.name_label = QLabel(label)
        self.name_label.setStyleSheet("color: #9aa4b8; font-size: 12px;")
        self.value_label = QLabel(value)
        style = "font-size: 13px; font-weight: 600;"
        if accent:
            style += f" color: {accent};"
        self.value_label.setStyleSheet(style)
        self.value_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        layout.addWidget(self.name_label)
        layout.addStretch(1)
        layout.addWidget(self.value_label)

    def set_value(self, text):
        self.value_label.setText(text)


class StatsPanel(QWidget):
    """Left-side live statistics panel."""

    def __init__(self, on_replay, on_settings, on_history, on_export, on_reset, parent=None):
        super().__init__(parent)
        self.setFixedWidth(320)
        layout = QVBoxLayout(self)

        title = QLabel("🐭 Mouse World Tour")
        title.setStyleSheet("font-size: 20px; font-weight: 700;")
        subtitle = QLabel("Your boring mouse is secretly circling the globe.")
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet("color: #9aa4b8; font-size: 11px; margin-bottom: 6px;")
        layout.addWidget(title)
        layout.addWidget(subtitle)

        journey_box = QGroupBox("Live Journey")
        journey_layout = QVBoxLayout(journey_box)
        self.total_distance = StatRow("Total Distance", "0.00 km", "#f0c040")
        self.current_app = StatRow("Current Application", "--")
        self.current_direction = StatRow("Current Direction", "--")
        self.current_location = StatRow("Current Location", "--")
        for row in (self.total_distance, self.current_app, self.current_direction, self.current_location):
            journey_layout.addWidget(row)
        layout.addWidget(journey_box)

        direction_box = QGroupBox("Distance by Direction")
        direction_layout = QVBoxLayout(direction_box)
        self.dist_n = StatRow("North", "0.00 km", DIRECTION_COLORS_QT["N"])
        self.dist_e = StatRow("East", "0.00 km", DIRECTION_COLORS_QT["E"])
        self.dist_s = StatRow("South", "0.00 km", DIRECTION_COLORS_QT["S"])
        self.dist_w = StatRow("West", "0.00 km", DIRECTION_COLORS_QT["W"])
        for row in (self.dist_n, self.dist_e, self.dist_s, self.dist_w):
            direction_layout.addWidget(row)
        layout.addWidget(direction_box)

        session_box = QGroupBox("Session")
        session_layout = QVBoxLayout(session_box)
        self.app_changes = StatRow("Application Changes", "0")
        self.route_segments = StatRow("Route Segments", "0")
        self.today_distance = StatRow("Today's Distance", "0.00 km")
        self.lifetime_distance = StatRow("Lifetime Distance", "0.00 km")
        for row in (self.app_changes, self.route_segments, self.today_distance, self.lifetime_distance):
            session_layout.addWidget(row)
        layout.addWidget(session_box)

        layout.addStretch(1)

        btn_replay = QPushButton("▶ Replay Today")
        btn_replay.clicked.connect(on_replay)
        layout.addWidget(btn_replay)

        row1 = QHBoxLayout()
        btn_settings = QPushButton("Settings")
        btn_settings.clicked.connect(on_settings)
        btn_history = QPushButton("History")
        btn_history.clicked.connect(on_history)
        row1.addWidget(btn_settings)
        row1.addWidget(btn_history)
        layout.addLayout(row1)

        row2 = QHBoxLayout()
        btn_export = QPushButton("Export Route")
        btn_export.clicked.connect(on_export)
        btn_reset = QPushButton("Reset")
        btn_reset.setStyleSheet("color: #ff5c6c;")
        btn_reset.clicked.connect(on_reset)
        row2.addWidget(btn_export)
        row2.addWidget(btn_reset)
        layout.addLayout(row2)


class WelcomeDialog(QDialog):
    """First-screen calibration + start-location picker."""

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self.setWindowTitle("Welcome to Mouse World Tour")
        self.setMinimumWidth(420)

        layout = QVBoxLayout(self)
        intro = QLabel(
            "🐭 Your mouse is about to start a secret world tour.\n"
            "Every pixel you move gets converted into virtual kilometres, "
            "in a direction taken from whatever app is in focus."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        form = QFormLayout()

        self.pixel_to_km = QDoubleSpinBox()
        self.pixel_to_km.setRange(1.0, 100000.0)
        self.pixel_to_km.setDecimals(0)
        self.pixel_to_km.setSuffix(" px = 1 virtual km")
        self.pixel_to_km.setValue(config.pixel_to_km)
        form.addRow("Sensitivity:", self.pixel_to_km)

        self.preset_combo = QComboBox()
        for name, _, _ in START_PRESETS:
            self.preset_combo.addItem(name)
        self.preset_combo.addItem("Custom...")
        current_name = config.start_name
        idx = self.preset_combo.findText(current_name)
        if idx >= 0:
            self.preset_combo.setCurrentIndex(idx)
        else:
            self.preset_combo.setCurrentIndex(self.preset_combo.count() - 1)
        self.preset_combo.currentIndexChanged.connect(self._on_preset_changed)
        form.addRow("Starting location:", self.preset_combo)

        self.lat_edit = QLineEdit(str(config.start_lat))
        self.lon_edit = QLineEdit(str(config.start_lon))
        form.addRow("Latitude:", self.lat_edit)
        form.addRow("Longitude:", self.lon_edit)

        layout.addLayout(form)

        note = QLabel(
            "Note: the starting location only takes effect on first run or after Reset."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color: #9aa4b8; font-size: 11px;")
        layout.addWidget(note)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)

    def _on_preset_changed(self, idx):
        if idx < len(START_PRESETS):
            name, lat, lon = START_PRESETS[idx]
            self.lat_edit.setText(str(lat))
            self.lon_edit.setText(str(lon))

    def result_values(self):
        idx = self.preset_combo.currentIndex()
        if idx < len(START_PRESETS):
            name = START_PRESETS[idx][0]
        else:
            name = "Custom"
        try:
            lat = float(self.lat_edit.text())
            lon = float(self.lon_edit.text())
        except ValueError:
            lat, lon = self.config.start_lat, self.config.start_lon
        return {
            "pixel_to_km": float(self.pixel_to_km.value()),
            "start_name": name,
            "start_lat": lat,
            "start_lon": lon,
        }


class SettingsDialog(QDialog):
    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self.setWindowTitle("Settings")
        self.setMinimumWidth(380)
        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.pixel_to_km = QDoubleSpinBox()
        self.pixel_to_km.setRange(1.0, 100000.0)
        self.pixel_to_km.setDecimals(0)
        self.pixel_to_km.setSuffix(" px = 1 virtual km")
        self.pixel_to_km.setValue(config.pixel_to_km)
        form.addRow("Sensitivity:", self.pixel_to_km)

        self.waypoint_interval = QDoubleSpinBox()
        self.waypoint_interval.setRange(0.001, 10.0)
        self.waypoint_interval.setDecimals(3)
        self.waypoint_interval.setSuffix(" km per waypoint")
        self.waypoint_interval.setValue(config.waypoint_interval_km)
        form.addRow("Route detail:", self.waypoint_interval)

        self.poll_interval = QSpinBox()
        self.poll_interval.setRange(10, 500)
        self.poll_interval.setSuffix(" ms")
        self.poll_interval.setValue(config.poll_interval_ms)
        form.addRow("Mouse sample rate:", self.poll_interval)

        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["dark", "light"])
        self.theme_combo.setCurrentText(config.theme)
        form.addRow("Theme:", self.theme_combo)

        self.sound_combo = QComboBox()
        self.sound_combo.addItems(["On", "Off"])
        self.sound_combo.setCurrentText("On" if config.sound_enabled else "Off")
        form.addRow("Milestone sound:", self.sound_combo)

        layout.addLayout(form)

        note = QLabel("Starting location can only be changed via Reset.")
        note.setStyleSheet("color: #9aa4b8; font-size: 11px;")
        layout.addWidget(note)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def result_values(self):
        return {
            "pixel_to_km": float(self.pixel_to_km.value()),
            "waypoint_interval_km": float(self.waypoint_interval.value()),
            "poll_interval_ms": int(self.poll_interval.value()),
            "theme": self.theme_combo.currentText(),
            "sound_enabled": self.sound_combo.currentText() == "On",
        }


class HistoryDialog(QDialog):
    """Shows per-day distances, lifetime stats, a chart, and a Replay button."""

    def __init__(self, storage, on_replay_day, parent=None):
        super().__init__(parent)
        self.storage = storage
        self.on_replay_day = on_replay_day
        self.setWindowTitle("Journey History")
        self.setMinimumSize(600, 480)

        layout = QVBoxLayout(self)

        days = storage.list_days()
        distances = [(d, storage.day_distance(d)) for d in days]

        summary_box = QGroupBox("Summary")
        summary_layout = QFormLayout(summary_box)
        lifetime_km = storage.lifetime.get("lifetime_distance_km", 0.0)
        longest = max((d[1] for d in distances), default=0.0)
        average = (sum(d[1] for d in distances) / len(distances)) if distances else 0.0
        summary_layout.addRow("Lifetime Distance:", QLabel(f"{lifetime_km:.2f} km"))
        summary_layout.addRow("Longest Single Day:", QLabel(f"{longest:.2f} km"))
        summary_layout.addRow("Average Daily Distance:", QLabel(f"{average:.2f} km"))
        summary_layout.addRow("Days Tracked:", QLabel(str(len(distances))))
        layout.addWidget(summary_box)

        self.table = QTableWidget(len(distances), 2)
        self.table.setHorizontalHeaderLabels(["Date", "Distance (km)"])
        for row, (d, dist) in enumerate(distances):
            self.table.setItem(row, 0, QTableWidgetItem(d))
            self.table.setItem(row, 1, QTableWidgetItem(f"{dist:.2f}"))
        self.table.resizeColumnsToContents()
        layout.addWidget(self.table)

        chart = self._build_chart(distances)
        if chart is not None:
            layout.addWidget(chart)

        btn_row = QHBoxLayout()
        self.replay_btn = QPushButton("Replay Selected Day")
        self.replay_btn.clicked.connect(self._replay_selected)
        btn_row.addWidget(self.replay_btn)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

    def _build_chart(self, distances):
        try:
            from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
            from matplotlib.figure import Figure
        except ImportError:
            return None
        if not distances:
            return None
        fig = Figure(figsize=(5, 2.2), tight_layout=True)
        ax = fig.add_subplot(111)
        labels = [d for d, _ in distances]
        values = [v for _, v in distances]
        ax.bar(labels, values, color="#4da3ff")
        ax.set_ylabel("km")
        ax.tick_params(axis="x", rotation=45, labelsize=7)
        canvas = FigureCanvasQTAgg(fig)
        canvas.setFixedHeight(180)
        return canvas

    def _replay_selected(self):
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.information(self, "Replay", "Select a day in the table first.")
            return
        day_str = self.table.item(row, 0).text()
        self.on_replay_day(day_str)
        self.accept()


class ReplayDialog(QDialog):
    """Animates a day's waypoints on the shared globe."""

    def __init__(self, globe, waypoints, home_lat, home_lon, restore_callback, parent=None):
        super().__init__(parent)
        self.globe = globe
        self.waypoints = waypoints
        self.home_lat = home_lat
        self.home_lon = home_lon
        self.restore_callback = restore_callback
        self.index = 0
        self.speed = 1

        self.setWindowTitle("Journey Replay")
        self.setMinimumWidth(420)
        layout = QVBoxLayout(self)

        self.info_label = QLabel("Ready to replay.")
        self.info_label.setWordWrap(True)
        layout.addWidget(self.info_label)

        self.progress_label = QLabel(f"0 / {len(waypoints)} segments")
        layout.addWidget(self.progress_label)

        controls = QHBoxLayout()
        self.play_btn = QPushButton("▶ Play")
        self.play_btn.clicked.connect(self._toggle_play)
        controls.addWidget(self.play_btn)
        for speed in (1, 2, 4):
            btn = QPushButton(f"{speed}x")
            btn.clicked.connect(lambda _, s=speed: self._set_speed(s))
            controls.addWidget(btn)
        layout.addLayout(controls)

        close_btn = QPushButton("Close & Return to Live View")
        close_btn.clicked.connect(self._close_and_restore)
        layout.addWidget(close_btn)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._step)

        self.globe.replay_reset(home_lat, home_lon)

    def _set_speed(self, speed):
        self.speed = speed
        if self.timer.isActive():
            self.timer.setInterval(int(300 / self.speed))

    def _toggle_play(self):
        if self.timer.isActive():
            self.timer.stop()
            self.play_btn.setText("▶ Play")
        else:
            self.timer.start(int(300 / self.speed))
            self.play_btn.setText("⏸ Pause")

    def _step(self):
        if self.index >= len(self.waypoints):
            self.timer.stop()
            self.play_btn.setText("▶ Play")
            self.info_label.setText("Replay finished.")
            return
        wp = self.waypoints[self.index]
        self.globe.replay_step(wp["lat"], wp["lon"], wp.get("direction"))
        app = wp.get("application", "?")
        ts = wp.get("timestamp", "")
        direction = wp.get("direction", "?")
        self.info_label.setText(f"[{ts}] {app} -> moved {direction}")
        self.index += 1
        self.progress_label.setText(f"{self.index} / {len(self.waypoints)} segments")

    def _close_and_restore(self):
        self.timer.stop()
        self.restore_callback()
        self.accept()

    def closeEvent(self, event):
        self.timer.stop()
        self.restore_callback()
        super().closeEvent(event)
