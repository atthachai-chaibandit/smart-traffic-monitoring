
from PyQt6.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy
)
from PyQt6.QtCore import Qt

from .icons import get_pixmap, set_button_icon


class AppTitle(QWidget):
    def __init__(self):
        super().__init__()

        self.setObjectName("appHeader")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedHeight(54)

        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed
        )

        self.setup_ui()

    def setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 1)
        layout.setSpacing(10)

        # App Icon
        self.app_icon = QLabel()
        self.app_icon.setPixmap(
            get_pixmap("car", "#A78BFA", 22, self.devicePixelRatioF())
        )
        self.app_icon.setFixedSize(22, 22)

        # App Title
        self.app_title = QLabel(
            "SMART TRAFFIC MONITORING"
        )
        self.app_title.setObjectName("appTitle")

        # Media Status
        self.media_status = QLabel("No media loaded")
        self.media_status.setObjectName("mediaStatus")
        self.media_status.setFixedHeight(26)
        self.media_status.setAlignment(
            Qt.AlignmentFlag.AlignCenter
        )

        # Settings Button
        self.settings_btn = QPushButton()
        self.settings_btn.setObjectName("settingsButton")
        self.settings_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.settings_btn.setFixedSize(32, 32)
        self.settings_btn.setToolTip("Settings")
        self.settings_btn.setAccessibleName("Settings")
        self.settings_btn.setCursor(
            Qt.CursorShape.PointingHandCursor
        )

        set_button_icon(
            self.settings_btn,
            "adjustments-horizontal",
            "#9CA3AF",
            24
        )

        # Add Widgets
        layout.addWidget(self.app_icon)
        layout.addWidget(self.app_title)
        layout.addStretch()
        layout.addWidget(self.media_status)
        layout.addWidget(self.settings_btn)

    def set_media_status(self, filename):
        self.media_status.setText(
            filename if filename else "No media loaded"
        )
        self.media_status.setToolTip(filename or "No media loaded")
