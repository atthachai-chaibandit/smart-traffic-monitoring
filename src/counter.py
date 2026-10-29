"""ตรรกะนับรถที่ข้ามเส้นนับ

ไฟล์นี้ไม่ขึ้นกับ YOLO รับแค่ ID, ตำแหน่ง และประเภทของรถในแต่ละเฟรม
จึงทดสอบได้ด้วยข้อมูลจำลอง (ดูส่วนท้ายไฟล์)
"""

from collections import defaultdict

# ตำแหน่งเส้นนับ เก็บเป็นสัดส่วนของภาพ (0-1) จึงใช้กับวิดีโอทุกขนาดได้
# ค่าตั้งต้นเลือกจากวิดีโอ cars-on-the-road-11668582.mp4 (3840x2160)
DEFAULT_LINE_Y = 0.630   # ความสูงของเส้น (y=1361 px)
DEFAULT_X_LEFT = 0.212   # ปลายซ้าย = ขอบถนนฝั่งขาออก (x=814 px)
DEFAULT_X_RIGHT = 0.667  # ปลายขวา = ขอบถนนฝั่งขาเข้า (x=2561 px)

# ระยะที่ถือว่า "ทับเส้น" ตอนเริ่มคลิป เป็นสัดส่วนของความสูงภาพ (0.015 = 32 px ที่ 2160)
DEFAULT_START_BAND = 0.015


class LineCounter:
    """นับรถที่ข้ามเส้นแนวนอน แยกตามทิศทางและประเภท

    ทิศทาง (ในภาพ ค่า y เพิ่ม = ลงล่าง):
        "in"  = ข้ามเส้นจากบนลงล่าง (รถวิ่งเข้าหากล้อง)
        "out" = ข้ามเส้นจากล่างขึ้นบน (รถวิ่งออกจากกล้อง)
    """

    def __init__(self, width, height,
                 line_y=DEFAULT_LINE_Y, x_left=DEFAULT_X_LEFT, x_right=DEFAULT_X_RIGHT,
                 start_band=DEFAULT_START_BAND):
        # แปลงสัดส่วนเป็นพิกเซลครั้งเดียวตอนสร้าง
        self.line_y = int(line_y * height)
        self.x_left = int(x_left * width)
        self.x_right = int(x_right * width)
        self.start_band = int(start_band * height)

        self.prev_y = {}      # ตำแหน่ง y เฟรมก่อนหน้าของแต่ละ ID
        self.counted = set()  # ID ที่นับไปแล้ว กันนับซ้ำ
        self.on_line_at_start = set()  # ID ที่ทับเส้นตอนเริ่มคลิป รอดูว่าจะเคลื่อนที่ผ่านไปทางไหน
        self.counts = {"in": defaultdict(int), "out": defaultdict(int)}

    def update(self, track_id, cx, cy, class_name, clip_start=False):
        """เรียกทุกเฟรม ทุกคัน คืน "in" / "out" ถ้ารถคันนี้เพิ่งถูกนับ ไม่อย่างนั้นคืน None

        clip_start=True ใช้กับเฟรมช่วงแรกสุดของคลิป เพื่อจับรถที่ทับเส้นอยู่ตั้งแต่ต้น
        """
        direction = None
        before = self.prev_y.get(track_id)

        # นับเฉพาะรถที่จุดกึ่งกลางอยู่บนถนน (ระหว่างปลายซ้าย-ขวา) กันนับคนบนทางเท้า
        on_road = self.x_left <= cx <= self.x_right

        if before is None and clip_start and abs(cy - self.line_y) <= self.start_band:
            # เห็นครั้งแรกตอนเริ่มคลิปขณะทับเส้น ยังไม่รู้ทิศ จึงรอให้เคลื่อนที่พ้นแถบก่อน
            self.on_line_at_start.add(track_id)

        elif track_id in self.on_line_at_start:
            # นับเมื่อพ้นแถบไปแล้ว ถ้ายังจอดอยู่ในแถบ (กรอบแค่สั่น) จะไม่ถูกนับ
            if track_id not in self.counted and on_road:
                if cy > self.line_y + self.start_band:
                    direction = "in"
                elif cy < self.line_y - self.start_band:
                    direction = "out"

        elif before is not None and track_id not in self.counted and on_road:
            if before < self.line_y <= cy:
                direction = "in"
            elif before >= self.line_y > cy:
                direction = "out"

        if direction:
            # ใช้ประเภทรถ ณ ตอนข้ามเส้น ซึ่งรถใหญ่และทายคลาสได้แม่นที่สุด
            self.counts[direction][class_name] += 1
            self.counted.add(track_id)
            self.on_line_at_start.discard(track_id)

        self.prev_y[track_id] = cy
        return direction

    def total(self, direction=None):
        """จำนวนรถรวม ระบุ "in" / "out" หรือไม่ระบุเพื่อรวมทั้งสองทิศ"""
        directions = [direction] if direction else ["in", "out"]
        return sum(sum(self.counts[d].values()) for d in directions)

    def summary(self):
        """ผลนับในรูป dict ธรรมดา เช่น {"in": {"car": 3}, "out": {"motorcycle": 2}}"""
        return {d: dict(c) for d, c in self.counts.items()}


