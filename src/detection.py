"""ตรวจจับ ติดตาม และนับรถจากวิดีโอ

อ่านวิดีโอทีละเฟรม -> YOLO track -> ส่งตำแหน่งรถให้ LineCounter -> วาดผล -> บันทึกวิดีโอผลลัพธ์

รันจากโฟลเดอร์ repo:
    python -m src.detection --video data_video/cars-on-the-road-11668582.mp4
"""

import argparse
import subprocess
import time
from pathlib import Path

import cv2
from ultralytics import YOLO

from src.counter import DEFAULT_LINE_Y, DEFAULT_X_LEFT, DEFAULT_X_RIGHT, LineCounter
from src.preprocessing import DEFAULT_ROI_POLYGON, Preprocessor

DEFAULT_MODEL = "best_r2.pt"
DEFAULT_IMGSZ = 1024     # ต้องเท่ากับตอนเทรน best_r2.pt
DEFAULT_CONF = 0.25
OUTPUT_MAX_WIDTH = 1920  # ย่อวิดีโอผลลัพธ์ วิดีโอ 4K ไฟล์ใหญ่และเปิดดูกระตุก
PREVIEW_WIDTH = 960      # ขนาดภาพสดที่ส่งให้แอป ย่อให้เล็กเพื่อส่งไปเว็บได้เร็ว
CLIP_START_SECONDS = 0.5 # ช่วงแรกของคลิปที่ถือว่า "เริ่มคลิป" สำหรับรถที่ทับเส้นอยู่แล้ว
FLASH_SECONDS = 0.3      # เส้นนับกะพริบเป็นสีเขียวนานเท่านี้หลังนับรถได้

# ตำแหน่งเส้นนับและ ROI แยกตามวิดีโอ เลือกจากชื่อไฟล์ (ไม่รวมนามสกุล)
# วิดีโอที่ไม่อยู่ในรายการจะใช้ค่าของ cars-on-the-road
DEFAULT_PRESET = "cars-on-the-road-11668582"
VIDEO_PRESETS = {
    # 3840x2160 แนวนอน ถนนสองทิศทาง
    "cars-on-the-road-11668582": {
        "line_y": DEFAULT_LINE_Y, "x_left": DEFAULT_X_LEFT, "x_right": DEFAULT_X_RIGHT,
        "roi_polygon": DEFAULT_ROI_POLYGON,
    },
    # 2160x3840 แนวตั้ง กลางคืน วัดจากภาพ 504x898: (8,758) ถึง (513,758)
    # ปลายขวาเลยขอบภาพไป จึงใช้ 1.0 (ขอบขวาสุด)
    "vibrant-night-traffic-in-urban-thailand-29900216": {
        "line_y": 0.844, "x_left": 0.016, "x_right": 1.0,
        "roi_polygon": None,  # ยังไม่ได้วาดรูปถนนของวิดีโอนี้ จึงเปิด ROI ไม่ได้
    },
    # 3840x2160 แนวนอน กลางคืนมืดจริง ใช้ทดสอบ CLAHE
    # วัดจากภาพ 2557x1437: (788,1181) ถึง (2413,1181)
    "night-traffic-on-city-highway-38928325": {
        "line_y": 0.822, "x_left": 0.308, "x_right": 0.944,
        "roi_polygon": None,
    },
}


def get_preset(video_path):
    """ค่าตั้งต้นของเส้นนับและ ROI สำหรับวิดีโอนี้"""
    return VIDEO_PRESETS.get(Path(video_path).stem, VIDEO_PRESETS[DEFAULT_PRESET])


def preset_line_points(preset):
    """เส้นนับของ preset ในรูปจุดปลายสองข้าง (สัดส่วนของภาพ)"""
    return (preset["x_left"], preset["line_y"]), (preset["x_right"], preset["line_y"])


# สีกรอบแต่ละประเภท (OpenCV เรียงสีเป็น B, G, R)
CLASS_COLORS = {
    "car": (246, 130, 59),
    "motorcycle": (11, 158, 245),
    "bus": (247, 85, 168),
    "truck": (68, 68, 239),
}
LINE_COLOR = (60, 60, 255)
FLASH_COLOR = (80, 220, 80)
COUNTED_COLOR = (80, 220, 80)


