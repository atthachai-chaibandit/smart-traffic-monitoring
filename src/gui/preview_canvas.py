
from PyQt6.QtCore import QEvent, QSignalBlocker, Qt
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QSlider, QVBoxLayout, QWidget

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
        self.mode_label = QLabel("")
        self.mode_label.setObjectName("mutedText")
        title_row.addWidget(self.mode_label)
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

        # Use frame indices so arrow keys can move one frame at a time.
        self.timeline_slider = QSlider(Qt.Orientation.Horizontal)
        self.timeline_slider.setObjectName("timelineSlider")
        self.timeline_slider.setAccessibleName("Video timeline")
        self.timeline_slider.setSingleStep(1)

        # Reset and Fullscreen Buttons
        self.reset_btn = self.icon_button("refresh", "Reset video")
        self.fullscreen_btn = self.icon_button("maximize", "Fullscreen preview")

        # Add Playback Widgets
        playback.addWidget(self.play_btn)
        playback.addWidget(self.time_label)
        playback.addWidget(self.timeline_slider, 1)
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
        self.set_video_mode(False)

    def set_video_mode(self, enabled):
        self.play_btn.setEnabled(enabled)
        self.reset_btn.setEnabled(enabled)
        self.set_playing(False)
        self.time_label.setText("00:00 / --:--" if enabled else "\u2014 / \u2014")
        with QSignalBlocker(self.timeline_slider):
            self.timeline_slider.setSliderDown(False)
            self.timeline_slider.setRange(0, 0)
            self.timeline_slider.setValue(0)
            self.timeline_slider.setEnabled(False)

    def configure_timeline(self, total_frames, fps):
        with QSignalBlocker(self.timeline_slider):
            self.timeline_slider.setRange(0, max(0, total_frames - 1))
            self.timeline_slider.setPageStep(max(1, round(fps)))
            self.timeline_slider.setEnabled(total_frames > 1)

    def set_timeline_position(self, frame_index):
        # Playback updates must not trigger another seek through valueChanged.
        with QSignalBlocker(self.timeline_slider):
            self.timeline_slider.setValue(frame_index)

    def set_playing(self, playing):
        icon = "player-pause" if playing else "player-play"
        label = "Pause video" if playing else "Play video"
        set_button_icon(self.play_btn, icon, "#A78BFA", 20)
        self.play_btn.setToolTip(label)
        self.play_btn.setAccessibleName(label)

    @staticmethod
    def format_time(seconds):
        if seconds is None:
            return "--:--"
        minutes, seconds = divmod(max(0, int(seconds)), 60)
        return f"{minutes:02d}:{seconds:02d}"

    def set_playback_time(self, elapsed, duration):
        self.time_label.setText(
            f"{self.format_time(elapsed)} / {self.format_time(duration)}"
        )

    def show_image(self, image):
        self.original_pixmap = QPixmap.fromImage(image)
        self.empty_state.hide()
        self.image_label.show()
        self.update_preview()
        self.detection_overlay.raise_()

    def set_preview_mode(self, mode):
        self.mode_label.setText(mode)

    def clear_media(self):
        self.set_preview_mode("")
        self.original_pixmap = QPixmap()
        self.image_label.clear()
        self.image_label.hide()
        self.empty_state.show()
        self.set_video_mode(False)
        self.detection_overlay.reset_state()
        for card in (self.total_card, self.in_card, self.out_card):
            card.findChild(QLabel, "statValue").setText("\u2014")
        self.update_empty_spacing()

    def update_empty_spacing(self):
        overlay = self.detection_overlay
        narrow = self.preview.width() < 2 * (overlay.width() + overlay.MARGIN) + 34
        top = overlay.height() + 2 * overlay.MARGIN if narrow else 16
        self.preview.layout().setContentsMargins(16, top, 16, 16)

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
                # Keep the empty-state message below the overlay on narrow previews.
                self.update_empty_spacing()
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
