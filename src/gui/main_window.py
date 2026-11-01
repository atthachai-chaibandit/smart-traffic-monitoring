
from pathlib import Path
from math import isfinite
from time import perf_counter

import cv2
import numpy as np

from PyQt6.QtCore import QThread, QTimer, Qt, pyqtSignal
from PyQt6.QtGui import QImage, QImageReader, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QHBoxLayout, QMainWindow, 
    QScrollArea, QVBoxLayout, 
    QWidget, QFileDialog, QMessageBox
)

from .app_title import AppTitle
from .control_panel import ControlPanel
from .preview_canvas import PreviewCanvas
from .media_formats import SUPPORTED_FILE_FORMATS
from .detection_worker import DetectionWorker
from .settings_dialog import AppSettings, SettingsDialog
from ..preprocessing import brighten_frame, mask_outside_roi

class MainWindow(QMainWindow):
    """Local media playback with image detection and continuous video tracking."""

    detect_frame_requested = pyqtSignal(object, int, int, int, bool, object, float)

    def __init__(self):
        super().__init__()

        # Window Configuration
        self.setWindowTitle("Smart Traffic Monitoring")
        self.resize(980, 680)
        self.setMinimumSize(800, 580)
        self.media_path = None
        self.raw_frame = None
        self.settings = AppSettings()
        self._detection_revision = 0
        self._tracking_session = 0
        self._detection_busy = False
        self._detection_roi = ()
        self._counting_line = ()
        self._closing = False
        self.is_playing = False
        self.continuous_detection = False
        # Keep at most one decoded frame waiting for its matching detection result.
        self._next_detection_frame = None
        self._active_detection_frame = None
        self._active_detection_revision = None
        self._detection_requested = False
        self._detection_started = 0.0

        # Keep one decoder and one timer for the selected video.
        self.capture = None
        self.fps = 30.0
        self.current_frame = 0
        self.total_frames = 0
        self.at_end = False
        self._seeking = False
        self._resume_after_seek = False
        self.playback_timer = QTimer(self)
        self.playback_timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.playback_timer.setSingleShot(True)
        self.playback_timer.timeout.connect(self.read_next_frame)
        self.set_styles()
        
        # Initialize UI and Signals
        self.setup_ui()
        # Keep model execution on the same native thread for the app's lifetime.
        self.detection_thread = QThread(self)
        self.detection_worker = DetectionWorker()
        self.detection_worker.moveToThread(self.detection_thread)
        self.detection_thread.finished.connect(self.detection_worker.deleteLater)
        self.connect_signals()
        self.detection_thread.start()
        self.update_edit_controls()
        
        # Center Window on Screen
        screen = self.screen()
        if screen is not None:
            frame = self.frameGeometry()
            frame.moveCenter(screen.availableGeometry().center())
            self.move(frame.topLeft())
            
    def set_styles(self):
        # Load QSS Stylesheets
        style_dir = Path(__file__).resolve().parent / "styles"
        styles = "\n".join(
            (style_dir / name).read_text(encoding="utf-8-sig")
            for name in (
                "main.qss", 
                "app_title.qss", 
                "preview_canvas.qss", 
                "control_panel.qss",
                "settings_dialog.qss",
            )
        )

        # Resolve Asset Paths for Stylesheets
        assets = (style_dir.parent / "assets").as_posix()
        self.setStyleSheet(styles.replace("__ASSETS__", assets))

    def setup_ui(self):
        # Central Widget
        central = QWidget()
        central.setObjectName("appRoot")
        central.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.setCentralWidget(central)
        central.setFocus()

        # Main Layout
        layout = QVBoxLayout(central)
        layout.setContentsMargins(10, 0, 10, 10)
        layout.setSpacing(12)

        # Application Title
        self.app_title = AppTitle()
        layout.addWidget(self.app_title)

        # Content Layout
        content = QHBoxLayout()
        content.setSpacing(10)

        # Preview and Control Panel
        self.preview_canvas = PreviewCanvas()
        self.control_panel = ControlPanel()

        # Scrollable Control Panel
        self.controls_scroll = QScrollArea()
        self.controls_scroll.setObjectName("controlsScroll")
        self.controls_scroll.viewport().setObjectName("controlsViewport")
        self.controls_scroll.setWidgetResizable(True)
        self.controls_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.controls_scroll.setFixedWidth(292)
        self.controls_scroll.setWidget(self.control_panel)

        # Add Content Widgets
        content.addWidget(self.preview_canvas, 1)
        content.addWidget(self.controls_scroll)
        layout.addLayout(content, 1)
        
    def connect_signals(self):
        self.app_title.settings_btn.clicked.connect(self.open_settings)
        # Connect Upload Button to File Dialog
        self.control_panel.upload_btn.clicked.connect(self.browse_media)
        self.control_panel.clear_btn.clicked.connect(self.clear_media)
        self.preview_canvas.play_btn.clicked.connect(self.toggle_playback)
        self.preview_canvas.reset_btn.clicked.connect(self.reset_video)
        timeline = self.preview_canvas.timeline_slider
        timeline.sliderPressed.connect(self.begin_seek)
        timeline.sliderMoved.connect(self.preview_seek_time)
        timeline.sliderReleased.connect(self.finish_seek)
        timeline.valueChanged.connect(self.seek_from_slider)

        # Enhancement redraws the stored frame without advancing the decoder.
        panel = self.control_panel
        panel.enhance_checkbox.toggled.connect(self.on_enhancement_toggled)
        panel.brightness_slider.valueChanged.connect(self.on_brightness_changed)
        panel.original_btn.clicked.connect(self.refresh_preview)
        panel.enhanced_btn.clicked.connect(self.refresh_preview)

        panel.roi_btn.clicked.connect(self.begin_roi)
        panel.apply_roi_btn.clicked.connect(self.preview_canvas.apply_edit)
        panel.cancel_roi_btn.clicked.connect(self.preview_canvas.cancel_edit)
        panel.undo_btn.clicked.connect(self.preview_canvas.undo_edit_point)
        panel.redo_btn.clicked.connect(self.preview_canvas.redo_edit_point)
        panel.reset_roi_btn.clicked.connect(self.preview_canvas.clear_roi)
        panel.counting_line_btn.clicked.connect(self.begin_counting_line)
        panel.apply_line_btn.clicked.connect(self.preview_canvas.apply_edit)
        panel.cancel_line_btn.clicked.connect(self.preview_canvas.cancel_edit)
        panel.line_undo_btn.clicked.connect(self.preview_canvas.undo_edit_point)
        panel.line_redo_btn.clicked.connect(self.preview_canvas.redo_edit_point)
        panel.reset_line_btn.clicked.connect(self.preview_canvas.clear_counting_line)
        panel.mask_checkbox.toggled.connect(self.refresh_preview)
        self.preview_canvas.edit_changed.connect(self.on_edit_changed)
        panel.detect_btn.clicked.connect(self.run_detection)
        self.detection_worker.result_ready.connect(self.on_detection_result)
        self.detection_worker.failed.connect(self.on_detection_error)
        self.detection_worker.job_finished.connect(self.on_detection_finished)
        self.detect_frame_requested.connect(
            self.detection_worker.detect_frame, Qt.ConnectionType.QueuedConnection
        )

        # Window shortcuts still work after using a control outside the image.
        self.edit_shortcuts = []
        for key, handler in (("Return", self.preview_canvas.apply_edit),
                             ("Enter", self.preview_canvas.apply_edit),
                             ("Escape", self.preview_canvas.cancel_edit),
                             ("Ctrl+Z", self.preview_canvas.undo_edit_point),
                             ("Ctrl+Y", self.preview_canvas.redo_edit_point)):
            shortcut = QShortcut(QKeySequence(key), self)
            shortcut.activated.connect(handler)
            self.edit_shortcuts.append(shortcut)
        
    def browse_media(self):
        # Generate Supported Media File Filter
        formats = " ".join(f"*{ext}" for ext in SUPPORTED_FILE_FORMATS.keys())

        # Open Media File Dialog
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Image or Video",
            "",
            f"Supported Media ({formats})"
        )

        if not path:
            return

        self.load_media(path)

    def load_media(self, path):
        """Read an image or the first video frame before replacing the preview."""
        source = Path(path)
        extension = source.suffix.lower()
        capture = None
        fps = 30.0
        total_frames = 0

        try:
            if extension not in SUPPORTED_FILE_FORMATS:
                raise ValueError("Unsupported media format.")

            if extension in (".mp4", ".avi"):
                capture = cv2.VideoCapture(str(source))
                if not capture.isOpened():
                    raise ValueError("Could not open the video file.")
                ok, frame = capture.read()
                if not ok or frame is None:
                    raise ValueError("Could not read the first video frame.")
                # Some codecs do not provide usable FPS or frame-count metadata.
                reported_fps = capture.get(cv2.CAP_PROP_FPS)
                frame_count = capture.get(cv2.CAP_PROP_FRAME_COUNT)
                fps = reported_fps if isfinite(reported_fps) and reported_fps > 0 else 30.0
                total_frames = int(frame_count) if isfinite(frame_count) and frame_count > 0 else 0
            else:
                reader = QImageReader(str(source))
                reader.setAutoTransform(True)
                image = reader.read()
                if image.isNull():
                    raise ValueError(reader.errorString())
                frame = self.image_to_frame(image)

        except (ValueError, cv2.error) as error:
            if capture is not None:
                capture.release()
            QMessageBox.warning(self, "Unable to open media", str(error))
            return

        # Keep the previous file and preview intact until decoding succeeds.
        self.stop_current_video()
        self.invalidate_detection()
        self.raw_frame = None
        self.preview_canvas.clear_annotations()
        self.capture = capture
        self.fps = fps
        self.total_frames = total_frames
        self.display_frame(frame)
        self.control_panel.set_enhancement_available(True)
        self.control_panel.set_filename(source)
        self.media_path = source
        self.preview_canvas.set_video_mode(capture is not None)
        if capture is not None:
            self.preview_canvas.configure_timeline(self.total_frames, self.fps)
            self.update_playback_time()
        self.update_edit_controls()

    @staticmethod
    def image_to_frame(image):
        # QImageReader handles EXIF rotation before conversion to OpenCV's BGR.
        rgb = image.convertToFormat(QImage.Format.Format_RGB888)
        pixels = np.frombuffer(rgb.constBits().asstring(rgb.sizeInBytes()), dtype=np.uint8)
        # Ignore row padding, which is present for some image widths.
        rows = pixels.reshape(rgb.height(), rgb.bytesPerLine())
        rgb_pixels = rows[:, :rgb.width() * 3].reshape(rgb.height(), rgb.width(), 3)
        return cv2.cvtColor(rgb_pixels, cv2.COLOR_RGB2BGR)

    def open_settings(self):
        resume = self.is_playing
        self.pause_video()
        dialog = SettingsDialog(self.settings, self)
        if dialog.exec() == SettingsDialog.DialogCode.Accepted:
            self.apply_settings(dialog.values())
        if resume and not self._closing:
            self.toggle_playback()
        dialog.deleteLater()

    def apply_settings(self, settings):
        confidence_changed = settings.confidence != self.settings.confidence
        had_detection = self.preview_canvas.detections is not None or self._detection_busy
        self.settings = settings
        canvas = self.preview_canvas
        canvas.show_confidence = settings.show_confidence
        canvas.show_track_id = settings.show_track_id
        canvas.image_label.update()
        self.update_edit_controls()
        if confidence_changed:
            self.reset_tracking_session()
            self.invalidate_detection()
            self.request_updated_detection()
            # Refresh an already detected image, without starting video detection.
            if (self.capture is None and self.raw_frame is not None and had_detection
                    and canvas.edit_mode is None and not self._seeking):
                self.request_detection()

    def on_enhancement_toggled(self, enabled):
        self.reset_tracking_session()
        self.invalidate_detection()
        panel = self.control_panel
        button = panel.enhanced_btn if enabled else panel.original_btn
        button.setChecked(True)
        panel.set_enhancement_available(self.raw_frame is not None)
        self.refresh_preview()
        self.request_updated_detection()

    def on_brightness_changed(self):
        if self.control_panel.enhance_checkbox.isChecked():
            self.reset_tracking_session()
            self.invalidate_detection()
        self.refresh_preview()
        if self.control_panel.enhance_checkbox.isChecked():
            self.request_updated_detection()

    def reset_tracking_session(self):
        # The worker resets its tracker before processing this new session.
        self._tracking_session += 1
        self.preview_canvas.set_counting_summary(None)

    def invalidate_detection(self):
        # Ignore in-flight results after their source frame or settings change.
        self._detection_revision += 1
        self._detection_requested = False
        self.preview_canvas.set_detections(None)

    def run_detection(self):
        if self.continuous_detection:
            self.stop_detection()
            return
        canvas = self.preview_canvas
        if self.raw_frame is None or self._detection_busy or self._seeking or canvas.edit_mode is not None:
            return
        self.pause_video()
        if self.at_end and self.capture is not None and not self.reset_video():
            return
        self.reset_tracking_session()
        self.invalidate_detection()
        self.continuous_detection = self.capture is not None
        self.is_playing = self.continuous_detection
        self.preview_canvas.set_playing(self.is_playing)
        if self._next_detection_frame is None:
            self._next_detection_frame = (self.raw_frame, self.current_frame)
        self.request_detection()

    def stop_detection(self):
        self.pause_video()
        self._resume_after_seek = False
        self.continuous_detection = False
        self.invalidate_detection()
        # Preserve a decoded next frame for ordinary playback without seeking back.
        if (self._next_detection_frame is not None
                and self._next_detection_frame[1] <= self.current_frame):
            self._next_detection_frame = None
        self.update_edit_controls()

    def request_updated_detection(self):
        if self.continuous_detection and self.preview_canvas.edit_mode is None and not self._seeking:
            self.request_detection()

    def request_detection(self):
        self.playback_timer.stop()
        if self._next_detection_frame is None:
            self._next_detection_frame = (self.raw_frame, self.current_frame)
        # Resume must not submit the same in-flight frame twice.
        if (self._detection_busy and self._active_detection_revision == self._detection_revision
                and self._active_detection_frame is self._next_detection_frame):
            return
        self._detection_requested = True
        self.start_requested_detection()

    def start_requested_detection(self):
        canvas = self.preview_canvas
        if (not self._detection_requested or self._detection_busy or self._closing
                or self._seeking or canvas.edit_mode is not None):
            return
        self._active_detection_frame = self._next_detection_frame
        frame = self._active_detection_frame[0].copy()
        self._detection_started = perf_counter()
        panel = self.control_panel
        # Preview mode does not affect the pixels sent to the model.
        if panel.enhance_checkbox.isChecked():
            frame = brighten_frame(frame, panel.brightness_slider.value())
        if canvas.roi_points:
            frame = mask_outside_roi(frame, canvas.roi_points)
        self._active_detection_revision = self._detection_revision
        self._detection_busy = True
        self._detection_requested = False
        self.update_edit_controls()
        self.detect_frame_requested.emit(
            frame, self._active_detection_revision, self._tracking_session,
            self._active_detection_frame[1], self.capture is not None,
            tuple(self.preview_canvas.counting_line),
            self.settings.confidence,
        )

    def on_detection_result(self, revision, detections, counts):
        if revision == self._detection_revision and not self._closing:
            frame, index = self._active_detection_frame
            self.display_frame(frame, invalidate=False)
            # Reprocessing the final displayed frame must preserve EOF for Replay.
            self.at_end = self.at_end and index == self.current_frame
            self.current_frame = index
            if self.capture is not None:
                self.update_playback_time()
            self.preview_canvas.set_detections(detections)
            self.preview_canvas.set_counting_summary(counts)
            self._next_detection_frame = None

    def on_detection_error(self, revision, message):
        if revision == self._detection_revision and not self._closing:
            self.stop_detection()
            QMessageBox.warning(self, "Detection error", message)

    def on_detection_finished(self):
        self._detection_busy = False
        self._active_detection_frame = None
        self._active_detection_revision = None
        if self._closing:
            self.close()
        else:
            self.update_edit_controls()
            if self._detection_requested:
                self.start_requested_detection()
            elif self.continuous_detection and self.is_playing:
                # Subtract inference time instead of adding a full frame delay.
                elapsed_ms = (perf_counter() - self._detection_started) * 1000
                self.playback_timer.start(max(1, round(1000 / self.fps - elapsed_ms)))

    def refresh_preview(self):
        if self.raw_frame is not None:
            self.display_frame(self.raw_frame)

    def display_frame(self, frame, *, invalidate=True):
        if invalidate and frame is not self.raw_frame:
            self.invalidate_detection()
        # Always process the raw frame so repeated adjustments do not accumulate.
        panel = self.control_panel
        shown = frame
        mode = "Original"
        if panel.enhance_checkbox.isChecked() and panel.enhanced_btn.isChecked():
            shown = brighten_frame(frame, panel.brightness_slider.value())
            mode = "Enhanced"
        canvas = self.preview_canvas
        if canvas.edit_mode == "roi":
            # Show the full image while choosing a replacement polygon.
            mode += " · ROI editing"
        elif panel.mask_checkbox.isChecked() and canvas.roi_points:
            shown = mask_outside_roi(shown, canvas.roi_points)
            mode += " · Masked"
        if canvas.edit_mode == "line":
            mode += " · Line editing"
        image = self.frame_to_image(shown)
        self.raw_frame = frame
        self.preview_canvas.show_image(image)
        self.preview_canvas.set_preview_mode(mode)

    def begin_roi(self):
        if self.raw_frame is None or self._seeking or self.preview_canvas.edit_mode is not None:
            return
        self.pause_video()
        self.invalidate_detection()
        self.preview_canvas.begin_edit("roi")

    def begin_counting_line(self):
        if self.capture is None or self._seeking or self.preview_canvas.edit_mode is not None:
            return
        self.pause_video()
        self.preview_canvas.begin_edit("line")

    def on_edit_changed(self):
        roi = tuple(self.preview_canvas.roi_points)
        line = tuple(self.preview_canvas.counting_line)
        if roi != self._detection_roi or line != self._counting_line:
            self._detection_roi = roi
            self._counting_line = line
            self.reset_tracking_session()
            self.invalidate_detection()
        self.update_edit_controls()
        self.refresh_preview()
        self.preview_canvas.image_label.update()
        if self.preview_canvas.detections is None or self._next_detection_frame is not None:
            self.request_updated_detection()

    def update_edit_controls(self):
        canvas = self.preview_canvas
        editing = canvas.edit_mode is not None
        self.control_panel.set_detection_state(
            self.raw_frame is not None and not editing and not self._closing,
            self._detection_busy, self.continuous_detection,
        )
        # Keep the whole image available for placing points while editing.
        canvas.detection_overlay.setVisible(self.settings.show_overlay and not editing)
        self.control_panel.set_roi_controls(
            self.raw_frame is not None and canvas.edit_mode != "line",
            canvas.edit_mode == "roi", bool(canvas.draft_points),
            bool(canvas.roi_points), canvas.can_apply_edit(), bool(canvas.redo_points)
        )
        self.control_panel.set_line_controls(
            self.capture is not None and canvas.edit_mode != "roi",
            canvas.edit_mode == "line", bool(canvas.draft_points),
            bool(canvas.counting_line), canvas.can_apply_edit(), bool(canvas.redo_points)
        )
        for shortcut in self.edit_shortcuts:
            shortcut.setEnabled(editing)
        video_enabled = self.capture is not None and not editing
        canvas.play_btn.setEnabled(video_enabled)
        canvas.reset_btn.setEnabled(video_enabled)
        canvas.timeline_slider.setEnabled(video_enabled and self.total_frames > 1)

    @staticmethod
    def frame_to_image(frame):
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        height, width = rgb.shape[:2]
        # Own the pixels after the local NumPy frame goes out of scope.
        return QImage(
            rgb.data, width, height, rgb.strides[0], QImage.Format.Format_RGB888
        ).copy()

    def toggle_playback(self):
        if self.capture is None or self._seeking or self.preview_canvas.edit_mode is not None:
            return
        if self.is_playing:
            self.pause_video()
            return
        if self.at_end and not self.reset_video():
            return

        self.is_playing = True
        self.preview_canvas.set_playing(True)
        if self.continuous_detection:
            if self._next_detection_frame is not None or self.preview_canvas.detections is None:
                self.request_detection()
            else:
                self.playback_timer.start(max(1, round(1000 / self.fps)))
        else:
            self.invalidate_detection()
            self.playback_timer.start(max(1, round(1000 / self.fps)))

    def pause_video(self):
        # Keep the decoder position so Play resumes from the same frame.
        self.playback_timer.stop()
        self.is_playing = False
        self.preview_canvas.set_playing(False)

    def read_next_frame(self):
        if self.capture is None or not self.is_playing:
            return
        if self.continuous_detection and self._detection_busy:
            return
        try:
            if self._next_detection_frame is not None:
                frame, frame_index = self._next_detection_frame
                self._next_detection_frame = None
                ok = True
            else:
                ok, frame = self.capture.read()
                frame_index = self.current_frame + 1
            if not ok or frame is None:
                self.pause_video()
                self.at_end = True
                self.update_playback_time()
                return
            if self.continuous_detection:
                self._next_detection_frame = (frame, frame_index)
                self.request_detection()
                return
            self.display_frame(frame)
        except cv2.error as error:
            self.stop_detection()
            self.at_end = True
            QMessageBox.warning(self, "Video playback error", str(error))
            return

        self.current_frame = frame_index
        self.update_playback_time()
        self.playback_timer.start(max(1, round(1000 / self.fps)))

    def reset_video(self):
        # Reset rewinds the video without clearing ROI or overlay preferences.
        return self.seek_video(0)

    def seek_video(self, frame_index):
        if self.capture is None or self.preview_canvas.edit_mode is not None:
            return False
        self.pause_video()
        self.reset_tracking_session()
        if self.continuous_detection:
            self.invalidate_detection()
        frame_index = max(0, min(frame_index, self.total_frames - 1)) if self.total_frames else 0
        try:
            if not self.capture.set(cv2.CAP_PROP_POS_FRAMES, frame_index):
                raise ValueError("Could not seek to the selected video frame.")
            ok, frame = self.capture.read()
            if not ok or frame is None:
                raise ValueError("Could not read the selected video frame.")
            self._next_detection_frame = None
            self.display_frame(frame)
        except (ValueError, cv2.error) as error:
            # Restore the displayed position and remain paused if seeking fails.
            if self.continuous_detection:
                self.stop_detection()
            self.update_playback_time()
            self.at_end = True
            QMessageBox.warning(self, "Unable to seek video", str(error))
            return False

        self.current_frame = frame_index
        self.at_end = False
        self.update_playback_time()
        if self.continuous_detection:
            self.request_detection()
        return True

    def begin_seek(self):
        if self.capture is None or self.total_frames <= 0 or self.preview_canvas.edit_mode is not None:
            return
        self._resume_after_seek = self.is_playing
        self._seeking = True
        self.pause_video()
        if self.continuous_detection:
            self.invalidate_detection()

    def preview_seek_time(self, frame_index):
        if self._seeking:
            self.preview_canvas.set_playback_time(
                frame_index / self.fps, self.total_frames / self.fps
            )

    def finish_seek(self):
        if not self._seeking:
            return
        resume = self._resume_after_seek
        self._seeking = False
        self._resume_after_seek = False
        if self.seek_video(self.preview_canvas.timeline_slider.value()) and resume:
            self.toggle_playback()

    def seek_from_slider(self, frame_index):
        # Arrow keys and track clicks seek immediately; dragging seeks on release.
        if self._seeking or self.capture is None or self.total_frames <= 0:
            return
        resume = self.is_playing
        if self.seek_video(frame_index) and resume:
            self.toggle_playback()

    def update_playback_time(self):
        # Frame-based timestamps pause with the video instead of using wall time.
        elapsed = (self.current_frame + int(self.at_end)) / self.fps
        duration = self.total_frames / self.fps if self.total_frames else None
        if duration is not None:
            elapsed = min(elapsed, duration)
        self.preview_canvas.set_playback_time(elapsed, duration)
        self.preview_canvas.set_timeline_position(self.current_frame)

    def stop_current_video(self):
        self.pause_video()
        self.reset_tracking_session()
        self.continuous_detection = False
        self._detection_requested = False
        self._next_detection_frame = None
        if self.capture is not None:
            self.capture.release()
            self.capture = None
        self.current_frame = 0
        self.total_frames = 0
        self.at_end = False
        self.fps = 30.0
        self._seeking = False
        self._resume_after_seek = False
        self.preview_canvas.set_video_mode(False)

    def clear_media(self):
        self.stop_current_video()
        self.invalidate_detection()
        self.media_path = None
        self.raw_frame = None
        self.preview_canvas.clear_media()
        self.control_panel.reset_controls()
        self.controls_scroll.verticalScrollBar().setValue(0)
        self.centralWidget().setFocus()

    def closeEvent(self, event):
        self._closing = True
        self.invalidate_detection()
        self.stop_current_video()
        if self._detection_busy:
            # The last job calls close again when model execution has finished.
            self.hide()
            event.ignore()
            return
        # No model job is pending, so the idle event loop can stop safely.
        self.detection_thread.quit()
        self.detection_thread.wait()
        super().closeEvent(event)
