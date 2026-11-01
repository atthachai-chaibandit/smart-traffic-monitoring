"""Settings edited as a draft until the user presses Apply."""
from dataclasses import dataclass

from PyQt6.QtCore import QLocale, Qt
from PyQt6.QtGui import QDoubleValidator
from PyQt6.QtWidgets import (
    QCheckBox, QDialog, QFrame, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QVBoxLayout,
)


@dataclass(frozen=True)
class AppSettings:
    confidence: float = 0.25
    show_confidence: bool = True
    show_track_id: bool = True
    show_overlay: bool = True


class SettingsDialog(QDialog):
    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.setObjectName("settingsDialog")
        self.setWindowTitle("Settings")
        self.setFixedWidth(360)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        heading = QLabel("Detection")
        heading.setObjectName("sectionHeading")
        layout.addWidget(heading)
        row = QHBoxLayout()
        label = QLabel("Confidence threshold")
        row.addWidget(label)
        row.addStretch()
        self.confidence_input = QLineEdit()
        validator = QDoubleValidator(0.01, 1.0, 2, self)
        locale = QLocale.c()
        locale.setNumberOptions(locale.numberOptions() | QLocale.NumberOption.RejectGroupSeparator)
        validator.setLocale(locale)
        validator.setNotation(QDoubleValidator.Notation.StandardNotation)
        self.confidence_input.setValidator(validator)
        self.confidence_input.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.confidence_input.setToolTip("Enter a confidence threshold from 0.01 to 1.00.")
        self.confidence_input.setFixedWidth(90)
        self.confidence_input.setAccessibleName("Detection confidence threshold")
        label.setBuddy(self.confidence_input)
        row.addWidget(self.confidence_input)
        layout.addLayout(row)
        note = QLabel("Changing confidence starts a new tracking and counting session.")
        note.setObjectName("mutedText")
        note.setWordWrap(True)
        layout.addWidget(note)

        separator = QFrame()
        separator.setObjectName("separator")
        separator.setFixedHeight(1)
        layout.addWidget(separator)
        heading = QLabel("Display")
        heading.setObjectName("sectionHeading")
        layout.addWidget(heading)
        self.confidence_checkbox = QCheckBox("Show confidence")
        self.track_id_checkbox = QCheckBox("Show track ID")
        self.overlay_checkbox = QCheckBox("Show vehicle overlay")
        for checkbox in (self.confidence_checkbox, self.track_id_checkbox, self.overlay_checkbox):
            layout.addWidget(checkbox)

        buttons = QHBoxLayout()
        self.defaults_btn = QPushButton("Restore defaults")
        self.defaults_btn.setObjectName("secondaryButton")
        self.apply_btn = QPushButton("Apply")
        self.apply_btn.setObjectName("primaryButton")
        for button in (self.defaults_btn, self.apply_btn):
            button.setFixedHeight(34)
            button.setAutoDefault(False)
        self.apply_btn.setMinimumWidth(85)
        buttons.addWidget(self.defaults_btn)
        buttons.addStretch()
        buttons.addWidget(self.apply_btn)
        layout.addLayout(buttons)
        self.defaults_btn.clicked.connect(lambda: self.set_values(AppSettings()))
        self.apply_btn.clicked.connect(self.accept)
        self.confidence_input.textChanged.connect(
            lambda: self.apply_btn.setEnabled(self.confidence_input.hasAcceptableInput())
        )
        self.set_values(settings)

    def set_values(self, settings):
        self.confidence_input.setText(f"{settings.confidence:.2f}")
        self.confidence_checkbox.setChecked(settings.show_confidence)
        self.track_id_checkbox.setChecked(settings.show_track_id)
        self.overlay_checkbox.setChecked(settings.show_overlay)

    def accept(self):
        # Validate again for keyboard or programmatic acceptance, not only button clicks.
        if not self.confidence_input.hasAcceptableInput():
            self.confidence_input.setFocus()
            return
        super().accept()

    def values(self):
        return AppSettings(
            confidence=float(self.confidence_input.text()),
            show_confidence=self.confidence_checkbox.isChecked(),
            show_track_id=self.track_id_checkbox.isChecked(),
            show_overlay=self.overlay_checkbox.isChecked(),
        )
