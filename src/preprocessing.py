"""Image Processing ก่อนส่งภาพให้ YOLO

1) CLAHE  - เพิ่มความคมชัดในส่วนมืด (เช่น วิดีโอกลางคืน) โดยไม่ทำให้ไฟหน้ารถจ้าขึ้น
2) ROI Mask - ทำให้พื้นที่นอกถนนเป็นสีดำ กันไม่ให้ตรวจจับคนบนทางเท้า

ทั้งสองแบบเปิด/ปิดได้ใน src/detection.py (--clahe / --roi) เพื่อทดลองเทียบผล
"""

import cv2
import numpy as np

# CLAHE: clip_limit ยิ่งสูง ความคมชัดยิ่งเพิ่ม แต่ Noise ก็เพิ่มด้วย, tile = จำนวนช่องที่แบ่งภาพ
DEFAULT_CLIP_LIMIT = 2.0
DEFAULT_TILE_GRID = (8, 8)

# ROI: จุดมุมของพื้นที่ถนน เป็นสัดส่วนของภาพ (x, y) เรียงตามเข็มนาฬิกา
# เลือกจากวิดีโอ cars-on-the-road-11668582.mp4 ให้ครอบถนนทั้งสองทิศ ไม่รวมทางเท้า
DEFAULT_ROI_POLYGON = [
    (0.000, 0.770),  # ซ้ายล่าง ตามแนวรั้วเขียวฝั่งซ้าย
    (0.478, 0.423),  # ซ้ายบน (ไกลกล้อง)
    (0.572, 0.423),  # ขวาบน (ไกลกล้อง)
    (0.768, 0.758),  # ตามแนวรั้วเขียวฝั่งขวา
    (0.842, 1.000),  # ขวาล่าง
    (0.000, 1.000),  # มุมซ้ายล่างของภาพ
]


def apply_clahe(frame, clip_limit=DEFAULT_CLIP_LIMIT, tile_grid=DEFAULT_TILE_GRID):
    """เพิ่มความคมชัดแบบ CLAHE โดยปรับเฉพาะช่องความสว่าง สีจึงไม่เพี้ยน

    แปลง BGR -> LAB (L = ความสว่าง, A/B = สี) แล้วทำ CLAHE กับ L อย่างเดียว
    ถ้าทำกับ B, G, R แยกกันทีละช่อง สีของภาพจะเพี้ยน
    """
    lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=tile_grid)
    l = clahe.apply(l)
    return cv2.cvtColor(cv2.merge((l, a, b)), cv2.COLOR_LAB2BGR)


def roi_points(width, height, polygon=DEFAULT_ROI_POLYGON):
    """จุดมุม ROI เป็นพิกเซล สำหรับวาดเส้นขอบบนภาพ"""
    return np.array([(int(x * width), int(y * height)) for x, y in polygon], dtype=np.int32)


def make_roi_mask(width, height, polygon=DEFAULT_ROI_POLYGON, exclude_polygons=()):
    """สร้างหน้ากากขาวดำขนาดเท่าภาพ: พื้นที่ที่ให้โมเดลดู = 255 (ขาว), พื้นที่ที่ไม่สนใจ = 0 (ดำ)

    polygon = พื้นที่ถนนที่ให้ดู (None = ดูทั้งภาพ)
    exclude_polygons = พื้นที่ที่ผู้ใช้วาดให้ไม่สนใจ (ถมดำทับ) วาดได้หลายพื้นที่
    """
    if polygon is None:
        mask = np.full((height, width), 255, dtype=np.uint8)
    else:
        mask = np.zeros((height, width), dtype=np.uint8)
        cv2.fillPoly(mask, [roi_points(width, height, polygon)], 255)
    for poly in exclude_polygons:
        cv2.fillPoly(mask, [roi_points(width, height, poly)], 0)
    return mask


def apply_roi(frame, mask):
    """เก็บเฉพาะพิกเซลในพื้นที่ที่ให้ดู ส่วนอื่นกลายเป็นสีดำ (bitwise AND กับหน้ากาก)"""
    return cv2.bitwise_and(frame, frame, mask=mask)


def shade_outside(frame, mask, strength=0.6):
    """ทำให้พื้นที่ที่ไม่สนใจมืดลงแบบโปร่งแสง ใช้แสดงผลให้คนดู (โมเดลยังได้ภาพดำทึบ)"""
    shaded = frame.copy()
    outside = mask == 0
    shaded[outside] = (frame[outside] * (1 - strength)).astype(np.uint8)
    return shaded


