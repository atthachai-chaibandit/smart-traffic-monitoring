
from pathlib import Path

import cv2

from PyQt6.QtCore import Qt
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

        try:
            if extension not in SUPPORTED_FILE_FORMATS:
                raise ValueError("Unsupported media format.")

            if extension in (".mp4", ".avi"):
                capture = cv2.VideoCapture(str(source))
                try:
                    if not capture.isOpened():
                        raise ValueError("Could not open the video file.")
                    ok, frame = capture.read()
                    if not ok or frame is None:
                        raise ValueError("Could not read the first video frame.")

                    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    height, width = rgb.shape[:2]
                    # Copy the pixels so QImage does not depend on the local NumPy buffer.
                    image = QImage(
                        rgb.data, width, height, rgb.strides[0],
                        QImage.Format.Format_RGB888,
                    ).copy()
                finally:
                    capture.release()
            else:
                reader = QImageReader(str(source))
                reader.setAutoTransform(True)
                image = reader.read()
                if image.isNull():
                    raise ValueError(reader.errorString())

        except (ValueError, cv2.error) as error:
            QMessageBox.warning(self, "Unable to open media", str(error))
            return

        # Keep the previous file and preview intact until decoding succeeds.
        self.preview_canvas.show_image(image)
        self.control_panel.set_filename(source)
        self.media_path = source
