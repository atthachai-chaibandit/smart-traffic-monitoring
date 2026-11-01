"""Count tracked vehicle centers crossing a finite, directed line segment."""
from math import hypot


VEHICLE_CLASSES = ("car", "motorcycle", "bus", "truck")


class LineCounter:
    def __init__(self, points, margin=2.0, max_gap=30):
        self.start, self.end = points
        self.dx = self.end[0] - self.start[0]
        self.dy = self.end[1] - self.start[1]
        self.length = hypot(self.dx, self.dy)
        if self.length == 0:
            raise ValueError("The counting line needs two different points.")
        self.margin = margin
        self.max_gap = max_gap
        self.previous = {}
        self.counted_ids = set()
        self.counts = {direction: dict.fromkeys(VEHICLE_CLASSES, 0) for direction in ("in", "out")}

    def distance(self, point):
        # Positive is the IN side; reversing the line reverses IN and OUT.
        return (self.dx * (point[1] - self.start[1])
                - self.dy * (point[0] - self.start[0])) / self.length

    def update(self, detections, frame_index):
        # Do not connect positions separated by a long tracking gap.
        self.previous = {key: value for key, value in self.previous.items()
                         if frame_index - value[1] <= self.max_gap}
        for detection in detections:
            track_id = detection.get("track_id")
            name = detection["class_name"]
            if track_id is None or track_id in self.counted_ids or name not in VEHICLE_CLASSES:
                continue
            x1, y1, x2, y2 = detection["box"]
            center = ((x1 + x2) / 2, (y1 + y2) / 2)
            distance = self.distance(center)
            previous = self.previous.get(track_id)
            if abs(distance) <= self.margin:
                # Keep the last stable side while the center is close to the line.
                if previous is not None:
                    self.previous[track_id] = (previous[0], frame_index)
                continue
            self.previous[track_id] = (center, frame_index)
            if previous is None:
                continue
            before = previous[0]
            before_distance = self.distance(before)
            if before_distance * distance >= 0:
                continue
            fraction = before_distance / (before_distance - distance)
            intersection = (before[0] + fraction * (center[0] - before[0]),
                            before[1] + fraction * (center[1] - before[1]))
            position = ((intersection[0] - self.start[0]) * self.dx
                        + (intersection[1] - self.start[1]) * self.dy) / self.length ** 2
            if 0 <= position <= 1:
                direction = "in" if distance > 0 else "out"
                self.counts[direction][name] += 1
                self.counted_ids.add(track_id)
                del self.previous[track_id]

    def summary(self):
        # Return a snapshot so later worker updates cannot change a queued result.
        return {direction: dict(values) for direction, values in self.counts.items()}