def mean_brightness(frame):
    """ค่าความสว่างเฉลี่ย (ช่อง L ของ LAB, 0-255) ใช้แนะนำว่าควรเปิด CLAHE ไหม"""
    return float(cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)[:, :, 0].mean())


class Preprocessor:
    """รวมขั้นตอน Image Processing ที่เปิด/ปิดได้ สร้างครั้งเดียวต่อวิดีโอ"""

    def __init__(self, width, height, use_clahe=False, use_roi=False,
                 clip_limit=DEFAULT_CLIP_LIMIT, roi_polygon=DEFAULT_ROI_POLYGON, exclude_polygons=()):
        self.use_clahe = use_clahe
        self.use_roi = use_roi
        self.clip_limit = clip_limit
        # หน้ากากสร้างครั้งเดียว ใช้ซ้ำทุกเฟรม เพราะกล้องไม่ขยับ
        self.mask = make_roi_mask(width, height, roi_polygon, exclude_polygons) if use_roi else None
        polygons = ([roi_polygon] if roi_polygon is not None else []) + list(exclude_polygons)
        self.outlines = [roi_points(width, height, p) for p in polygons]

    def enhance(self, frame):
        """ขั้นปรับภาพ (CLAHE) ใช้ทั้งกับภาพที่ส่งให้โมเดลและภาพที่แสดงผล"""
        if self.use_clahe:
            frame = apply_clahe(frame, clip_limit=self.clip_limit)
        return frame

    def for_model(self, enhanced):
        """ภาพที่ส่งให้ YOLO: พื้นที่ที่ไม่สนใจเป็นสีดำทึบ"""
        return apply_roi(enhanced, self.mask) if self.use_roi else enhanced

    def for_display(self, enhanced):
        """ภาพที่แสดงให้คนดู: พื้นที่ที่ไม่สนใจมืดลงแบบโปร่งแสง ยังเห็นถนนด้านหลัง"""
        return shade_outside(enhanced, self.mask) if self.use_roi else enhanced.copy()

    def __call__(self, frame):
        return self.for_model(self.enhance(frame))

    def name(self):
        """ชื่อโหมดสำหรับตั้งชื่อไฟล์ผลลัพธ์ เช่น "clahe_roi" หรือ "none" """
        parts = [p for p, on in (("clahe", self.use_clahe), ("roi", self.use_roi)) if on]
        return "_".join(parts) or "none"


if __name__ == "__main__":
    # สร้างภาพก่อน-หลังจากเฟรมของวิดีโอ ใช้ตรวจตำแหน่ง ROI และดูผล CLAHE
    #   python -m src.preprocessing --video data_video/cars-on-the-road-11668582.mp4 --second 5
    import argparse
    from pathlib import Path

    parser = argparse.ArgumentParser(description="สร้างภาพก่อน-หลัง CLAHE และ ROI")
    parser.add_argument("--video", required=True)
    parser.add_argument("--second", type=float, default=5.0, help="ดึงเฟรมที่วินาทีที่")
    parser.add_argument("--outdir", default="images/preprocessing")
    args = parser.parse_args()

    cap = cv2.VideoCapture(args.video)
    cap.set(cv2.CAP_PROP_POS_MSEC, args.second * 1000)
    ok, frame = cap.read()
    cap.release()
    if not ok:
        raise SystemExit(f"อ่านเฟรมจาก {args.video} ไม่ได้")

    h, w = frame.shape[:2]
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    stem = Path(args.video).stem

    roi_outline = frame.copy()
    cv2.polylines(roi_outline, [roi_points(w, h)], True, (0, 255, 0), max(2, w // 640))

    outputs = {
        "original": frame,
        "clahe": apply_clahe(frame),
        "roi_outline": roi_outline,
        "roi": apply_roi(frame, make_roi_mask(w, h)),
    }
    for name, img in outputs.items():
        # ย่อเหลือกว้าง 1920 ให้ไฟล์ไม่ใหญ่เกินไปสำหรับใส่รายงาน
        small = cv2.resize(img, (1920, int(h * 1920 / w))) if w > 1920 else img
        path = outdir / f"{stem}_{name}.jpg"
        cv2.imwrite(str(path), small)
        print("saved", path)
