"""Process frames on one persistent thread without blocking the GUI."""
from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot

from ..detector import VehicleDetector
from ..line_counter import LineCounter


class DetectionWorker(QObject):
    result_ready = pyqtSignal(int, list, object)
    failed = pyqtSignal(int, str)
    job_finished = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.detector = None
        self.tracking_session = None
        self.last_frame_index = None
        self.last_detections = None
        self.counting_line = ()
        self.counter = None

    def start_session(self, session, line):
        # Tracker and counter must always start together on this worker thread.
        self.detector.reset_tracking()
        self.tracking_session = session
        self.last_frame_index = None
        self.last_detections = None
        self.counting_line = line
        self.counter = LineCounter(line) if len(line) == 2 else None

    @pyqtSlot(object, int, int, int, bool, object)
    def detect_frame(self, frame, revision, session, frame_index, tracking, counting_line=()):
        try:
            if self.detector is None:
                self.detector = VehicleDetector()
            line = tuple(tuple(point) for point in counting_line) if tracking else ()
            if session != self.tracking_session or line != self.counting_line:
                self.start_session(session, line)
            if tracking and frame_index == self.last_frame_index:
                # Redrawing a paused frame must not advance the tracker twice.
                detections = self.last_detections
            else:
                if (tracking and self.last_frame_index is not None
                        and frame_index != self.last_frame_index + 1):
                    self.start_session(session, line)
                detections = self.detector.detect(frame, tracking=tracking)
                if tracking and self.counter is not None:
                    self.counter.update(detections, frame_index)
                self.last_frame_index = frame_index if tracking else None
                self.last_detections = detections if tracking else None
            counts = self.counter.summary() if self.counter is not None else None
            self.result_ready.emit(revision, detections, counts)
        except Exception as error:
            # Retry with a fresh tracker after a partially completed job.
            self.tracking_session = None
            # Report dependency, model and inference errors on the GUI thread.
            self.failed.emit(revision, str(error))
        finally:
            # Completing a job keeps the thread alive for the next frame.
            self.job_finished.emit()