if __name__ == "__main__":
    # ทดสอบด้วยเส้นทางรถจำลอง บนภาพขนาด 3840x2160 (เส้นอยู่ที่ y=1360, x=814-2561)
    counter = LineCounter(3840, 2160)
    print("line:", counter.line_y, "x:", counter.x_left, "-", counter.x_right)

    tracks = {
        # id: (ประเภท, x, ลำดับค่า y ทีละเฟรม)
        1: ("car", 2000, [1200, 1300, 1400, 1500]),         # ลงข้ามเส้น -> in
        2: ("motorcycle", 1200, [1600, 1450, 1300, 1200]),  # ขึ้นข้ามเส้น -> out
        3: ("car", 2200, [1300, 1400, 1300, 1400]),         # ข้ามไปมา -> นับครั้งเดียว
        4: ("motorcycle", 300, [1300, 1400]),               # อยู่บนทางเท้า -> ไม่นับ
        5: ("truck", 1800, [1000, 1100, 1200]),             # ยังไม่ถึงเส้น -> ไม่นับ
        6: ("bus", 1500, [1400]),                           # เห็นแค่เฟรมเดียว -> ไม่นับ
    }

    for track_id, (cls, x, ys) in tracks.items():
        for y in ys:
            counter.update(track_id, x, y, cls)

    # รถที่ทับเส้นอยู่ตั้งแต่เฟรมแรกของคลิป (แถบทับเส้น = 1360 +- 32 px)
    start_tracks = {
        # id: (ประเภท, x, ลำดับค่า y ทีละเฟรม, เฟรมแรกอยู่ช่วงเริ่มคลิปไหม)
        7: ("car", 2000, [1370, 1380, 1400], True),         # ทับเส้นแล้ววิ่งลงไป -> in
        8: ("motorcycle", 1200, [1350, 1340, 1320], True),  # ทับเส้นแล้ววิ่งขึ้นไป -> out
        9: ("car", 2300, [1365, 1362, 1366], True),         # ทับเส้นแต่จอดนิ่ง กรอบแค่สั่น -> ไม่นับ
        10: ("car", 1900, [1370, 1380, 1400], False),       # โผล่บนเส้นกลางคลิป (เช่น ID ใหม่) -> ไม่นับ
    }

    for track_id, (cls, x, ys, at_start) in start_tracks.items():
        for i, y in enumerate(ys):
            counter.update(track_id, x, y, cls, clip_start=at_start and i == 0)

    print("summary:", counter.summary())
    print("total in:", counter.total("in"), "out:", counter.total("out"), "all:", counter.total())

    assert counter.summary() == {"in": {"car": 3}, "out": {"motorcycle": 2}}
    assert counter.total() == 5
    print("all tests passed")
