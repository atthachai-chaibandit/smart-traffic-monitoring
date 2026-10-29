"""ตรวจจับ ติดตาม และนับรถจากวิดีโอ

อ่านวิดีโอทีละเฟรม -> YOLO track -> ส่งตำแหน่งรถให้ LineCounter -> วาดผล -> บันทึกวิดีโอผลลัพธ์

รันจากโฟลเดอร์ repo:
    python -m src.detection --video data_video/cars-on-the-road-11668582.mp4
"""

import argparse
import time
from pathlib import Path

import cv2
from ultralytics import YOLO

from src.counter import DEFAULT_LINE_Y, DEFAULT_X_LEFT, DEFAULT_X_RIGHT, LineCounter

DEFAULT_MODEL = "best_r2.pt"
DEFAULT_IMGSZ = 1024     # ต้องเท่ากับตอนเทรน best_r2.pt
DEFAULT_CONF = 0.25
OUTPUT_MAX_WIDTH = 1920  # ย่อวิดีโอผลลัพธ์ วิดีโอ 4K ไฟล์ใหญ่และเปิดดูกระตุก
CLIP_START_SECONDS = 0.5 # ช่วงแรกของคลิปที่ถือว่า "เริ่มคลิป" สำหรับรถที่ทับเส้นอยู่แล้ว

# สีกรอบแต่ละประเภท (OpenCV เรียงสีเป็น B, G, R)
CLASS_COLORS = {
    "car": (255, 191, 0),
    "motorcycle": (0, 215, 255),
    "bus": (255, 0, 255),
    "truck": (0, 128, 255),
}


