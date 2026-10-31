from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from .icons import get_pixmap, set_button_icon


class PreviewCanvas(QWidget):
    def __init__(self):
        super().__init__()
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        title_row = QHBoxLayout()
        heading = QLabel("Preview Workspace")
        heading.setObjectName("sectionHeading")
        title_row.addWidget(heading)
        title_row.addStretch()
        mode = QLabel("Original / Enhanced / Masked")
        mode.setObjectName("mutedText")
        title_row.addWidget(mode)
        layout.addLayout(title_row)

        self.preview = QFrame()
        self.preview.setObjectName("previewArea")
        self.preview.setMinimumSize(400, 240)
        empty = QVBoxLayout(self.preview)
        empty.setContentsMargins(16, 16, 16, 16)
        empty.setSpacing(8)
        empty.addStretch()
        icon = QLabel()
        icon.setPixmap(get_pixmap("photo-plus", "#A78BFA", 34, self.devicePixelRatioF()))
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty.addWidget(icon)
        title = QLabel("Upload Image or Video")
        title.setObjectName("emptyTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty.addWidget(title)
        hint = QLabel("Choose a file to start processing")
        hint.setObjectName("mutedText")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty.addWidget(hint)
        empty.addStretch()
        layout.addWidget(self.preview, 1)

        self.playback = QFrame()
        self.playback.setObjectName("playbackBar")
        self.playback.setFixedHeight(44)
        playback = QHBoxLayout(self.playback)
        playback.setContentsMargins(10, 0, 10, 0)
        playback.setSpacing(10)
        self.play_btn = self.icon_button("player-play", "Play video", "#A78BFA")
        self.play_btn.setObjectName("playButton")
        self.time_label = QLabel("00:00 / 00:00")
        self.time_label.setObjectName("mutedText")
        self.reset_btn = self.icon_button("refresh", "Reset preview")
        self.fullscreen_btn = self.icon_button("maximize", "Fullscreen preview")
        playback.addWidget(self.play_btn)
        playback.addWidget(self.time_label)
        playback.addStretch()
        playback.addWidget(self.reset_btn)
        playback.addWidget(self.fullscreen_btn)
        layout.addWidget(self.playback)

        stats = QHBoxLayout()
        stats.setSpacing(8)
        self.total_label = self.create_stat("Total Vehicles")
        self.cars_label = self.create_stat("Cars")
        self.other_label = self.create_stat("Other Vehicles")
        for card in (self.total_label, self.cars_label, self.other_label):
            stats.addWidget(card, 1)
        layout.addLayout(stats)

    @staticmethod
    def icon_button(icon, label, color="#9CA3AF"):
        button = QPushButton()
        button.setObjectName("iconButton")
        button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        button.setFixedSize(28, 28)
        button.setToolTip(label)
        button.setAccessibleName(label)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        set_button_icon(button, icon, color, 20)
        return button

    @staticmethod
    def create_stat(title):
        card = QFrame()
        card.setObjectName("statCard")
        card.setFixedHeight(68)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 9, 12, 8)
        layout.setSpacing(4)
        name = QLabel(title)
        name.setObjectName("mutedText")
        layout.addWidget(name)
        value = QLabel("\u2014")
        value.setObjectName("statValue")
        layout.addWidget(value)
        return card
