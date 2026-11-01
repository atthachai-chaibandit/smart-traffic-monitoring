"""Run one inference request at a time without blocking Qt's event loop."""
from PyQt6.QtCore import QThread, pyqtSignal

from ..detector import VehicleDetector


class DetectionWorker(QThread):
    result_ready = pyqtSignal(int, list)
    failed = pyqtSignal(int, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.detector = None
        self.frame = None
        self.revision = 0

    def run(self):
        try:
            if self.detector is None:
                self.detector = VehicleDetector()
            detections = self.detector.detect(self.frame)
            self.result_ready.emit(self.revision, detections)
        except Exception as error:
            # Report dependency, model and inference errors on the GUI thread.
            self.failed.emit(self.revision, str(error))
