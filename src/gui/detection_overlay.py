
from PyQt6.QtCore import QEvent, QPoint, Qt
from PyQt6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from .icons import get_pixmap


class DetectionOverlay(QFrame):
    """Presentation-only breakdown, movable by its header within the preview."""

    MARGIN = 12

    def __init__(self, parent):
        super().__init__(parent)

        # Overlay Configuration
        self.setObjectName("detectionOverlay")
        self.setFixedSize(240, 180)
        self._drag_offset = None

        # Main Layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(6)

        # Draggable Header
        self.drag_header = QWidget()
        self.drag_header.setFixedHeight(22)
        self.drag_header.setCursor(Qt.CursorShape.OpenHandCursor)
        self.drag_header.setToolTip("Drag to move within the preview")

        header = QHBoxLayout(self.drag_header)
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(6)

        # Drag Handle Icon
        grip = QLabel()
        grip.setFixedSize(16, 16)
        grip.setPixmap(get_pixmap("grip-vertical", "#9CA3AF", 16, self.devicePixelRatioF()))

        # Overlay Title
        title = QLabel("Vehicle Detections")
        title.setObjectName("overlayTitle")

        # Let the parent header handle mouse events instead of its child labels.
        for child in (grip, title):
            child.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            header.addWidget(child)

        header.addStretch()
        layout.addWidget(self.drag_header)

        # Detection Caption
        caption = QLabel("Detected in current frame")
        caption.setObjectName("overlayCaption")
        layout.addWidget(caption)

        # Section Separator
        separator = QFrame()
        separator.setObjectName("separator")
        separator.setFixedHeight(1)
        layout.addWidget(separator)

        # Detection Grid Layout
        rows = QGridLayout()
        rows.setHorizontalSpacing(8)
        rows.setVerticalSpacing(0)
        rows.setColumnStretch(1, 1)

        # Vehicle Detection Rows
        self.values = {}
        for row, (name, icon_name) in enumerate((
            ("Car", "car"), ("Motorcycle", "motorbike"),
            ("Bus", "bus"), ("Truck", "truck"),
        )):
            # Vehicle Icon
            icon = QLabel()
            icon.setFixedSize(18, 18)
            icon.setPixmap(
                get_pixmap(icon_name, "#A78BFA", 18, self.devicePixelRatioF())
            )

            # Detection Count
            value = QLabel("\u2014")
            value.setObjectName("overlayValue")
            value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            value.setAccessibleName(f"{name} detected in current frame")

            # Store Detection Value Labels
            self.values[name.lower()] = value

            # Add Detection Row
            rows.addWidget(icon, row, 0)
            rows.addWidget(QLabel(name), row, 1)
            rows.addWidget(value, row, 2)
            rows.setRowMinimumHeight(row, 24)

        layout.addLayout(rows)

        # Initial Overlay Position
        self.move(self.MARGIN, self.MARGIN)

        # Monitor Header Mouse Events and Preview Resize Events
        self.drag_header.installEventFilter(self)
        parent.installEventFilter(self)

    def keep_inside_preview(self):
        # Calculate Overlay Movement Boundaries
        parent = self.parentWidget()
        right = max(self.MARGIN, parent.width() - self.width() - self.MARGIN)
        bottom = max(self.MARGIN, parent.height() - self.height() - self.MARGIN)

        # Keep Overlay Within Preview Bounds
        self.move(
            min(max(self.MARGIN, self.x()), right),
            min(max(self.MARGIN, self.y()), bottom),
        )

    def eventFilter(self, watched, event):
        # Reposition Overlay When Preview Resizes
        if watched is self.parentWidget() and event.type() == QEvent.Type.Resize:
            self.keep_inside_preview()

        # Handle Header Drag Events
        elif watched is self.drag_header:

            # Start Dragging on Left Mouse Press
            if (event.type() == QEvent.Type.MouseButtonPress
                    and event.button() == Qt.MouseButton.LeftButton):
                self._drag_offset = event.globalPosition().toPoint() - self.mapToGlobal(QPoint())
                self.drag_header.setCursor(Qt.CursorShape.ClosedHandCursor)
                self.raise_()
                return True

            # Move Overlay While Dragging
            if event.type() == QEvent.Type.MouseMove and self._drag_offset is not None:
                point = self.parentWidget().mapFromGlobal(event.globalPosition().toPoint())
                self.move(point - self._drag_offset)
                self.keep_inside_preview()
                return True

            # Stop Dragging on Left Mouse Release
            if (event.type() == QEvent.Type.MouseButtonRelease
                    and event.button() == Qt.MouseButton.LeftButton):
                self._drag_offset = None
                self.drag_header.setCursor(Qt.CursorShape.OpenHandCursor)
                return True

        return super().eventFilter(watched, event)
