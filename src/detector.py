"""Vehicle detection and tracking, independent of the GUI and counting code."""
from pathlib import Path


MODEL_PATH = Path(__file__).resolve().parent.parent / "model" / "smart_traffic.pt"
VEHICLE_COLORS = {
    "car": "#38BDF8",
    "motorcycle": "#FACC15",
    "bus": "#E879F9",
    "truck": "#FB923C",
}


class VehicleDetector:
    def __init__(self, model_path=MODEL_PATH):
        # Import and load on the worker thread, only when detection is requested.
        from ultralytics import YOLO

        model_path = Path(model_path)
        if not model_path.is_file():
            raise FileNotFoundError(f"Model not found: {model_path}")
        self.model = YOLO(str(model_path))
        self.class_names = self.model.names
        if not set(VEHICLE_COLORS).issubset(set(self.class_names.values())):
            raise ValueError("The model must contain car, motorcycle, bus and truck classes.")

    def reset_tracking(self):
        # Clear track history without loading the model again.
        predictor = self.model.predictor
        for tracker in getattr(predictor, "trackers", ()):
            tracker.reset()

    def detect(self, frame, *, tracking=False):
        if tracking:
            result = self.model.track(
                frame, persist=True, tracker="bytetrack.yaml", conf=0.25, verbose=False
            )[0]
        else:
            result = self.model.predict(frame, conf=0.25, verbose=False)[0]
        # Keep coordinates relative to the full source image.
        detections = []
        for box in result.boxes:
            name = result.names[int(box.cls.item())]
            if name not in VEHICLE_COLORS:
                continue
            detections.append({
                "box": tuple(float(value) for value in box.xyxy[0].tolist()),
                "class_name": name,
                "confidence": float(box.conf.item()),
                "track_id": int(box.id.item()) if tracking and box.id is not None else None,
            })
        return detections
