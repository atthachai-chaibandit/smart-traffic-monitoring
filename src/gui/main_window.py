
from pathlib import Path
from math import isfinite

import cv2

from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtGui import QImage, QImageReader
from PyQt6.QtWidgets import (
    QHBoxLayout, QMainWindow, 
    QScrollArea, QVBoxLayout, 
    QWidget, QFileDialog, QMessageBox
)

from .app_title import AppTitle
from .control_panel import ControlPanel
from .preview_canvas import PreviewCanvas
from .media_formats import SUPPORTED_FILE_FORMATS

class MainWindow(QMainWindow):
    """Local media selection and preview; detection is not connected yet."""

    def __init__(self):
        super().__init__()

        # Window Configuration
        self.setWindowTitle("Smart Traffic Monitoring")
        self.resize(980, 680)
        self.setMinimumSize(800, 580)
        self.media_path = None

        # Keep one decoder and one timer for the selected video.
        self.capture = None
        self.fps = 30.0
        self.current_frame = 0
        self.total_frames = 0
        self.at_end = False
        self.playback_timer = QTimer(self)
        self.playback_timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.playback_timer.timeout.connect(self.read_next_frame)
        self.set_styles()
        
        # Initialize UI and Signals
        self.setup_ui()
        self.connect_signals()
        
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
                "control_panel.qss"
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
        # Connect Upload Button to File Dialog
        self.control_panel.upload_btn.clicked.connect(self.browse_media)
        self.preview_canvas.play_btn.clicked.connect(self.toggle_playback)
        self.preview_canvas.reset_btn.clicked.connect(self.reset_video)
        
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
                image = self.frame_to_image(frame)

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

        except (ValueError, cv2.error) as error:
            if capture is not None:
                capture.release()
            QMessageBox.warning(self, "Unable to open media", str(error))
            return

        # Keep the previous file and preview intact until decoding succeeds.
        self.stop_current_video()
        self.capture = capture
        self.fps = fps
        self.total_frames = total_frames
        self.preview_canvas.show_image(image)
        self.control_panel.set_filename(source)
        self.media_path = source
        self.preview_canvas.set_video_mode(capture is not None)
        if capture is not None:
            self.update_playback_time()

    @staticmethod
    def frame_to_image(frame):
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        height, width = rgb.shape[:2]
        # Own the pixels after the local NumPy frame goes out of scope.
        return QImage(
            rgb.data, width, height, rgb.strides[0], QImage.Format.Format_RGB888
        ).copy()

    def toggle_playback(self):
        if self.capture is None:
            return
        if self.playback_timer.isActive():
            self.pause_video()
            return
        if self.at_end and not self.reset_video():
            return

        self.playback_timer.start(max(1, round(1000 / self.fps)))
        self.preview_canvas.set_playing(True)

    def pause_video(self):
        # Keep the decoder position so Play resumes from the same frame.
        self.playback_timer.stop()
        self.preview_canvas.set_playing(False)

    def read_next_frame(self):
        if self.capture is None:
            return
        try:
            ok, frame = self.capture.read()
            if not ok or frame is None:
                self.pause_video()
                self.at_end = True
                self.update_playback_time()
                return
            image = self.frame_to_image(frame)
        except cv2.error as error:
            self.pause_video()
            self.at_end = True
            QMessageBox.warning(self, "Video playback error", str(error))
            return

        self.current_frame += 1
        self.preview_canvas.show_image(image)
        self.update_playback_time()

    def reset_video(self):
        if self.capture is None:
            return False
        self.pause_video()
        try:
            if not self.capture.set(cv2.CAP_PROP_POS_FRAMES, 0):
                raise ValueError("Could not return to the first video frame.")
            ok, frame = self.capture.read()
            if not ok or frame is None:
                raise ValueError("Could not read the first video frame.")
            image = self.frame_to_image(frame)
        except (ValueError, cv2.error) as error:
            self.at_end = True
            QMessageBox.warning(self, "Unable to reset video", str(error))
            return False

        self.current_frame = 0
        self.at_end = False
        self.preview_canvas.show_image(image)
        self.update_playback_time()
        return True

    def update_playback_time(self):
        # Frame-based timestamps pause with the video instead of using wall time.
        elapsed = (self.current_frame + int(self.at_end)) / self.fps
        duration = self.total_frames / self.fps if self.total_frames else None
        if duration is not None:
            elapsed = min(elapsed, duration)
        self.preview_canvas.set_playback_time(elapsed, duration)

    def stop_current_video(self):
        self.pause_video()
        if self.capture is not None:
            self.capture.release()
            self.capture = None
        self.current_frame = 0
        self.total_frames = 0
        self.at_end = False
        self.preview_canvas.set_video_mode(False)

    def closeEvent(self, event):
        self.stop_current_video()
        super().closeEvent(event)
