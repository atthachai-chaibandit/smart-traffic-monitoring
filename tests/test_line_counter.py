"""Verify line geometry, direction, counting state and GUI summary updates."""
import unittest

from PyQt6.QtWidgets import QLabel

from src.line_counter import LineCounter
import test_tracking as tracking


def vehicle(x, y, track_id=1, name="car"):
    return {"box": (x - 5, y - 5, x + 5, y + 5), "track_id": track_id,
            "class_name": name, "confidence": 0.9}


class LineCounterTests(unittest.TestCase):
    def test_horizontal_in_out_and_once_per_id(self):
        counter = LineCounter(((0, 50), (100, 50)))
        for index, y in enumerate((20, 50, 80, 20, 80)):
            counter.update([vehicle(40, y)], index)
        counter.update([vehicle(60, 80, 2, "truck")], 5)
        counter.update([vehicle(60, 20, 2, "truck")], 6)
        self.assertEqual(counter.counts["in"]["car"], 1)
        self.assertEqual(counter.counts["out"]["truck"], 1)
        self.assertEqual(len(counter.counted_ids), 2)

    def test_vertical_diagonal_and_reversed_line(self):
        cases = [(((50, 0), (50, 100)), (80, 40), (20, 40), "in"),
                 (((0, 0), (100, 100)), (60, 20), (20, 60), "in"),
                 (((100, 50), (0, 50)), (40, 20), (40, 80), "out")]
        for line, before, after, direction in cases:
            with self.subTest(line=line):
                counter = LineCounter(line)
                counter.update([vehicle(*before)], 0)
                counter.update([vehicle(*after)], 1)
                self.assertEqual(counter.counts[direction]["car"], 1)

    def test_crossing_outside_segment_does_not_count(self):
        counter = LineCounter(((20, 50), (80, 50)))
        counter.update([vehicle(90, 20)], 0)
        counter.update([vehicle(90, 80)], 1)
        self.assertFalse(counter.counted_ids)

    def test_uses_intersection_not_current_x(self):
        counter = LineCounter(((20, 50), (80, 50)))
        counter.update([vehicle(0, 0)], 0)
        counter.update([vehicle(100, 100)], 1)
        self.assertEqual(counter.counts["in"]["car"], 1)

    def test_near_line_jitter_and_start_on_line_do_not_count(self):
        counter = LineCounter(((0, 50), (100, 50)))
        for index, y in enumerate((50, 49, 51, 80, 51, 49, 80)):
            counter.update([vehicle(40, y)], index)
        self.assertFalse(counter.counted_ids)

    def test_stable_sides_across_dead_band_count_once(self):
        counter = LineCounter(((0, 50), (100, 50)))
        for index, y in enumerate((20, 49, 50, 51, 80)):
            counter.update([vehicle(40, y)], index)
        self.assertEqual(counter.counts["in"]["car"], 1)

    def test_waiting_near_line_keeps_last_stable_side(self):
        counter = LineCounter(((0, 50), (100, 50)))
        counter.update([vehicle(40, 20)], 0)
        for index in range(1, 80):
            counter.update([vehicle(40, 50)], index)
        counter.update([vehicle(40, 80)], 80)
        self.assertEqual(counter.counts["in"]["car"], 1)

    def test_missing_ids_and_long_gaps_do_not_count(self):
        counter = LineCounter(((0, 50), (100, 50)))
        counter.update([vehicle(40, 20, None), vehicle(60, 20, 2)], 0)
        counter.update([vehicle(40, 80, None), vehicle(60, 80, 2)], 40)
        self.assertFalse(counter.counted_ids)

    def test_all_classes_and_summary_is_a_copy(self):
        counter = LineCounter(((0, 50), (100, 50)))
        for index, name in enumerate(("car", "motorcycle", "bus", "truck")):
            counter.update([vehicle(40, 20, index, name)], 0)
            counter.update([vehicle(40, 80, index, name)], 1)
        snapshot = counter.summary()
        self.assertEqual(sum(snapshot["in"].values()), 4)
        snapshot["in"]["car"] = 99
        self.assertEqual(counter.counts["in"]["car"], 1)

    def test_zero_length_line_is_rejected(self):
        with self.assertRaises(ValueError):
            LineCounter(((10, 10), (10, 10)))


class CountingWorkerTests(unittest.TestCase):
    setUp = tracking.WorkerTests.setUp

    def test_duplicate_frame_and_new_session_counting(self):
        positions = iter((15, 35, 15))
        self.detector.detect = lambda frame, tracking, confidence: [vehicle(40, next(positions))]
        summaries = []
        self.worker.result_ready.connect(lambda revision, result, counts: summaries.append(counts))
        line = ((0, 25), (96, 25))
        for index in (0, 1, 1):
            self.worker.detect_frame(self.frame, 1, 1, index, True, line)
        self.assertEqual([s["in"]["car"] for s in summaries], [0, 1, 1])
        self.worker.detect_frame(self.frame, 2, 2, 0, True, line)
        self.assertEqual(summaries[-1]["in"]["car"], 0)


class CountingGuiTests(unittest.TestCase):
    setUpClass = classmethod(tracking.GuiTrackingTests.setUpClass.__func__)
    tearDownClass = classmethod(tracking.GuiTrackingTests.tearDownClass.__func__)
    setUp = tracking.GuiTrackingTests.setUp
    tearDown = tracking.GuiTrackingTests.tearDown
    wait_for = tracking.GuiTrackingTests.wait_for
    detect_paused_frame = tracking.GuiTrackingTests.detect_paused_frame

    def values(self):
        canvas = self.window.preview_canvas
        return [card.findChild(QLabel, "statValue").text()
                for card in (canvas.total_card, canvas.in_card, canvas.out_card)]

    def test_counting_cards_stop_and_reset(self):
        self.window.preview_canvas.counting_line = [(0, 25), (96, 25)]
        self.window.preview_canvas.edit_changed.emit()
        self.detector.detect = lambda frame, tracking, confidence: [vehicle(40, 15 + float(frame.mean()) * 4)]
        self.detect_paused_frame()
        self.assertEqual(self.values(), ["0", "0", "0"])
        self.window.toggle_playback()
        self.wait_for(lambda: self.window.current_frame >= 1)
        self.window.pause_video()
        self.wait_for(lambda: not self.window._detection_busy)
        self.assertEqual(self.values(), ["1", "1", "0"])
        self.window.stop_detection()
        self.assertEqual(self.values(), ["1", "1", "0"])
        self.detect_paused_frame()
        self.assertEqual(self.values(), ["0", "0", "0"])
        self.window.preview_canvas.clear_counting_line()
        self.wait_for(lambda: not self.window._detection_busy)
        self.assertEqual(self.values(), ["—", "—", "—"])


if __name__ == "__main__":
    unittest.main()
