
from PyQt6.QtCore import QEvent, Qt
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from .icons import get_pixmap, set_button_icon
from .detection_overlay import DetectionOverlay
from .media_formats import SUPPORTED_FILE_FORMATS

class PreviewCanvas(QWidget):
    def __init__(self):
        super().__init__()
        self.original_pixmap = QPixmap()
        self.setup_ui()

    def setup_ui(self):
        # Main Layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # Preview Header
        title_row = QHBoxLayout()

        heading = QLabel("Preview Workspace")
        heading.setObjectName("sectionHeading")
        title_row.addWidget(heading)
        title_row.addStretch()

        # Preview Mode Label
        mode = QLabel("Original / Enhanced / Masked")
        mode.setObjectName("mutedText")
        title_row.addWidget(mode)
        layout.addLayout(title_row)

        # Preview Area
        self.preview = QFrame()
        self.preview.setObjectName("previewArea")
        self.preview.setMinimumSize(400, 240)

        # Group the placeholder so it can be hidden when media is loaded.
        preview_layout = QVBoxLayout(self.preview)
        preview_layout.setContentsMargins(16, 16, 16, 16)
        self.empty_state = QWidget()
        empty = QVBoxLayout(self.empty_state)
        empty.setContentsMargins(0, 0, 0, 0)
        empty.setSpacing(8)
        empty.addStretch()

        # Upload Placeholder Icon
        icon = QLabel()
        icon.setPixmap(
            get_pixmap("photo-plus", "#A78BFA", 34, self.devicePixelRatioF())
        )
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty.addWidget(icon)

        # Upload Placeholder Title
        title = QLabel("Upload Image or Video")
        title.setObjectName("emptyTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty.addWidget(title)

        # Upload Placeholder Hint
        formats = ", ".join(SUPPORTED_FILE_FORMATS.values())
        hint = QLabel(f"Choose a file to start processing ({formats})")
        hint.setObjectName("mutedText")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setWordWrap(True)
        empty.addWidget(hint)

        empty.addStretch()
        preview_layout.addWidget(self.empty_state)
        layout.addWidget(self.preview, 1)

        # A child label avoids letting the source image's size affect the layout.
        self.image_label = QLabel(self.preview)
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.hide()

        # Detection Overlay
        self.detection_overlay = DetectionOverlay(self.preview)
        self.detection_overlay.raise_()

        # Monitor Preview Resize Events
        self.preview.installEventFilter(self)

        # Playback Controls
        self.playback = QFrame()
        self.playback.setObjectName("playbackBar")
        self.playback.setFixedHeight(44)

        playback = QHBoxLayout(self.playback)
        playback.setContentsMargins(10, 0, 10, 0)
        playback.setSpacing(10)

        # Play Button
        self.play_btn = self.icon_button("player-play", "Play video", "#A78BFA")
        self.play_btn.setObjectName("playButton")

        # Playback Time Label
        self.time_label = QLabel("00:00 / 00:00")
        self.time_label.setObjectName("mutedText")

        # Reset and Fullscreen Buttons
        self.reset_btn = self.icon_button("refresh", "Reset preview")
        self.fullscreen_btn = self.icon_button("maximize", "Fullscreen preview")

        # Add Playback Widgets
        playback.addWidget(self.play_btn)
        playback.addWidget(self.time_label)
        playback.addStretch()
        playback.addWidget(self.reset_btn)
        playback.addWidget(self.fullscreen_btn)
        layout.addWidget(self.playback)

        # Vehicle Counting Summary
        self.counting_summary = QWidget()
        self.counting_summary.setFixedHeight(68)

        stats = QHBoxLayout(self.counting_summary)
        stats.setContentsMargins(0, 0, 0, 0)
        stats.setSpacing(8)

        # Counting Statistic Cards
        self.total_card = self.create_stat("Total Counted", "car", "#A78BFA")
        self.in_card = self.create_stat("IN", "arrow-down-right", "#34D399")
        self.out_card = self.create_stat("OUT", "arrow-up-right", "#FBBF24")

        # Add Statistic Cards
        for card in (self.total_card, self.in_card, self.out_card):
            stats.addWidget(card, 1)

        self.counting_summary.setToolTip("Cumulative vehicle crossings at the counting line")
        layout.addWidget(self.counting_summary)

    def show_image(self, image):
        self.original_pixmap = QPixmap.fromImage(image)
        self.empty_state.hide()
        self.image_label.show()
        self.update_preview()
        self.detection_overlay.raise_()

    def update_preview(self):
        if self.original_pixmap.isNull():
            return

        self.image_label.setGeometry(self.preview.contentsRect().adjusted(8, 8, -8, -8))
        if self.image_label.size().isEmpty():
            return

        # Scale from the original pixels each time, including the display's DPR.
        dpr = self.devicePixelRatioF()
        pixmap = self.original_pixmap.scaled(
            self.image_label.size() * dpr,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        pixmap.setDevicePixelRatio(dpr)
        self.image_label.setPixmap(pixmap)

    def eventFilter(self, watched, event):
        # Adjust Empty State Spacing When Preview Resizes
        if watched is self.preview and event.type() == QEvent.Type.Resize:
            if self.original_pixmap.isNull():
                overlay = self.detection_overlay

                # Keep the empty-state message below the overlay on narrow previews.
                narrow = self.preview.width() < 2 * (overlay.width() + overlay.MARGIN) + 34
                top = overlay.height() + 2 * overlay.MARGIN if narrow else 16
                self.preview.layout().setContentsMargins(16, top, 16, 16)
            else:
                self.update_preview()

        return super().eventFilter(watched, event)

    @staticmethod
    def icon_button(icon, label, color="#9CA3AF"):
        # Create Icon Button
        button = QPushButton()
        button.setObjectName("iconButton")
        button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        button.setFixedSize(28, 28)

        # Button Accessibility and Interaction
        button.setToolTip(label)
        button.setAccessibleName(label)
        button.setCursor(Qt.CursorShape.PointingHandCursor)

        # Button Icon
        set_button_icon(button, icon, color, 20)
        return button

    def create_stat(self, title, icon_name, color):
        # Create Statistic Card
        card = QFrame()
        card.setObjectName("statCard")
        card.setFixedHeight(68)

        # Card Layout
        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 9, 12, 8)
        layout.setSpacing(4)

        # Statistic Label
        name = QLabel(title)
        name.setObjectName("mutedText")

        # Card Header
        heading = QHBoxLayout()
        heading.setSpacing(8)
        heading.addWidget(name)
        heading.addStretch()

        # Statistic Icon
        icon = QLabel()
        icon.setFixedSize(16, 16)
        icon.setPixmap(
            get_pixmap(icon_name, color, 16, self.devicePixelRatioF())
        )
        heading.addWidget(icon)
        layout.addLayout(heading)

        # Statistic Value
        value = QLabel("\u2014")
        value.setObjectName("statValue")
        layout.addWidget(value)

        return card