def draw_label(frame, text, x, y, color, scale):
    """ป้ายชื่อแบบมีพื้นหลังสี ตัวอักษรสีขาว วางเหนือมุมซ้ายบนของกรอบ"""
    font_scale = 0.55 * scale
    thick = max(1, int(1.5 * scale))
    (tw, th), base = cv2.getTextSize(text, cv2.FONT_HERSHEY_DUPLEX, font_scale, thick)
    pad = int(5 * scale)
    top = max(0, y - th - base - 2 * pad)
    cv2.rectangle(frame, (x, top), (x + tw + 2 * pad, y), color, -1)
    cv2.putText(frame, text, (x + pad, y - base - pad // 2), cv2.FONT_HERSHEY_DUPLEX,
                font_scale, (255, 255, 255), thick, cv2.LINE_AA)


def draw_panel(frame, counter, preprocessor, scale):
    """แผงตัวเลขนับโปร่งแสงมุมซ้ายบน"""
    summary = counter.summary()
    rows = [(f"IN {counter.total('in')}   OUT {counter.total('out')}   ALL {counter.total()}", None)]
    for name, color in CLASS_COLORS.items():
        rows.append((f"{name}: in {summary['in'].get(name, 0)} / out {summary['out'].get(name, 0)}", color))
    rows.append((f"image processing: {preprocessor.name()}", None))

    line_h = int(32 * scale)
    pad = int(14 * scale)
    w = int(430 * scale)
    h = line_h * len(rows) + pad
    overlay = frame.copy()
    cv2.rectangle(overlay, (pad, pad), (pad + w, pad + h), (20, 20, 20), -1)
    cv2.addWeighted(overlay, 0.65, frame, 0.35, 0, frame)

    for i, (text, color) in enumerate(rows):
        y = pad + line_h * (i + 1)
        x = pad + int(14 * scale)
        if color:
            cv2.circle(frame, (x + int(6 * scale), y - int(8 * scale)), int(7 * scale), color, -1)
            x += int(22 * scale)
        size = 0.75 if i == 0 else 0.6
        cv2.putText(frame, text, (x, y), cv2.FONT_HERSHEY_DUPLEX, size * scale,
                    (255, 255, 255), max(1, int(1.5 * scale)), cv2.LINE_AA)


def draw_frame(frame, counter, detections, scale, preprocessor, flash=False):
    """วาดขอบ ROI เส้นนับ กรอบรถ และแผงตัวเลขลงบนเฟรมที่ใช้แสดงผล"""
    thick = max(2, int(2 * scale))

    for outline in preprocessor.outlines if preprocessor.use_roi else []:
        cv2.polylines(frame, [outline], True, (200, 200, 200), max(1, int(1.5 * scale)), cv2.LINE_AA)

    line_color = FLASH_COLOR if flash else LINE_COLOR
    cv2.line(frame, counter.p1, counter.p2, line_color, max(3, int(5 * scale)), cv2.LINE_AA)
    for p in (counter.p1, counter.p2):
        cv2.circle(frame, p, max(4, int(8 * scale)), line_color, -1, cv2.LINE_AA)

    for x1, y1, x2, y2, track_id, name in detections:
        color = CLASS_COLORS.get(name, (200, 200, 200))
        counted = track_id in counter.counted
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, thick + (1 if counted else 0), cv2.LINE_AA)
        label = f"{name} #{track_id}" if track_id is not None else name
        draw_label(frame, label, x1, y1, color, scale)
        # จุดกึ่งกลางคือจุดที่ใช้ตัดสินว่าข้ามเส้นหรือยัง รถที่นับแล้วเป็นจุดสีเขียว
        center = ((x1 + x2) // 2, (y1 + y2) // 2)
        cv2.circle(frame, center, max(3, int(5 * scale)), COUNTED_COLOR if counted else color, -1, cv2.LINE_AA)

    draw_panel(frame, counter, preprocessor, scale)


def resolve_device(device):
    """'gpu' -> 0 (การ์ดจอตัวแรก), 'cpu' -> 'cpu', None -> ให้ Ultralytics เลือกเอง"""
    if device == "gpu":
        return 0
    return device


def process_video(video_path, model_path=DEFAULT_MODEL, output_path=None,
                  imgsz=DEFAULT_IMGSZ, conf=DEFAULT_CONF,
                  line_points=None, line_y=None, x_left=None, x_right=None,
                  start=0.0, duration=None, show=False, progress_callback=None,
                  use_clahe=False, use_roi=False, exclude_polygons=(),
                  device=None, preview_callback=None, preview_every=5):
    """ประมวลผลวิดีโอทั้งไฟล์ (หรือช่วง start..start+duration วินาที) คืนผลนับเป็น dict

    line_points = ((x1, y1), (x2, y2)) เส้นนับเป็นสัดส่วนของภาพ (ไม่ใส่ = ใช้ VIDEO_PRESETS)
    exclude_polygons = พื้นที่ที่ผู้ใช้วาดให้โมเดลไม่สนใจ (ใช้เมื่อ use_roi=True)
    device = "gpu" / "cpu" / None
    progress_callback(เฟรมที่ทำแล้ว, เฟรมทั้งหมด) ใช้แสดงความคืบหน้า
    preview_callback(ภาพ RGB ย่อแล้ว, ผลนับ) เรียกทุก preview_every เฟรม ใช้แสดงภาพสดในแอป
    """
    preset = get_preset(video_path)
    if line_points is None:
        p1, p2 = preset_line_points(preset)
        if line_y is not None or x_left is not None or x_right is not None:
            ly = p1[1] if line_y is None else line_y
            p1 = (p1[0] if x_left is None else x_left, ly)
            p2 = (p2[0] if x_right is None else x_right, ly)
        line_points = (p1, p2)

    # ROI: ถ้าผู้ใช้วาดพื้นที่เองให้ดูทั้งภาพแล้วถมเฉพาะส่วนที่วาด ไม่อย่างนั้นใช้รูปถนนของ preset
    roi_polygon = None if exclude_polygons else preset["roi_polygon"]
    if use_roi and not exclude_polygons and roi_polygon is None:
        print("คำเตือน: วิดีโอนี้ยังไม่มีรูปถนนสำหรับ ROI จึงปิด ROI")
        use_roi = False

    model = YOLO(model_path)
    names = model.names  # แปลงเลขคลาสเป็นชื่อ ไม่เขียนเลขคลาสตายตัวในโค้ด
    device = resolve_device(device)

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

    counter = LineCounter(width, height, p1=line_points[0], p2=line_points[1])
    preprocessor = Preprocessor(width, height, use_clahe=use_clahe, use_roi=use_roi,
                                roi_polygon=roi_polygon, exclude_polygons=exclude_polygons)
    clip_start_frames = int(CLIP_START_SECONDS * fps)
    flash_frames = int(FLASH_SECONDS * fps)

    # ขนาดเส้นและตัวอักษรตามด้านที่สั้นของภาพ (ออกแบบไว้ที่ 1080) ใช้ได้ทั้งวิดีโอแนวนอนและแนวตั้ง
    scale = min(width, height) / 1080
    out_w = min(width, OUTPUT_MAX_WIDTH)
    out_h = int(height * out_w / width)

    writer = None
    if output_path:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        writer = cv2.VideoWriter(str(output_path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (out_w, out_h))

    window = "Smart Traffic Monitoring"
    if show:
        # หน้าต่างย่อขยายได้ เริ่มให้พอดีกรอบ 1280x720 เพราะภาพ 1920 (หรือวิดีโอแนวตั้ง) ใหญ่เกินจอ
        cv2.namedWindow(window, cv2.WINDOW_NORMAL)
        fit = min(1280 / out_w, 720 / out_h)
        cv2.resizeWindow(window, int(out_w * fit), int(out_h * fit))

    events = []  # (วินาทีในวิดีโอ, ทิศทาง, ประเภท) ของรถแต่ละคันที่ถูกนับ ใช้ทำกราฟในแอป
    last_count_frame = -flash_frames - 1
    t0 = time.time()
    processed = 0
    for i in range(n_frames):
        ok, frame = cap.read()
        if not ok:
            break
        processed += 1

        # Image Processing: โมเดลได้ภาพที่พื้นที่ไม่สนใจเป็นสีดำทึบ ส่วนภาพแสดงผลมืดลงแบบโปร่งแสง
        enhanced = preprocessor.enhance(frame)
        model_input = preprocessor.for_model(enhanced)

        # persist=True ให้ Tracker จำ ID ข้ามเฟรม ถ้าไม่ใส่จะได้ ID ใหม่ทุกเฟรม
        result = model.track(model_input, persist=True, imgsz=imgsz, conf=conf,
                             device=device, verbose=False)[0]
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
                    direction = counter.update(track_id, (x1 + x2) // 2, (y1 + y2) // 2, name,
                                               clip_start=i < clip_start_frames)
                    if direction:
                        events.append((round((start_frame + i) / fps, 2), direction, name))
                        last_count_frame = i
                detections.append((x1, y1, x2, y2, track_id, name))

        display = preprocessor.for_display(enhanced)
        draw_frame(display, counter, detections, scale, preprocessor,
                   flash=i - last_count_frame <= flash_frames)
        out_frame = cv2.resize(display, (out_w, out_h)) if out_w != width else display

        if writer:
            writer.write(out_frame)
        if show:
            cv2.imshow(window, out_frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
        if progress_callback:
            progress_callback(i + 1, n_frames)
        if preview_callback and (i % preview_every == 0 or i == n_frames - 1):
            pw = min(PREVIEW_WIDTH, out_w)
            preview = cv2.resize(out_frame, (pw, int(out_h * pw / out_w)))
            preview_callback(cv2.cvtColor(preview, cv2.COLOR_BGR2RGB), counter.summary())

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
        "events": events,
        "frames": processed,
        "fps": fps,
        "seconds_processed": round(processed / fps, 2),
        "elapsed": round(time.time() - t0, 1),
        "preprocess": preprocessor.name(),
        "output_path": str(output_path) if output_path else None,
    }


def to_browser_video(src, dst):
    """แปลงวิดีโอ mp4v (ที่ OpenCV เขียน) เป็น H.264 เพื่อให้เบราว์เซอร์เล่นได้ ใช้ ffmpeg จาก imageio-ffmpeg"""
    import imageio_ffmpeg

    cmd = [imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error", "-i", str(src),
           "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "veryfast", "-movflags", "+faststart",
           str(dst)]
    subprocess.run(cmd, check=True)
    return str(dst)


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
    parser.add_argument("--output", help="path วิดีโอผลลัพธ์ (ค่าเริ่มต้น runs/count/<ชื่อวิดีโอ>_<โหมด>.mp4)")
    parser.add_argument("--imgsz", type=int, default=DEFAULT_IMGSZ)
    parser.add_argument("--conf", type=float, default=DEFAULT_CONF)
    parser.add_argument("--start", type=float, default=0.0, help="เริ่มที่วินาทีที่")
    parser.add_argument("--duration", type=float, help="ประมวลผลกี่วินาที (ไม่ใส่ = จนจบวิดีโอ)")
    parser.add_argument("--show", action="store_true", help="แสดงหน้าต่างวิดีโอระหว่างประมวลผล")
    parser.add_argument("--manual", type=int, help="จำนวนที่คนนับได้ เพื่อคำนวณความคลาดเคลื่อน")
    parser.add_argument("--clahe", action="store_true", help="เปิด CLAHE เพิ่มความคมชัดภาพมืด")
    parser.add_argument("--roi", action="store_true", help="เปิด ROI Mask ตรวจจับเฉพาะพื้นที่ถนน")
    parser.add_argument("--device", choices=["gpu", "cpu"], help="บังคับใช้ GPU หรือ CPU (ไม่ใส่ = เลือกเอง)")
    args = parser.parse_args()

    if args.roi and get_preset(args.video)["roi_polygon"] is None:
        print("คำเตือน: วิดีโอนี้ยังไม่มีรูปถนนสำหรับ ROI จึงปิด ROI")
        args.roi = False

    mode = "_".join(p for p, on in (("clahe", args.clahe), ("roi", args.roi)) if on) or "none"
    output = args.output or f"runs/count/{Path(args.video).stem}_{mode}.mp4"
    print(f"ประมวลผล {args.video} ด้วย {args.model} (imgsz={args.imgsz}, preprocess={mode})")

    result = process_video(args.video, args.model, output, imgsz=args.imgsz, conf=args.conf,
                           start=args.start, duration=args.duration, show=args.show,
                           progress_callback=print_progress,
                           use_clahe=args.clahe, use_roi=args.roi, device=args.device)

    print("\n===== ผลการนับ =====")
    print(f"Image Processing: {result['preprocess']}")
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