def draw_frame(frame, counter, detections, scale):
    """วาดเส้นนับ กรอบรถ และตัวเลขนับลงบนเฟรม"""
    thick = max(1, int(2 * scale))
    font_scale = 0.6 * scale

    cv2.line(frame, (counter.x_left, counter.line_y), (counter.x_right, counter.line_y),
             (0, 0, 255), max(2, int(4 * scale)))

    for x1, y1, x2, y2, track_id, name in detections:
        color = CLASS_COLORS.get(name, (200, 200, 200))
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, thick)
        label = f"{track_id} {name}" if track_id is not None else name
        cv2.putText(frame, label, (x1, max(0, y1 - int(6 * scale))),
                    cv2.FONT_HERSHEY_SIMPLEX, font_scale, color, thick)
        # จุดกึ่งกลางคือจุดที่ใช้ตัดสินว่าข้ามเส้นหรือยัง
        cv2.circle(frame, ((x1 + x2) // 2, (y1 + y2) // 2), max(2, int(4 * scale)), color, -1)

    # ตารางตัวเลขนับมุมซ้ายบน
    summary = counter.summary()
    lines = [f"IN {counter.total('in')}   OUT {counter.total('out')}   ALL {counter.total()}"]
    for name in CLASS_COLORS:
        lines.append(f"{name}: in {summary['in'].get(name, 0)} / out {summary['out'].get(name, 0)}")

    line_h = int(30 * scale)
    cv2.rectangle(frame, (0, 0), (int(420 * scale), line_h * len(lines) + int(15 * scale)), (0, 0, 0), -1)
    for i, text in enumerate(lines):
        cv2.putText(frame, text, (int(10 * scale), line_h * (i + 1)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8 * scale, (255, 255, 255), thick)


def process_video(video_path, model_path=DEFAULT_MODEL, output_path=None,
                  imgsz=DEFAULT_IMGSZ, conf=DEFAULT_CONF,
                  line_y=DEFAULT_LINE_Y, x_left=DEFAULT_X_LEFT, x_right=DEFAULT_X_RIGHT,
                  start=0.0, duration=None, show=False, progress_callback=None):
    """ประมวลผลวิดีโอทั้งไฟล์ (หรือช่วง start..start+duration วินาที) คืนผลนับเป็น dict

    progress_callback(เฟรมที่ทำแล้ว, เฟรมทั้งหมด) ใช้แสดงความคืบหน้า เช่นใน Streamlit
    """
    model = YOLO(model_path)
    names = model.names  # แปลงเลขคลาสเป็นชื่อ ไม่เขียนเลขคลาสตายตัวในโค้ด

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise FileNotFoundError(f"เปิดวิดีโอไม่ได้: {video_path}")

    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    start_frame = int(start * fps)
    end_frame = total_frames if duration is None else min(total_frames, start_frame + int(duration * fps))
    n_frames = end_frame - start_frame
    cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)

    counter = LineCounter(width, height, line_y=line_y, x_left=x_left, x_right=x_right)
    clip_start_frames = int(CLIP_START_SECONDS * fps)

    # ขนาดเส้นและตัวอักษรตามความกว้างภาพ (ออกแบบไว้ที่ 1920)
    scale = width / 1920
    out_w = min(width, OUTPUT_MAX_WIDTH)
    out_h = int(height * out_w / width)

    writer = None
    if output_path:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        writer = cv2.VideoWriter(str(output_path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (out_w, out_h))

    t0 = time.time()
    processed = 0
    for i in range(n_frames):
        ok, frame = cap.read()
        if not ok:
            break
        processed += 1

        # persist=True ให้ Tracker จำ ID ข้ามเฟรม ถ้าไม่ใส่จะได้ ID ใหม่ทุกเฟรม
        result = model.track(frame, persist=True, imgsz=imgsz, conf=conf, verbose=False)[0]
        boxes = result.boxes

        detections = []
        if len(boxes):
            xyxy = boxes.xyxy.int().tolist()
            classes = boxes.cls.int().tolist()
            # รถที่เพิ่งโผล่ Tracker อาจยังไม่ให้ ID วาดกรอบได้แต่ยังไม่นับ
            ids = boxes.id.int().tolist() if boxes.id is not None else [None] * len(xyxy)

            for (x1, y1, x2, y2), cls, track_id in zip(xyxy, classes, ids):
                name = names[cls]
                if track_id is not None:
                    counter.update(track_id, (x1 + x2) // 2, (y1 + y2) // 2, name,
                                   clip_start=i < clip_start_frames)
                detections.append((x1, y1, x2, y2, track_id, name))

        draw_frame(frame, counter, detections, scale)
        out_frame = cv2.resize(frame, (out_w, out_h)) if out_w != width else frame

        if writer:
            writer.write(out_frame)
        if show:
            cv2.imshow("Smart Traffic Monitoring", out_frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
        if progress_callback:
            progress_callback(i + 1, n_frames)

    cap.release()
    if writer:
        writer.release()
    if show:
        cv2.destroyAllWindows()

    return {
        "summary": counter.summary(),
        "total_in": counter.total("in"),
        "total_out": counter.total("out"),
        "total": counter.total(),
        "frames": processed,
        "seconds_processed": round(processed / fps, 2),
        "elapsed": round(time.time() - t0, 1),
        "output_path": str(output_path) if output_path else None,
    }


def print_progress(done, total, _state={"t0": None}):
    """พิมพ์ความคืบหน้าทุก 30 เฟรม พร้อมเวลาที่น่าจะเหลือ"""
    if _state["t0"] is None:
        _state["t0"] = time.time()
    if done % 30 == 0 or done == total:
        elapsed = time.time() - _state["t0"]
        eta = elapsed / done * (total - done)
        print(f"  frame {done}/{total}  ({done / total:.0%})  เหลือประมาณ {eta:.0f} วินาที")


def main():
    parser = argparse.ArgumentParser(description="นับรถที่ข้ามเส้นจากวิดีโอ")
    parser.add_argument("--video", required=True, help="path ของวิดีโอ")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--output", help="path วิดีโอผลลัพธ์ (ค่าเริ่มต้น runs/count/<ชื่อวิดีโอ>_counted.mp4)")
    parser.add_argument("--imgsz", type=int, default=DEFAULT_IMGSZ)
    parser.add_argument("--conf", type=float, default=DEFAULT_CONF)
    parser.add_argument("--start", type=float, default=0.0, help="เริ่มที่วินาทีที่")
    parser.add_argument("--duration", type=float, help="ประมวลผลกี่วินาที (ไม่ใส่ = จนจบวิดีโอ)")
    parser.add_argument("--show", action="store_true", help="แสดงหน้าต่างวิดีโอระหว่างประมวลผล")
    parser.add_argument("--manual", type=int, help="จำนวนที่คนนับได้ เพื่อคำนวณความคลาดเคลื่อน")
    args = parser.parse_args()

    output = args.output or f"runs/count/{Path(args.video).stem}_counted.mp4"
    print(f"ประมวลผล {args.video} ด้วย {args.model} (imgsz={args.imgsz})")

    result = process_video(args.video, args.model, output, imgsz=args.imgsz, conf=args.conf,
                           start=args.start, duration=args.duration, show=args.show,
                           progress_callback=print_progress)

    print("\n===== ผลการนับ =====")
    print(f"ช่วงที่ประมวลผล: {result['seconds_processed']} วินาที ({result['frames']} เฟรม)"
          f" ใช้เวลา {result['elapsed']} วินาที")
    print(f"ขาเข้า (in):  {result['total_in']}  {result['summary']['in']}")
    print(f"ขาออก (out): {result['total_out']}  {result['summary']['out']}")
    print(f"รวม: {result['total']}")
    print(f"วิดีโอผลลัพธ์: {result['output_path']}")

    if args.manual:
        error = abs(result["total"] - args.manual) / args.manual * 100
        print(f"\nคนนับได้ {args.manual} / ระบบนับได้ {result['total']}"
              f" -> คลาดเคลื่อน {error:.1f}%")


if __name__ == "__main__":
    main()
