from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QHBoxLayout, QMainWindow, QScrollArea, QVBoxLayout, QWidget

from .app_title import AppTitle
from .control_panel import ControlPanel
from .preview_canvas import PreviewCanvas


class MainWindow(QMainWindow):
    """Presentation-only shell, without media or processing handlers."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Smart Traffic Monitoring")
        self.resize(980, 680)
        self.setMinimumSize(800, 580)
        style_dir = Path(__file__).resolve().parent / "styles"
        styles = "\n".join(
            (style_dir / name).read_text(encoding="utf-8")
            for name in ("main.qss", "app_title.qss", "preview_canvas.qss", "control_panel.qss")
        )
        assets = (style_dir.parent / "assets").as_posix()
        self.setStyleSheet(styles.replace("__ASSETS__", assets))
        self.setup_ui()
        screen = self.screen()
        if screen is not None:
            frame = self.frameGeometry()
            frame.moveCenter(screen.availableGeometry().center())
            self.move(frame.topLeft())

    def setup_ui(self):
        central = QWidget()
        central.setObjectName("appRoot")
        central.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.setCentralWidget(central)
        central.setFocus()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(10, 0, 10, 10)
        layout.setSpacing(12)
        self.app_title = AppTitle()
        layout.addWidget(self.app_title)
        content = QHBoxLayout()
        content.setSpacing(10)
        self.preview_canvas = PreviewCanvas()
        self.control_panel = ControlPanel()
        self.controls_scroll = QScrollArea()
        self.controls_scroll.setObjectName("controlsScroll")
        self.controls_scroll.viewport().setObjectName("controlsViewport")
        self.controls_scroll.setWidgetResizable(True)
        self.controls_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.controls_scroll.setFixedWidth(292)
        self.controls_scroll.setWidget(self.control_panel)
        content.addWidget(self.preview_canvas, 1)
        content.addWidget(self.controls_scroll)
        layout.addLayout(content, 1)
