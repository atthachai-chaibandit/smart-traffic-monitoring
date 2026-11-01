"""Process frames on one persistent thread without blocking the GUI."""
from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot

from ..detector import VehicleDetector


class DetectionWorker(QObject):
    result_ready = pyqtSignal(int, list)
    failed = pyqtSignal(int, str)
    job_finished = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.detector = None

    @pyqtSlot(object, int)
    def detect_frame(self, frame, revision):
        try:
            if self.detector is None:
                self.detector = VehicleDetector()
            detections = self.detector.detect(frame)
            self.result_ready.emit(revision, detections)
        except Exception as error:
            # Report dependency, model and inference errors on the GUI thread.
            self.failed.emit(revision, str(error))
        finally:
            # Completing a job keeps the thread alive for the next frame.
            self.job_finished.emit()
