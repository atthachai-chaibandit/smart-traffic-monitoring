from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QButtonGroup, QCheckBox, QFrame, QHBoxLayout, QLabel,
    QPushButton, QSlider, QVBoxLayout,
)

from .icons import get_pixmap, set_button_icon


class ControlPanel(QFrame):
    """Input widgets only; no media, ROI or detection handlers are attached."""

    def __init__(self):
        super().__init__()
        self.setObjectName("controlPanel")
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(6)
        heading = QLabel("Controls")
        heading.setObjectName("sectionHeading")
        layout.addWidget(heading)
        self.add_caption(layout, "1. SOURCE")
        self.upload_btn = self.make_button("", "uploadButton")
        self.upload_btn.setAccessibleName("Upload Media")
        upload_layout = QVBoxLayout(self.upload_btn)
        upload_layout.setContentsMargins(6, 5, 6, 5)
        upload_layout.setSpacing(3)
        icon = QLabel()
        icon.setPixmap(get_pixmap("upload", "#A78BFA", 20, self.devicePixelRatioF()))
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        caption = QLabel("Upload Media")
        caption.setAlignment(Qt.AlignmentFlag.AlignCenter)
        for child in (icon, caption):
            child.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            upload_layout.addWidget(child)
        self.upload_btn.setFixedHeight(50)
        layout.addWidget(self.upload_btn)
        self.add_separator(layout)

        self.add_caption(layout, "2. ENHANCEMENT")
        enhancement = QHBoxLayout()
        sun = QLabel()
        sun.setPixmap(get_pixmap("brightness-up", "#A78BFA", 20, self.devicePixelRatioF()))
        enhancement.addWidget(sun)
        enhancement.addWidget(QLabel("Brighten Image"))
        enhancement.addStretch()
        self.enhance_checkbox = QCheckBox()
        self.enhance_checkbox.setAccessibleName("Enable brightness adjustment")
        enhancement.addWidget(self.enhance_checkbox)
        layout.addLayout(enhancement)
        self.brightness_slider = QSlider(Qt.Orientation.Horizontal)
        self.brightness_slider.setRange(0, 100)
        self.brightness_slider.setValue(55)
        self.brightness_slider.setAccessibleName("Brightness strength")
        layout.addWidget(self.brightness_slider)
        strength = QHBoxLayout()
        strength.addWidget(self.muted_label("Brightness preview"))
        strength.addStretch()
        self.brightness_value = self.muted_label("55%")
        strength.addWidget(self.brightness_value)
        layout.addLayout(strength)
        # Only mirrors the input value; does not process an image.
        self.brightness_slider.valueChanged.connect(
            lambda value: self.brightness_value.setText(f"{value}%")
        )
        modes = QHBoxLayout()
        modes.setSpacing(6)
        self.view_modes = QButtonGroup(self)
        for index, name in enumerate(("Original", "Enhanced")):
            button = self.make_button(name, "viewChip", checkable=True)
            button.setMinimumHeight(24)
            button.setChecked(index == 0)
            self.view_modes.addButton(button)
            modes.addWidget(button)
        modes.addStretch()
        layout.addLayout(modes)
        self.add_separator(layout)

        self.add_caption(layout, "3. ROAD REGION")
        self.roi_btn = self.make_button("Draw / Edit Road ROI", "roadButton", "pentagon")
        layout.addWidget(self.roi_btn)
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
        self.mask_checkbox = QCheckBox()
        self.mask_checkbox.setChecked(True)
        self.mask_checkbox.setAccessibleName("Black background outside ROI")
        mask_row.addWidget(self.mask_checkbox)
        layout.addLayout(mask_row)
        self.add_separator(layout, compact=True)
        self.add_caption(layout, "VIDEO COUNTING")
        self.counting_line_btn = self.make_button("Draw Counting Line", "roadButton", "line")
        layout.addWidget(self.counting_line_btn)
        edit_row = QHBoxLayout()
        edit_row.setSpacing(8)
        self.undo_btn = self.make_button("Undo Point", "secondaryButton")
        self.reset_roi_btn = self.make_button("Reset ROI", "secondaryButton")
        edit_row.addWidget(self.undo_btn)
        edit_row.addWidget(self.reset_roi_btn)
        layout.addLayout(edit_row)
        self.add_separator(layout)
        self.add_caption(layout, "4. DETECTION")
        self.detect_btn = self.make_button("Run Detection", "primaryButton", "player-play", "#15111E")
        layout.addWidget(self.detect_btn)
        layout.addStretch(1)

    @staticmethod
    def muted_label(text):
        label = QLabel(text)
        label.setObjectName("mutedText")
        return label

    def add_caption(self, layout, text):
        label = self.muted_label(text)
        label.setObjectName("groupCaption")
        layout.addWidget(label)

    @staticmethod
    def make_button(text, name, icon=None, color="#A78BFA", *, checkable=False):
        button = QPushButton(text)
        button.setObjectName(name)
        button.setCheckable(checkable)
        button.setFocusPolicy(
            Qt.FocusPolicy.StrongFocus if checkable else Qt.FocusPolicy.NoFocus
        )
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setMinimumHeight(36 if name == "roadButton" else 30)
        if icon:
            set_button_icon(button, icon, color, 19)
        return button

    @staticmethod
    def add_separator(layout, compact=False):
        layout.addSpacing(2 if compact else 4)
        line = QFrame()
        line.setObjectName("separator")
        line.setFixedHeight(1)
        layout.addWidget(line)
        layout.addSpacing(2 if compact else 4)
