
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QButtonGroup, QCheckBox, QFrame, QHBoxLayout, QLabel,
    QPushButton, QSizePolicy, QSlider, QVBoxLayout,
)

from .icons import get_pixmap, set_button_icon

BRIGHT_STRENGTH = 50

class ControlPanel(QFrame):
    """Control widgets and selected file display; no processing handlers."""

    def __init__(self):
        super().__init__()

        self.setObjectName("controlPanel")
        self._filename = ""
        self.setup_ui()
        self.set_enhancement_available(False)
        self.set_roi_controls(False, False, False, False)

    def setup_ui(self):
        # Main Layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(6)

        # Panel Heading
        heading = QLabel("Controls")
        heading.setObjectName("sectionHeading")
        layout.addWidget(heading)

        # Source Section
        self.add_caption(layout, "1. SOURCE")

        # Upload Media Button
        self.upload_btn = self.make_button("", "uploadButton")
        self.upload_btn.setAccessibleName("Upload Media")

        upload_layout = QVBoxLayout(self.upload_btn)
        upload_layout.setContentsMargins(6, 5, 6, 5)
        upload_layout.setSpacing(3)

        # Upload Icon
        icon = QLabel()
        icon.setPixmap(
            get_pixmap("upload", "#A78BFA", 20, self.devicePixelRatioF())
        )
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Upload Label
        caption = QLabel("Upload Media")
        caption.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Add Upload Widgets
        for child in (icon, caption):
            child.setAttribute(
                # Let the parent QPushButton handle mouse events instead of the icon and label.
                Qt.WidgetAttribute.WA_TransparentForMouseEvents
            )
            upload_layout.addWidget(child)

        self.upload_btn.setFixedHeight(50)
        layout.addWidget(self.upload_btn)

        # Keep long file names from widening the control panel.
        self.filename_label = self.muted_label("No file selected")
        self.filename_label.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed
        )
        self.clear_btn = self.make_button("Clear", "clearMediaButton")
        self.clear_btn.setFixedSize(48, 22)
        self.clear_btn.setToolTip("Clear the selected media")
        self.clear_btn.hide()
        filename_row = QHBoxLayout()
        filename_row.setSpacing(8)
        filename_row.addWidget(self.filename_label, 1)
        filename_row.addWidget(self.clear_btn)
        layout.addLayout(filename_row)
        self.add_separator(layout)

        # Enhancement Section
        self.add_caption(layout, "2. ENHANCEMENT")

        # Brightness Toggle
        enhancement = QHBoxLayout()

        sun_icon = QLabel()
        sun_icon.setPixmap(
            get_pixmap("brightness-up", "#A78BFA", 20, self.devicePixelRatioF())
        )
        enhancement.addWidget(sun_icon)
        enhancement.addWidget(QLabel("Brighten Image"))
        enhancement.addStretch()

        self.enhance_checkbox = QCheckBox()
        self.enhance_checkbox.setAccessibleName("Enable brightness adjustment")
        enhancement.addWidget(self.enhance_checkbox)
        layout.addLayout(enhancement)

        # Brightness Slider
        self.brightness_slider = QSlider(Qt.Orientation.Horizontal)
        self.brightness_slider.setObjectName("brightnessSlider")
        self.brightness_slider.setRange(0, 100)
        self.brightness_slider.setValue(BRIGHT_STRENGTH)
        self.brightness_slider.setAccessibleName("Brightness strength")
        layout.addWidget(self.brightness_slider)

        # Brightness Value
        strength = QHBoxLayout()
        strength.addWidget(self.muted_label("Brightness preview"))
        strength.addStretch()

        self.brightness_value = self.muted_label(f"{BRIGHT_STRENGTH}%")
        strength.addWidget(self.brightness_value)
        layout.addLayout(strength)

        # Update Brightness Label
        self.brightness_slider.valueChanged.connect(
            lambda value: self.brightness_value.setText(f"{value}%")
        )

        # Preview Mode Buttons
        modes = QHBoxLayout()
        modes.setSpacing(6)

        self.view_modes = QButtonGroup(self)
        self.original_btn = self.make_button("Original", "viewChip", checkable=True)
        self.enhanced_btn = self.make_button("Enhanced", "viewChip", checkable=True)
        for index, button in enumerate((self.original_btn, self.enhanced_btn)):
            button.setMinimumHeight(24)
            button.setChecked(index == 0)
            self.view_modes.addButton(button)
            modes.addWidget(button)

        modes.addStretch()
        layout.addLayout(modes)
        self.add_separator(layout)

        # Road Region Section
        self.add_caption(layout, "3. ROAD REGION")

        # Draw / Edit ROI Button
        self.roi_btn = self.make_button(
            "Draw / Edit Road ROI", "roadButton", "road"
        )
        self.apply_roi_btn = self.make_button("Apply ROI", "roadButton", "circle-check")
        self.cancel_roi_btn = self.make_button("Cancel", "secondaryButton")
        self.cancel_roi_btn.setMinimumHeight(36)
        roi_row = QHBoxLayout()
        roi_row.setSpacing(8)
        roi_row.addWidget(self.roi_btn, 2)
        roi_row.addWidget(self.apply_roi_btn, 2)
        roi_row.addWidget(self.cancel_roi_btn, 1)
        layout.addLayout(roi_row)

        # Point history is only shown while drawing a replacement ROI.
        self.undo_btn = self.make_button("Undo Point", "secondaryButton")
        self.redo_btn = self.make_button("Redo Point", "secondaryButton")
        self.undo_btn.setToolTip("Undo point (Ctrl+Z)")
        self.redo_btn.setToolTip("Redo point (Ctrl+Y)")
        edit_row = QHBoxLayout()
        edit_row.setSpacing(8)
        edit_row.addWidget(self.undo_btn)
        edit_row.addWidget(self.redo_btn)
        layout.addLayout(edit_row)

        # ROI Background Mask
        mask_row = QHBoxLayout()
        mask_labels = QVBoxLayout()
        mask_labels.setSpacing(3)

        title = QLabel("Black background outside ROI")
        title.setWordWrap(True)
        mask_labels.addWidget(title)

        subtitle = self.muted_label("Hide areas outside the road")
        subtitle.setWordWrap(True)
        mask_labels.addWidget(subtitle)

        mask_row.addLayout(mask_labels, 1)

        # Mask Checkbox
        self.mask_checkbox = QCheckBox()
        self.mask_checkbox.setChecked(True)
        self.mask_checkbox.setAccessibleName(
            "Black background outside ROI"
        )
        mask_row.addWidget(self.mask_checkbox)
        layout.addLayout(mask_row)

        self.reset_roi_btn = self.make_button("Reset ROI", "secondaryButton")
        layout.addWidget(self.reset_roi_btn)

        self.add_separator(layout, compact=True)

        # Video Counting Section
        self.add_caption(layout, "VIDEO COUNTING")

        # Draw Counting Line Button
        self.counting_line_btn = self.make_button(
            "Draw Counting Line", "roadButton", "line"
        )
        layout.addWidget(self.counting_line_btn)

        self.add_separator(layout)

        # Detection Section
        self.add_caption(layout, "4. DETECTION")

        # Run Detection Button
        self.detect_btn = self.make_button(
            "Run Detection", "primaryButton", "player-play", "#15111E"
        )
        layout.addWidget(self.detect_btn)
        layout.addStretch(1)

    def set_filename(self, path):
        self._filename = Path(path).name
        self.filename_label.setToolTip(str(path))
        self.clear_btn.show()
        # Include the Clear button's width before shortening the file name.
        self.layout().activate()
        self._update_filename()

    def reset_controls(self):
        self._filename = ""
        self.filename_label.setToolTip("")
        self.clear_btn.hide()
        self.layout().activate()
        self._update_filename()
        self.enhance_checkbox.setChecked(False)
        self.brightness_slider.setValue(BRIGHT_STRENGTH)
        self.original_btn.setChecked(True)
        self.mask_checkbox.setChecked(True)
        self.set_enhancement_available(False)

    def set_enhancement_available(self, available):
        # Comparing Original keeps the adjustment settings for the next preview.
        enabled = available and self.enhance_checkbox.isChecked()
        self.enhance_checkbox.setEnabled(available)
        self.brightness_slider.setEnabled(enabled)
        self.original_btn.setEnabled(available)
        self.enhanced_btn.setEnabled(enabled)

    def set_roi_controls(self, available, editing, has_points, has_roi,
                         can_apply=False, can_redo=False):
        # Replace Draw/Edit with Apply and Cancel in the same row while editing.
        self.roi_btn.setVisible(not editing)
        self.roi_btn.setEnabled(available and not editing)
        self.apply_roi_btn.setVisible(editing)
        self.apply_roi_btn.setEnabled(editing and can_apply)
        self.cancel_roi_btn.setVisible(editing)
        self.undo_btn.setVisible(editing)
        self.undo_btn.setEnabled(editing and has_points)
        self.redo_btn.setVisible(editing)
        self.redo_btn.setEnabled(editing and can_redo)
        self.reset_roi_btn.setVisible(has_roi and not editing)
        self.reset_roi_btn.setEnabled(has_roi and not editing)
        self.mask_checkbox.setEnabled(has_roi and not editing)

    def _update_filename(self):
        text = self._filename or "No file selected"
        self.filename_label.setText(self.filename_label.fontMetrics().elidedText(
            text, Qt.TextElideMode.ElideRight, self.filename_label.width()
        ))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_filename()

    @staticmethod
    def muted_label(text):
        # Create Muted Label
        label = QLabel(text)
        label.setObjectName("mutedText")
        return label

    def add_caption(self, layout, text):
        # Create Section Caption
        label = self.muted_label(text)
        label.setObjectName("groupCaption")
        layout.addWidget(label)

    @staticmethod
    def make_button(text, name, icon=None, color="#A78BFA", *, checkable=False):
        # Create Button
        button = QPushButton(text)
        button.setObjectName(name)
        button.setCheckable(checkable)

        # Button Interaction
        button.setFocusPolicy(
            Qt.FocusPolicy.StrongFocus if checkable else Qt.FocusPolicy.NoFocus
        )
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setMinimumHeight(36 if name == "roadButton" else 30)

        # Button Icon
        if icon:
            set_button_icon(button, icon, color, 19)

        return button

    @staticmethod
    def add_separator(layout, compact=False):
        # Create Section Separator
        layout.addSpacing(2 if compact else 4)

        line = QFrame()
        line.setObjectName("separator")
        line.setFixedHeight(1)
        layout.addWidget(line)

        layout.addSpacing(2 if compact else 4)
