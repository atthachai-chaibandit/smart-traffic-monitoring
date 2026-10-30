"""ตรรกะนับรถที่ข้ามเส้นนับ

ไฟล์นี้ไม่ขึ้นกับ YOLO รับแค่ ID, ตำแหน่ง และประเภทของรถในแต่ละเฟรม
จึงทดสอบได้ด้วยข้อมูลจำลอง (ดูส่วนท้ายไฟล์)

เส้นนับเป็นเส้นตรงระหว่างจุด p1 กับ p2 จะเอียงก็ได้ (ผู้ใช้วาดเองในแอป)
ใช้ "ฝั่ง" ของจุดเทียบกับเส้น (cross product) ตัดสินว่ารถข้ามเส้นหรือยัง
ถ้าเส้นเป็นแนวนอน ผลจะเหมือนการเทียบค่า y ตรง ๆ
"""

import math
from collections import defaultdict

# ตำแหน่งเส้นนับ เก็บเป็นสัดส่วนของภาพ (0-1) จึงใช้กับวิดีโอทุกขนาดได้
# ค่าตั้งต้นเลือกจากวิดีโอ cars-on-the-road-11668582.mp4 (3840x2160)
DEFAULT_LINE_Y = 0.630   # ความสูงของเส้น (y=1361 px)
DEFAULT_X_LEFT = 0.212   # ปลายซ้าย = ขอบถนนฝั่งขาออก (x=814 px)
DEFAULT_X_RIGHT = 0.667  # ปลายขวา = ขอบถนนฝั่งขาเข้า (x=2561 px)

# ระยะที่ถือว่า "ทับเส้น" ตอนเริ่มคลิป เป็นสัดส่วนของความสูงภาพ (0.015 = 32 px ที่ 2160)
DEFAULT_START_BAND = 0.015

# เงื่อนไขของเส้นที่ผู้ใช้วาด
MAX_LINE_ANGLE = 30.0    # องศา เส้นชันกว่านี้แยกขาเข้า/ขาออกไม่ชัด
MIN_LINE_LENGTH = 0.10   # สัดส่วนของความกว้างภาพ


def validate_line(p1, p2, width, height):
    """ตรวจเส้นที่ผู้ใช้วาด (จุดเป็นพิกเซล) คืนข้อความปัญหา หรือ None ถ้าใช้ได้"""
    dx, dy = p2[0] - p1[0], p2[1] - p1[1]
    if math.hypot(dx, dy) < MIN_LINE_LENGTH * width:
        return f"เส้นสั้นเกินไป ต้องยาวอย่างน้อย {MIN_LINE_LENGTH:.0%} ของความกว้างภาพ"
    angle = abs(math.degrees(math.atan2(dy, dx)))
    angle = min(angle, 180 - angle)  # มุมเทียบแนวนอน 0-90 องศา
    if angle > MAX_LINE_ANGLE:
        return f"เส้นเอียง {angle:.0f}° เกิน {MAX_LINE_ANGLE:.0f}° แยกขาเข้า/ขาออกไม่ชัด ลองวาดให้แนวนอนขึ้น"
    return None


