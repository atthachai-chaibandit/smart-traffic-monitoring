"""Verify settings drafts, display-only changes and inference session resets."""
from dataclasses import replace
import unittest
from unittest.mock import Mock

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication, QLabel

from src.detector import VehicleDetector
from src.gui.settings_dialog import AppSettings, SettingsDialog
import test_tracking as tracking


class SettingsGuiTests(unittest.TestCase):
    setUpClass = classmethod(tracking.GuiTrackingTests.setUpClass.__func__)
    tearDownClass = classmethod(tracking.GuiTrackingTests.tearDownClass.__func__)
    setUp = tracking.GuiTrackingTests.setUp
    tearDown = tracking.GuiTrackingTests.tearDown
    wait_for = tracking.GuiTrackingTests.wait_for
    detect_paused_frame = tracking.GuiTrackingTests.detect_paused_frame

    def test_invalid_confidence_disables_apply(self):
        dialog = SettingsDialog(AppSettings(), self.window)
        for text in ("", "0", "1.01", "abc"):
            dialog.confidence_input.setText(text)
            self.assertFalse(dialog.apply_btn.isEnabled())
        dialog.confidence_input.setText("0.50")
        self.assertTrue(dialog.apply_btn.isEnabled())
        self.assertEqual(dialog.values().confidence, 0.5)
        dialog.deleteLater()

    def test_restore_defaults_is_only_a_draft_until_apply(self):
        original = AppSettings(0.6, False, False, False)
        self.window.apply_settings(original)
        dialog = SettingsDialog(self.window.settings, self.window)
        self.assertEqual(dialog.values(), original)
        dialog.defaults_btn.click()
        self.assertEqual(dialog.values(), AppSettings())
        self.assertEqual(self.window.settings, original)
        dialog.reject()
        self.assertEqual(self.window.settings, original)
        dialog.deleteLater()

    def test_display_changes_keep_results_session_and_counts(self):
        self.detect_paused_frame()
        canvas = self.window.preview_canvas
        canvas.set_counting_summary({"in": {"car": 3}, "out": {"car": 1}})
        before = (self.window._tracking_session, self.window._detection_revision,
                  len(self.detector.calls))
        detection = canvas.detections[0]
        self.window.apply_settings(AppSettings(show_confidence=False, show_track_id=False,
                                               show_overlay=False))
        self.assertEqual(canvas.detection_label(detection), "car")
        self.assertTrue(canvas.detection_overlay.isHidden())
        self.assertEqual(canvas.total_card.findChild(QLabel, "statValue").text(), "4")
        self.assertEqual(before, (self.window._tracking_session, self.window._detection_revision,
                                  len(self.detector.calls)))

    def test_overlay_preference_survives_edit_and_clear(self):
        self.window.apply_settings(AppSettings(show_overlay=False))
        self.window.begin_roi()
        self.window.preview_canvas.cancel_edit()
        self.assertTrue(self.window.preview_canvas.detection_overlay.isHidden())
        self.window.apply_settings(AppSettings())
        self.window.begin_roi()
        self.assertTrue(self.window.preview_canvas.detection_overlay.isHidden())
        self.window.preview_canvas.cancel_edit()
        self.assertFalse(self.window.preview_canvas.detection_overlay.isHidden())
        self.window.apply_settings(AppSettings(show_overlay=False))
        self.window.clear_media()
        self.assertTrue(self.window.preview_canvas.detection_overlay.isHidden())
        self.assertFalse(self.window.settings.show_overlay)

    def test_confidence_change_resets_video_and_reaches_worker(self):
        self.detect_paused_frame()
        previous_session = self.window._tracking_session
        self.detector.detect = Mock(wraps=self.detector.detect)
        self.window.apply_settings(replace(self.window.settings, confidence=0.65))
        self.wait_for(lambda: not self.window._detection_busy)
        self.assertGreater(self.window._tracking_session, previous_session)
        self.assertEqual(self.detector.resets, 2)
        self.assertEqual(self.detector.detect.call_args.kwargs["confidence"], 0.65)
        self.assertFalse(self.window.is_playing)

    def test_confidence_change_refreshes_detected_image(self):
        self.window.load_media(self.image)
        self.window.run_detection()
        self.wait_for(lambda: not self.window._detection_busy)
        self.detector.detect = Mock(wraps=self.detector.detect)
        self.window.apply_settings(AppSettings(confidence=0.7))
        self.wait_for(lambda: not self.window._detection_busy)
        self.assertEqual(self.detector.detect.call_args.kwargs,
                         {"tracking": False, "confidence": 0.7})

    def test_title_button_opens_dialog_and_resumes_playback(self):
        self.detect_paused_frame()
        self.window.toggle_playback()
        observed = []

        def edit_dialog():
            dialog = QApplication.activeModalWidget()
            observed.append((isinstance(dialog, SettingsDialog), self.window.is_playing))
            dialog.track_id_checkbox.setChecked(False)
            dialog.apply_btn.click()

        QTimer.singleShot(0, edit_dialog)
        self.window.app_title.settings_btn.click()
        self.assertEqual(observed, [(True, False)])
        self.assertTrue(self.window.is_playing)
        self.assertFalse(self.window.settings.show_track_id)
        self.window.pause_video()


class SettingsDetectorTests(unittest.TestCase):
    def test_confidence_is_forwarded_in_both_modes(self):
        detector = VehicleDetector.__new__(VehicleDetector)
        detector.model = Mock()
        result = Mock(boxes=[])
        detector.model.predict.return_value = [result]
        detector.model.track.return_value = [result]
        frame = object()
        detector.detect(frame, confidence=0.6)
        detector.model.predict.assert_called_once_with(frame, conf=0.6, verbose=False)
        detector.detect(frame, tracking=True, confidence=0.7)
        detector.model.track.assert_called_once_with(
            frame, persist=True, tracker="bytetrack.yaml", conf=0.7, verbose=False)


if __name__ == "__main__":
    unittest.main()
