
from PyQt6.QtCore import QEvent, QPointF, QRectF, QSignalBlocker, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPen, QPixmap, QPolygonF
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QSlider, QVBoxLayout, QWidget

from .icons import get_pixmap, set_button_icon
from .detection_overlay import DetectionOverlay
from .media_formats import SUPPORTED_FILE_FORMATS
from ..detector import VEHICLE_COLORS


class PreviewImageLabel(QLabel):
    """Draw annotations over the image without changing its pixels."""

    def __init__(self, canvas):
        super().__init__(canvas.preview)
        self.canvas = canvas

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        self.canvas.paint_detections(painter)
        self.canvas.paint_roi(painter)
        self.canvas.paint_counting_line(painter)
        painter.end()


class PreviewCanvas(QWidget):
    edit_changed = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.original_pixmap = QPixmap()
        self.detections = None
        self.show_confidence = True
        self.show_track_id = True
        # Store confirmed and draft points in source-image pixels, not widget pixels.
        self.roi_points = []
        self.counting_line = []
        self.draft_points = []
        self.redo_points = []
        self.edit_mode = None
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
        self.image_label = PreviewImageLabel(self)
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.image_label.installEventFilter(self)
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
        self.set_detections(None)
        self.clear_annotations()
        self.set_preview_mode("")
        self.original_pixmap = QPixmap()
        self.image_label.clear()
        self.image_label.hide()
        self.empty_state.show()
        self.set_video_mode(False)
        self.detection_overlay.reset_state()
        self.set_counting_summary(None)
        self.update_empty_spacing()

    def set_counting_summary(self, counts):
        if counts is None:
            values = ("\u2014", "\u2014", "\u2014")
        else:
            incoming = sum(counts["in"].values())
            outgoing = sum(counts["out"].values())
            values = (incoming + outgoing, incoming, outgoing)
        for card, value in zip((self.total_card, self.in_card, self.out_card), values):
            card.findChild(QLabel, "statValue").setText(str(value))

    def begin_edit(self, mode):
        if self.original_pixmap.isNull() or self.edit_mode is not None:
            return
        # Keep confirmed geometry until the replacement is accepted.
        self.draft_points = []
        self.redo_points = []
        self.edit_mode = mode
        self.image_label.setCursor(Qt.CursorShape.CrossCursor)
        self.image_label.setFocus()
        self.edit_changed.emit()

    def can_apply_edit(self):
        if self.edit_mode == "line":
            return len(self.draft_points) == 2 and self.draft_points[0] != self.draft_points[1]
        if self.edit_mode != "roi" or len(self.draft_points) < 3:
            return False
        # Reject points that form a line instead of an area.
        points = self.draft_points
        area_twice = sum(
            x * points[(i + 1) % len(points)][1]
            - y * points[(i + 1) % len(points)][0]
            for i, (x, y) in enumerate(points)
        )
        return area_twice != 0

    def apply_edit(self):
        if not self.can_apply_edit():
            return False
        if self.edit_mode == "roi":
            self.roi_points = list(self.draft_points)
        else:
            self.counting_line = list(self.draft_points)
        self.cancel_edit()
        return True

    def cancel_edit(self):
        self.draft_points = []
        self.redo_points = []
        self.edit_mode = None
        self.image_label.unsetCursor()
        self.edit_changed.emit()

    def undo_edit_point(self):
        if self.edit_mode is not None and self.draft_points:
            self.redo_points.append(self.draft_points.pop())
            self.edit_changed.emit()

    def redo_edit_point(self):
        if self.edit_mode is not None and self.redo_points:
            self.draft_points.append(self.redo_points.pop())
            self.edit_changed.emit()

    def clear_roi(self):
        self.roi_points = []
        self.edit_changed.emit()

    def clear_counting_line(self):
        self.counting_line = []
        self.edit_changed.emit()

    def clear_annotations(self):
        self.roi_points = []
        self.counting_line = []
        self.cancel_edit()

    def image_rect(self):
        """Return the actual image bounds inside the centered label, in logical pixels."""
        pixmap = self.image_label.pixmap()
        if pixmap is None or pixmap.isNull():
            return QRectF()
        size = pixmap.deviceIndependentSize()
        bounds = self.image_label.contentsRect()
        return QRectF(
            bounds.x() + int((bounds.width() - size.width()) / 2),
            bounds.y() + int((bounds.height() - size.height()) / 2),
            size.width(), size.height(),
        )

    def preview_to_image(self, position):
        rect = self.image_rect()
        if rect.isEmpty() or not rect.contains(position):
            return None
        width, height = self.original_pixmap.width(), self.original_pixmap.height()
        x = round((position.x() - rect.x()) * width / rect.width())
        y = round((position.y() - rect.y()) * height / rect.height())
        return (max(0, min(x, width - 1)), max(0, min(y, height - 1)))

    def image_to_preview(self, point):
        rect = self.image_rect()
        return QPointF(
            rect.x() + point[0] * rect.width() / self.original_pixmap.width(),
            rect.y() + point[1] * rect.height() / self.original_pixmap.height(),
        )

    def paint_roi(self, painter):
        if self.original_pixmap.isNull():
            return
        points = self.draft_points if self.edit_mode == "roi" else self.roi_points
        if not points:
            return
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setClipRect(self.image_rect())
        painter.setPen(QPen(QColor("#A78BFA"), 2))
        polygon = QPolygonF([self.image_to_preview(point) for point in points])
        if self.edit_mode == "roi":
            painter.drawPolyline(polygon)
            painter.setBrush(QColor("#A78BFA"))
            for point in polygon:
                painter.drawEllipse(point, 3, 3)
        else:
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPolygon(polygon)

    def set_detections(self, detections):
        self.detections = detections
        self.detection_overlay.set_detections(detections)
        self.image_label.update()

    def detection_label(self, detection):
        text = detection["class_name"]
        if self.show_confidence:
            text += f' {detection["confidence"]:.2f}'
        if self.show_track_id and detection.get("track_id") is not None:
            text = f'ID {detection["track_id"]} · {text}'
        return text

    def paint_detections(self, painter):
        if not self.detections or self.edit_mode is not None or self.original_pixmap.isNull():
            return
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setClipRect(self.image_rect())
        painter.setBrush(Qt.BrushStyle.NoBrush)
        metrics = painter.fontMetrics()
        for detection in self.detections:
            x1, y1, x2, y2 = detection["box"]
            start = self.image_to_preview((x1, y1))
            end = self.image_to_preview((x2, y2))
            painter.setPen(QPen(QColor(VEHICLE_COLORS[detection["class_name"]]), 2))
            painter.drawRect(QRectF(start, end).normalized())
            text = self.detection_label(detection)
            rect = self.image_rect()
            left = max(rect.left(), min(start.x(), rect.right() - metrics.horizontalAdvance(text)))
            baseline = max(rect.top() + metrics.ascent(), start.y() - 4)
            painter.drawText(QPointF(left, baseline), text)

    def paint_counting_line(self, painter):
        if self.original_pixmap.isNull():
            return
        points = self.draft_points if self.edit_mode == "line" else self.counting_line
        if not points:
            return
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setClipRect(self.image_rect())
        painter.setPen(QPen(QColor("#FF4D4F"), 2))
        if len(points) == 2:
            start = self.image_to_preview(points[0])
            end = self.image_to_preview(points[1])
            painter.drawLine(start, end)
            if self.edit_mode != "line":
                # Show the two crossing directions in preview pixels, independent of zoom.
                dx, dy = end.x() - start.x(), end.y() - start.y()
                length = (dx * dx + dy * dy) ** 0.5
                if length:
                    middle = (start + end) / 2
                    normal = QPointF(-dy / length, dx / length)
                    tangent = QPointF(dx / length, dy / length)
                    for sign, label, color in ((1, "IN", "#34D399"), (-1, "OUT", "#FBBF24")):
                        tip = middle + normal * (24 * sign)
                        base = tip - normal * (6 * sign)
                        painter.setPen(QPen(QColor(color), 2))
                        painter.drawLine(middle, tip)
                        painter.drawLine(tip, base + tangent * 4)
                        painter.drawLine(tip, base - tangent * 4)
                        painter.drawText(tip + QPointF(7, 4), label)
        if self.edit_mode == "line":
            painter.setBrush(QColor("#FF4D4F"))
            for point in points:
                painter.drawEllipse(self.image_to_preview(point), 3, 3)

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
        if watched is self.image_label and self.edit_mode is not None:
            if event.type() == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
                point = self.preview_to_image(event.position())
                if self.edit_mode == "line" and len(self.draft_points) >= 2:
                    return True
                if point is not None and point not in self.draft_points:
                    self.draft_points.append(point)
                    # A new point starts a different history after Undo.
                    self.redo_points.clear()
                    self.edit_changed.emit()
                return True
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