class LineCounter:
    """นับรถที่ข้ามเส้น แยกตามทิศทางและประเภท

    ทิศทาง (ในภาพ ค่า y เพิ่ม = ลงล่าง):
        "in"  = ข้ามเส้นจากด้านบนลงด้านล่าง (รถวิ่งเข้าหากล้อง)
        "out" = ข้ามเส้นจากด้านล่างขึ้นด้านบน (รถวิ่งออกจากกล้อง)

    กำหนดเส้นได้ 2 แบบ (เป็นสัดส่วนของภาพ):
        - p1, p2 = จุดปลายสองข้าง (เส้นเอียงได้)
        - line_y, x_left, x_right = เส้นแนวนอน (ใช้เมื่อไม่ใส่ p1, p2)
    """

    def __init__(self, width, height,
                 line_y=DEFAULT_LINE_Y, x_left=DEFAULT_X_LEFT, x_right=DEFAULT_X_RIGHT,
                 start_band=DEFAULT_START_BAND, p1=None, p2=None):
        if p1 is None or p2 is None:
            p1, p2 = (x_left, line_y), (x_right, line_y)

        # แปลงสัดส่วนเป็นพิกเซลครั้งเดียวตอนสร้าง และให้ p1 อยู่ซ้ายเสมอ ทิศ in/out จึงไม่กลับด้าน
        a = (int(p1[0] * width), int(p1[1] * height))
        b = (int(p2[0] * width), int(p2[1] * height))
        self.p1, self.p2 = (a, b) if a[0] <= b[0] else (b, a)

        self._dx = self.p2[0] - self.p1[0]
        self._dy = self.p2[1] - self.p1[1]
        self._length = math.hypot(self._dx, self._dy) or 1.0
        self.start_band = int(start_band * height)

        self.prev_side = {}   # ระยะ (มีเครื่องหมาย) จากเส้นในเฟรมก่อนหน้าของแต่ละ ID
        self.counted = set()  # ID ที่นับไปแล้ว กันนับซ้ำ
        self.on_line_at_start = set()  # ID ที่ทับเส้นตอนเริ่มคลิป รอดูว่าจะเคลื่อนที่ผ่านไปทางไหน
        self.counts = {"in": defaultdict(int), "out": defaultdict(int)}

    def _side(self, cx, cy):
        """ระยะจากเส้นเป็นพิกเซล: ติดลบ = เหนือเส้น, บวก = ใต้เส้น"""
        return (self._dx * (cy - self.p1[1]) - self._dy * (cx - self.p1[0])) / self._length

    def _within_segment(self, cx, cy):
        """จุดอยู่ในช่วงความยาวของเส้นไหม (ไม่เลยปลายสองข้าง) กันนับคนบนทางเท้า"""
        t = ((cx - self.p1[0]) * self._dx + (cy - self.p1[1]) * self._dy) / (self._length ** 2)
        return 0.0 <= t <= 1.0

    def update(self, track_id, cx, cy, class_name, clip_start=False):
        """เรียกทุกเฟรม ทุกคัน คืน "in" / "out" ถ้ารถคันนี้เพิ่งถูกนับ ไม่อย่างนั้นคืน None

        clip_start=True ใช้กับเฟรมช่วงแรกสุดของคลิป เพื่อจับรถที่ทับเส้นอยู่ตั้งแต่ต้น
        """
        direction = None
        side = self._side(cx, cy)
        before = self.prev_side.get(track_id)
        on_segment = self._within_segment(cx, cy)

        if before is None and clip_start and abs(side) <= self.start_band:
            # เห็นครั้งแรกตอนเริ่มคลิปขณะทับเส้น ยังไม่รู้ทิศ จึงรอให้เคลื่อนที่พ้นแถบก่อน
            self.on_line_at_start.add(track_id)

        elif track_id in self.on_line_at_start:
            # นับเมื่อพ้นแถบไปแล้ว ถ้ายังจอดอยู่ในแถบ (กรอบแค่สั่น) จะไม่ถูกนับ
            if track_id not in self.counted and on_segment:
                if side > self.start_band:
                    direction = "in"
                elif side < -self.start_band:
                    direction = "out"

        elif before is not None and track_id not in self.counted and on_segment:
            if before < 0 <= side:
                direction = "in"
            elif before >= 0 > side:
                direction = "out"

        if direction:
            # ใช้ประเภทรถ ณ ตอนข้ามเส้น ซึ่งรถใหญ่และทายคลาสได้แม่นที่สุด
            self.counts[direction][class_name] += 1
            self.counted.add(track_id)
            self.on_line_at_start.discard(track_id)

        self.prev_side[track_id] = side
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
    print("line:", counter.p1, "->", counter.p2)

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

    # เส้นเอียง: จาก (1000,1200) ถึง (3000,1600) รถวิ่งลงตามแนวตั้งที่ x=2000 (เส้นอยู่ที่ y=1400)
    tilted = LineCounter(3840, 2160, p1=(3000 / 3840, 1600 / 2160), p2=(1000 / 3840, 1200 / 2160))
    for y in [1300, 1380, 1420, 1500]:
        tilted.update(1, 2000, y, "car")      # ลงข้ามเส้นเอียง -> in
    for y in [1500, 1420, 1380, 1300]:
        tilted.update(2, 2500, y, "truck")    # x=2500 เส้นอยู่ที่ y=1500 จึงเริ่มบนเส้นพอดีแล้วขึ้น -> out
    for y in [1300, 1500]:
        tilted.update(3, 3500, y, "car")      # เลยปลายเส้นไปแล้ว -> ไม่นับ
    print("tilted summary:", tilted.summary())
    assert tilted.summary() == {"in": {"car": 1}, "out": {"truck": 1}}

    # ตรวจเงื่อนไขเส้นที่ผู้ใช้วาด
    assert validate_line((0, 1000), (3840, 1100), 3840, 2160) is None   # เอียงนิดหน่อย ใช้ได้
    assert validate_line((0, 0), (1000, 1000), 3840, 2160) is not None  # เอียง 45° เกิน
    assert validate_line((0, 0), (100, 0), 3840, 2160) is not None      # สั้นเกินไป
    print("all tests passed")
