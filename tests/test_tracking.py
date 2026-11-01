"""Check tracker sessions without loading YOLO or requiring a GPU."""
import os
import tempfile
import time
import unittest
from pathlib import Path
from threading import Event, get_ident
from unittest.mock import Mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import cv2
import numpy as np
from PyQt6.QtWidgets import QApplication

from src.gui.detection_worker import DetectionWorker
from src.gui.main_window import MainWindow


class FakeDetector:
    def __init__(self):
        self.resets = 0
        self.calls = []
        self.gate = None

    def reset_tracking(self):
        self.resets += 1

    def detect(self, frame, *, tracking=False):
        self.calls.append((get_ident(), tracking, frame.copy()))
        if self.gate is not None:
            if not self.gate.wait(5):
                raise RuntimeError("Test did not release the worker.")
        return [{"box": (10, 10, 40, 40), "class_name": "car",
                 "confidence": 0.9, "track_id": self.resets if tracking else None}]


class WorkerTests(unittest.TestCase):
    def setUp(self):
        self.worker = DetectionWorker()
        self.detector = FakeDetector()
        self.worker.detector = self.detector
        self.frame = np.zeros((64, 96, 3), dtype=np.uint8)
        self.results = []
        self.worker.result_ready.connect(lambda revision, result, counts: self.results.append((revision, result)))

    def send(self, index, session=1, revision=1, tracking=True):
        self.worker.detect_frame(self.frame, revision, session, index, tracking)

    def test_consecutive_frames_keep_tracker_and_duplicate_is_cached(self):
        self.send(0)
        self.send(1)
        self.send(1, revision=2)
        self.assertEqual(self.detector.resets, 1)
        self.assertEqual(len(self.detector.calls), 2)
        self.assertEqual(self.results[-1][0], 2)
        self.assertEqual(self.results[-1][1], self.results[-2][1])

    def test_new_session_resets_before_same_frame(self):
        self.send(5)
        self.send(5, session=2)
        self.assertEqual(self.detector.resets, 2)
        self.assertEqual(len(self.detector.calls), 2)

    def test_nonconsecutive_frame_resets_tracker(self):
        for index in (4, 5, 20, 3):
            self.send(index)
        self.assertEqual(self.detector.resets, 3)

    def test_images_are_not_cached_or_tracked(self):
        self.send(0, tracking=False)
        self.send(0, tracking=False)
        self.assertEqual(len(self.detector.calls), 2)
        self.assertIsNone(self.results[-1][1][0]["track_id"])

    def test_error_starts_fresh_on_retry(self):
        self.detector.detect = Mock(side_effect=RuntimeError("inference failed"))
        errors, finished = [], []
        self.worker.failed.connect(lambda revision, error: errors.append(error))
        self.worker.job_finished.connect(lambda: finished.append(True))
        self.send(0)
        self.send(0)
        self.assertEqual(self.detector.resets, 2)
        self.assertEqual(errors, ["inference failed"] * 2)
        self.assertEqual(len(finished), 2)


class GuiTrackingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.folder = tempfile.TemporaryDirectory()
        cls.video = Path(cls.folder.name) / "sample.avi"
        writer = cv2.VideoWriter(str(cls.video), cv2.VideoWriter_fourcc(*"MJPG"), 30, (96, 64))
        assert writer.isOpened()
        for index in range(20):
            writer.write(np.full((64, 96, 3), index * 5, dtype=np.uint8))
        writer.release()
        cls.image = Path(cls.folder.name) / "sample.png"
        cv2.imwrite(str(cls.image), np.zeros((64, 96, 3), dtype=np.uint8))

    @classmethod
    def tearDownClass(cls):
        cls.folder.cleanup()

    def setUp(self):
        self.window = MainWindow()
        self.detector = FakeDetector()
        self.window.detection_worker.detector = self.detector
        self.window.load_media(self.video)

    def wait_for(self, condition, timeout=5):
        deadline = time.monotonic() + timeout
        while not condition():
            self.app.processEvents()
            if time.monotonic() > deadline:
                self.fail("Timed out waiting for the GUI worker.")
            time.sleep(0.002)
        self.app.processEvents()

    def detect_paused_frame(self):
        self.window.run_detection()
        self.window.pause_video()
        self.wait_for(lambda: not self.window._detection_busy)

    def tearDown(self):
        if self.detector.gate is not None:
            self.detector.gate.set()
        self.wait_for(lambda: not self.window._detection_busy)
        self.window.close()
        self.app.processEvents()

    def test_pause_and_preview_keep_session_and_worker_thread(self):
        self.detect_paused_frame()
        session = self.window._tracking_session
        calls = len(self.detector.calls)
        self.window.refresh_preview()
        self.window.toggle_playback()
        self.window.pause_video()
        self.app.processEvents()
        self.assertEqual(self.window._tracking_session, session)
        self.assertEqual(len(self.detector.calls), calls)
        self.assertNotEqual(self.detector.calls[0][0], get_ident())

    def test_seek_stop_restart_and_enhancement_reset(self):
        self.detect_paused_frame()
        self.window.seek_video(8)
        self.wait_for(lambda: not self.window._detection_busy)
        self.assertEqual(self.detector.resets, 2)
        self.assertEqual(self.window.current_frame, 8)
        self.window.stop_detection()
        self.detect_paused_frame()
        self.assertEqual(self.detector.resets, 3)
        self.window.control_panel.enhance_checkbox.setChecked(True)
        self.wait_for(lambda: not self.window._detection_busy)
        self.assertEqual(self.detector.resets, 4)

    def test_old_inflight_result_cannot_replace_new_session(self):
        self.detector.gate = Event()
        self.window.run_detection()
        self.wait_for(lambda: len(self.detector.calls) == 1)
        self.window.seek_video(12)
        self.detector.gate.set()
        self.wait_for(lambda: not self.window._detection_busy and not self.window._detection_requested)
        self.assertEqual(self.window.current_frame, 12)
        self.assertEqual(self.detector.resets, 2)
        self.assertEqual(self.window.preview_canvas.detections[0]["track_id"], 2)

    def test_switching_to_image_disables_tracking(self):
        self.detect_paused_frame()
        self.window.load_media(self.image)
        self.window.run_detection()
        self.wait_for(lambda: not self.window._detection_busy)
        self.assertFalse(self.detector.calls[-1][1])
        self.assertIsNone(self.window.preview_canvas.detections[0]["track_id"])
        self.window.clear_media()
        self.assertIsNone(self.window.preview_canvas.detections)

    def test_roi_and_enhancement_input_are_independent_of_preview(self):
        self.detect_paused_frame()
        panel = self.window.control_panel
        canvas = self.window.preview_canvas
        panel.enhance_checkbox.setChecked(True)
        self.wait_for(lambda: not self.window._detection_busy)
        panel.original_btn.click()
        session = self.window._tracking_session
        self.assertTrue(np.all(self.detector.calls[-1][2] == 40))
        canvas.roi_points = [(0, 0), (48, 0), (48, 63), (0, 63)]
        canvas.edit_changed.emit()
        self.wait_for(lambda: not self.window._detection_busy)
        self.assertGreater(self.window._tracking_session, session)
        model_input = self.detector.calls[-1][2]
        self.assertTrue(np.all(model_input[:, :48] == 40))
        self.assertTrue(np.all(model_input[:, 49:] == 0))
        calls = len(self.detector.calls)
        session = self.window._tracking_session
        panel.mask_checkbox.setChecked(False)
        canvas.counting_line = [(0, 0), (95, 63)]
        canvas.edit_changed.emit()
        self.app.processEvents()
        self.wait_for(lambda: not self.window._detection_busy)
        self.assertEqual(len(self.detector.calls), calls + 1)
        self.assertGreater(self.window._tracking_session, session)

    def test_eof_and_replay_start_a_new_session(self):
        self.window.fps = 1000
        self.window.run_detection()
        self.wait_for(lambda: self.window.at_end)
        self.assertEqual(self.window.current_frame, 19)
        self.assertFalse(self.window.is_playing)
        session = self.window._tracking_session
        self.window.toggle_playback()
        self.window.pause_video()
        self.wait_for(lambda: not self.window._detection_busy)
        self.assertGreater(self.window._tracking_session, session)
        self.assertEqual(self.window.current_frame, 0)
        self.assertEqual(self.detector.resets, 2)


if __name__ == "__main__":
    unittest.main()
