
from PyQt6.QtCore import QEvent, QPoint, Qt
from PyQt6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton,
    QSlider, QVBoxLayout, QWidget,
)

from .icons import get_pixmap, set_button_icon


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

        # The button handles its own clicks instead of starting a header drag.
        self.settings_btn = QPushButton()
        self.settings_btn.setObjectName("overlaySettingsButton")
        self.settings_btn.setFixedSize(22, 22)
        self.settings_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.settings_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.settings_btn.setToolTip("Background opacity")
        self.settings_btn.setAccessibleName("Overlay background opacity settings")
        set_button_icon(self.settings_btn, "adjustments-horizontal", "#9CA3AF", 16)
        header.addWidget(self.settings_btn)
        layout.addWidget(self.drag_header)

        # Detection Caption
        caption = QLabel("Detected in current frame")
        caption.setObjectName("overlayCaption")
        layout.addWidget(caption)

        # Section Separator
        self.separator = QFrame()
        self.separator.setObjectName("separator")
        self.separator.setFixedHeight(1)
        layout.addWidget(self.separator)

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

        # A popup closes on Escape or a click outside it, without changing layout.
        self.opacity_popup = QFrame(
            self, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint
        )
        self.opacity_popup.setObjectName("overlayOpacityPopup")
        self.opacity_popup.setFixedWidth(220)
        popup_layout = QVBoxLayout(self.opacity_popup)
        popup_layout.setContentsMargins(12, 12, 12, 12)
        popup_layout.setSpacing(8)
        popup_heading = QHBoxLayout()
        popup_heading.addWidget(QLabel("Background opacity"))
        popup_heading.addStretch()
        self.opacity_value = QLabel()
        self.opacity_value.setObjectName("mutedText")
        popup_heading.addWidget(self.opacity_value)
        popup_layout.addLayout(popup_heading)
        self.opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.opacity_slider.setRange(0, 100)
        self.opacity_slider.setValue(85)
        self.opacity_slider.setAccessibleName("Overlay background opacity")
        popup_layout.addWidget(self.opacity_slider)
        self.settings_btn.clicked.connect(self.show_opacity_popup)
        self.opacity_slider.valueChanged.connect(self.set_background_opacity)
        self.set_background_opacity(self.opacity_slider.value())

        # Initial Overlay Position
        self.move(self.MARGIN, self.MARGIN)

        # Monitor Header Mouse Events and Preview Resize Events
        self.drag_header.installEventFilter(self)
        parent.installEventFilter(self)

    def show_opacity_popup(self):
        if self.opacity_popup.isVisible():
            self.opacity_popup.hide()
            return

        self.opacity_popup.adjustSize()
        point = self.settings_btn.mapToGlobal(QPoint(
            self.settings_btn.width() - self.opacity_popup.width(),
            self.settings_btn.height() + 6,
        ))
        bounds = self.screen().availableGeometry()
        point.setX(max(bounds.left(), min(point.x(), bounds.right() - self.opacity_popup.width() + 1)))
        point.setY(max(bounds.top(), min(point.y(), bounds.bottom() - self.opacity_popup.height() + 1)))
        self.opacity_popup.move(point)
        self.opacity_popup.show()
        self.opacity_slider.setFocus()

    def set_background_opacity(self, value):
        self.opacity_value.setText(f"{value}%")
        alpha = round(255 * value / 100)
        border = "border-color: transparent;" if value == 0 else ""
        # Scope the alpha to the frame: text, icons and popup stay fully opaque.
        self.setStyleSheet(
            "QFrame#detectionOverlay {"
            f"background-color: rgba(37, 37, 51, {alpha}); {border}"
            "}"
        )
        # Hide the separator without removing its space or shifting the rows.
        self.separator.setStyleSheet("background: transparent;" if value == 0 else "")

    def hideEvent(self, event):
        # Do not leave the popup open when the overlay or its parent window is hidden.
        self.opacity_popup.hide()
        super().hideEvent(event)

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
