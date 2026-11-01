
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QHBoxLayout, QMainWindow, 
    QScrollArea, QVBoxLayout, 
    QWidget, QFileDialog
)

from .app_title import AppTitle
from .control_panel import ControlPanel
from .preview_canvas import PreviewCanvas
from .media_formats import SUPPORTED_FILE_FORMATS

class MainWindow(QMainWindow):
    """Presentation-only shell, without media or processing handlers."""

    def __init__(self):
        super().__init__()

        # Window Configuration
        self.setWindowTitle("Smart Traffic Monitoring")
        self.resize(980, 680)
        self.setMinimumSize(800, 580)
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