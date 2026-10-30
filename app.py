"""Smart Traffic Monitoring - เว็บแอปนับรถจากวิดีโอ

รันจากโฟลเดอร์ repo:
    streamlit run app.py

ขั้นตอนในแอป: เลือกวิดีโอ -> วาดเส้นนับและพื้นที่ไม่สนใจ (ROI) บนภาพ -> ประมวลผล -> ดูผลลัพธ์และสถิติ
"""

import base64
import time
from pathlib import Path

import cv2
import pandas as pd
import streamlit as st
import torch

from src.counter import validate_line
from src.detection import (CLASS_COLORS, DEFAULT_CONF, DEFAULT_MODEL, VIDEO_PRESETS, get_preset,
                           preset_line_points, process_video, to_browser_video)
from src.preprocessing import mean_brightness

ROOT = Path(__file__).parent
SAMPLE_DIR = ROOT / "data_video"
WORK_DIR = ROOT / "runs" / "app"
VIDEO_TYPES = ["mp4", "mov", "avi", "mkv"]
DARK_THRESHOLD = 80   # ความสว่างเฉลี่ย (0-255) ต่ำกว่านี้ถือว่าวิดีโอมืด แนะนำให้เปิด CLAHE
SNAP_MARGIN = 0.02    # คลิกห่างขอบภาพไม่เกิน 2% จะดูดติดขอบ ถมพื้นที่ได้ถึงขอบพอดี
SETUP_MAX_W, SETUP_MAX_H = 960, 640  # ขนาดภาพสำหรับวาด
ROI_POINTS = 4        # คลิกครบ 4 จุด ระบบปิดเป็นพื้นที่ (object) ให้อัตโนมัติ
RESIZE_STEP = 0.10    # ปุ่มขยาย/ย่อ ครั้งละ 10%

# ตัววาดเส้นนับ/พื้นที่บน <canvas> เขียนด้วย JavaScript ให้เบราว์เซอร์วาดตามเมาส์ทันทีระหว่างลาก
# (ถ้าให้ Python วาดภาพใหม่ทุกครั้ง จะเห็นผลหลังปล่อยเมาส์เท่านั้น) ใช้ Streamlit components v2
ROI_EDITOR = st.components.v2.component(
    "roi_editor",
    html="<canvas></canvas>",
    css="canvas {width: 100%; height: auto; display: block; border-radius: 8px; touch-action: none;}",
    js=(ROOT / "src" / "roi_editor.js").read_text(encoding="utf-8"),
)

st.set_page_config(page_title="Smart Traffic Monitoring", page_icon="🚦", layout="wide")

st.markdown("""
<style>
.block-container {padding-top: 2rem;}
.hero {padding: 1.2rem 1.5rem; border-radius: 16px; margin-bottom: 1rem;
       background: linear-gradient(135deg, #1E3A8A 0%, #0F172A 70%); border: 1px solid #334155;}
.hero h1 {margin: 0; font-size: 2rem;}
.hero p {margin: .3rem 0 0; color: #CBD5E1;}
.step {font-size: 1.15rem; font-weight: 700; margin: 1.2rem 0 .4rem;}
.legend span {display: inline-block; padding: 2px 10px; margin: 2px; border-radius: 999px;
              color: white; font-size: .85rem;}
</style>
""", unsafe_allow_html=True)


# ---------- ตัวช่วย ----------

def bgr_to_hex(bgr):
    b, g, r = bgr
    return f"#{r:02X}{g:02X}{b:02X}"


@st.cache_data(max_entries=16)
def video_info(path, file_size):
    """file_size ใส่ไว้ให้ cache รู้ว่าไฟล์ชื่อเดิมถูกเปลี่ยนเนื้อหา (อัปโหลดทับ)"""
    cap = cv2.VideoCapture(str(path))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    info = {"width": int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
            "height": int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
            "fps": fps, "frames": int(cap.get(cv2.CAP_PROP_FRAME_COUNT))}
    cap.release()
    info["duration"] = info["frames"] / fps
    return info


@st.cache_data(max_entries=16)
def setup_frame(path, file_size, second, scale):
    """ภาพสำหรับวาด (ย่อแล้ว เป็น data URL) กับความสว่างเฉลี่ย เก็บใน cache เพราะอ่านเฟรม 4K ใช้เวลาครึ่งวินาที
    ทำครั้งเดียวต่อวินาทีที่เลือก คลิกครั้งต่อไปไม่ต้องอ่านวิดีโอใหม่"""
    cap = cv2.VideoCapture(str(path))
    cap.set(cv2.CAP_PROP_POS_MSEC, second * 1000)
    ok, frame = cap.read()
    cap.release()
    if not ok:
        return None, 0.0
    small = cv2.resize(frame, (int(frame.shape[1] / scale), int(frame.shape[0] / scale)),
                       interpolation=cv2.INTER_AREA)
    # ส่งให้เบราว์เซอร์เป็น JPEG (เล็กกว่า PNG ~8 เท่า) ในรูป data URL ใส่ใน <img> ได้ตรง ๆ
    ok, jpg = cv2.imencode(".jpg", small, [cv2.IMWRITE_JPEG_QUALITY, 90])
    return "data:image/jpeg;base64," + base64.b64encode(jpg.tobytes()).decode(), mean_brightness(small)


def reset_setup(video_path, info):
    """วิดีโอใหม่: ล้างสิ่งที่วาดไว้ และตั้งเส้นนับเริ่มต้นจาก preset (ถ้ามี) ไม่อย่างนั้นเส้นแนวนอนกลางล่าง"""
    w, h = info["width"], info["height"]
    if Path(video_path).stem in VIDEO_PRESETS:
        (x1, y1), (x2, y2) = preset_line_points(get_preset(video_path))
    else:
        x1, y1, x2, y2 = 0.1, 0.63, 0.9, 0.63
    st.session_state.line_pts = [(int(x1 * w), int(y1 * h)), (int(x2 * w), int(y2 * h))]
    st.session_state.polygons = []
    st.session_state.current_poly = []
    st.session_state.selected = None
    st.session_state.last_click = None
    st.session_state.result = None


def apply_edit(edit):
    """รับผลจากตัววาดในเบราว์เซอร์ (src/roi_editor.js) มาเก็บใน session_state เป็นพิกเซลจริงของวิดีโอ
    คืน True ถ้าเป็นการแก้ใหม่ (ไม่ใช่ค่าเดิมที่ประมวลผลไปแล้ว)"""
    if not edit or edit.get("t") == st.session_state.last_click:
        return False
    st.session_state.last_click = edit["t"]
    to_pts = lambda pts: [(int(x), int(y)) for x, y in pts]
    st.session_state.line_pts = to_pts(edit["line"])
    st.session_state.polygons = [to_pts(poly) for poly in edit["polygons"]]
    st.session_state.current_poly = to_pts(edit["current"])
    st.session_state.selected = edit["selected"]
    return True


def resize_polygon(poly, factor, w, h):
    """ขยาย/ย่อพื้นที่รอบจุดศูนย์กลางของมันเอง (factor > 1 ขยาย, < 1 ย่อ) จุดที่เกินภาพจะถูกตัดไว้ที่ขอบ"""
    cx = sum(p[0] for p in poly) / len(poly)
    cy = sum(p[1] for p in poly) / len(poly)
    return [(int(min(max(cx + (x - cx) * factor, 0), w - 1)),
             int(min(max(cy + (y - cy) * factor, 0), h - 1))) for x, y in poly]


# ---------- ส่วนหัว ----------

st.markdown("""
<div class="hero">
  <h1>🚦 Smart Traffic Monitoring</h1>
  <p>ตรวจจับ ติดตาม และนับรถจากวิดีโอ ด้วย YOLO11 ที่ Fine-tune กับถนนไทย (car · motorcycle · bus · truck)</p>
</div>
""", unsafe_allow_html=True)

# ---------- แถบตั้งค่าด้านซ้าย ----------

with st.sidebar:
    st.header("⚙️ ตั้งค่า")

    gpu_ok = torch.cuda.is_available()
    device_options = ["GPU", "CPU"] if gpu_ok else ["CPU"]
    device_label = st.radio("ประมวลผลด้วย", device_options, horizontal=True)
    if gpu_ok:
        st.caption(f"🟢 พบการ์ดจอ: {torch.cuda.get_device_name(0)}")
    else:
        st.caption("⚪ ไม่พบ GPU ที่ใช้กับ PyTorch ได้ จึงใช้ CPU (ช้ากว่า)")

    conf = st.slider("ความมั่นใจขั้นต่ำ (confidence)", 0.10, 0.90, DEFAULT_CONF, 0.05,
                     help="กรอบที่โมเดลมั่นใจต่ำกว่านี้จะถูกตัดทิ้ง ค่าต่ำ = เจอรถมากขึ้นแต่ผิดมากขึ้น")

    st.subheader("Image Processing")
    use_clahe = st.toggle("CLAHE (เพิ่มความคมชัดภาพมืด)",
                          help="เหมาะกับวิดีโอกลางคืน ทำให้ประมวลผลช้าลงประมาณ 2 เท่า")
    use_roi = st.toggle("ROI (ไม่สนใจพื้นที่ที่วาดไว้)", value=True,
                        help="พื้นที่ที่วาดในขั้นตอนที่ 2 จะเป็นสีดำในภาพที่ส่งให้โมเดล")

    st.subheader("การแสดงผล")
    live = st.toggle("แสดงภาพสดระหว่างประมวลผล", value=True)
    preview_every = st.slider("อัปเดตภาพสดทุก ๆ (เฟรม)", 1, 30, 10, disabled=not live,
                              help="ค่ามาก = ประมวลผลเร็วขึ้น แต่ภาพสดกระตุกขึ้น วิดีโอผลลัพธ์ยังครบทุกเฟรม")

    st.markdown("**สีของแต่ละประเภท**")
    st.markdown('<div class="legend">' + "".join(
        f'<span style="background:{bgr_to_hex(c)}">{n}</span>' for n, c in CLASS_COLORS.items()) +
        "</div>", unsafe_allow_html=True)

# ---------- ขั้นที่ 1: เลือกวิดีโอ ----------

st.markdown('<div class="step">① เลือกวิดีโอ</div>', unsafe_allow_html=True)
col_up, col_sample = st.columns(2)
with col_up:
    uploaded = st.file_uploader("อัปโหลดวิดีโอ (กล้องนิ่ง มุมสูง)", type=VIDEO_TYPES)
with col_sample:
    samples = sorted(p.name for p in SAMPLE_DIR.glob("*") if p.suffix.lower().lstrip(".") in VIDEO_TYPES) \
        if SAMPLE_DIR.exists() else []
    sample = st.selectbox("หรือเลือกวิดีโอตัวอย่างในเครื่อง", ["-"] + samples)

video_path = None
if uploaded is not None:
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    video_path = WORK_DIR / uploaded.name
    if not video_path.exists() or video_path.stat().st_size != uploaded.size:
        video_path.write_bytes(uploaded.getbuffer())
elif sample != "-":
    video_path = SAMPLE_DIR / sample

if video_path is None:
    st.info("เลือกวิดีโอก่อน แล้วขั้นตอนถัดไปจะปรากฏ")
    st.stop()

file_size = video_path.stat().st_size
info = video_info(video_path, file_size)
if st.session_state.get("video_key") != str(video_path):
    st.session_state.video_key = str(video_path)
    reset_setup(video_path, info)
st.session_state.setdefault("selected", None)

w, h = info["width"], info["height"]
scale = max(w / SETUP_MAX_W, h / SETUP_MAX_H, 1.0)
setup_key = f"setup_{st.session_state.video_key}"
st.caption(f"📹 {video_path.name} · {w}×{h} · {info['fps']:.2f} fps · {info['duration']:.1f} วินาที")

# ---------- ขั้นที่ 2: วาดเส้นนับและพื้นที่ไม่สนใจ ----------

st.markdown('<div class="step">② วาดเส้นนับและพื้นที่ที่ไม่ต้องการให้โมเดลสนใจ</div>', unsafe_allow_html=True)

setup_col, help_col = st.columns([3, 1.2])
with help_col:
    second = st.slider("ใช้ภาพจากวินาทีที่", 0.0, max(0.0, info["duration"] - 0.1),
                       min(1.0, info["duration"] / 2), 0.5,
                       help="เลือกภาพที่เห็นถนนชัด ไม่มีรถคันใหญ่บัง พื้นที่ที่วาดจะใช้กับทั้งวิดีโอ")
    mode = st.segmented_control("กำลังวาด", ["📏 เส้นนับ", "⬛ พื้นที่ไม่สนใจ"],
                                default="📏 เส้นนับ", required=True)

    if mode == "📏 เส้นนับ":
        st.markdown("- คลิก **2 จุด** บนภาพ: ปลายซ้ายและปลายขวาของเส้นนับ (คลิกใหม่เพื่อวาดเส้นใหม่)\n"
                    "- **กดค้างที่ปลายเส้นแล้วลาก** = ย้ายปลายนั้น\n"
                    "- **กดค้างที่ตัวเส้นแล้วลาก** = ย้ายทั้งเส้น")
        if st.button("ล้างเส้นนับ", icon="🗑️", width="stretch"):
            st.session_state.line_pts = []
            st.rerun()
    else:
        st.markdown(f"- คลิก **{ROI_POINTS} จุด** ล้อมพื้นที่ที่ไม่ต้องการ ระบบปิดเป็นพื้นที่ให้เอง "
                    "คลิกถัดไปคือเริ่มพื้นที่ใหม่\n"
                    "- **กดค้างในพื้นที่แล้วลาก** = ย้ายทั้งพื้นที่\n"
                    "- **กดค้างที่มุม (จุดขาว) แล้วลาก** = ดึงมุมนั้น ขยาย/เปลี่ยนรูป\n"
                    "- **คลิกในพื้นที่** = เลือกพื้นที่นั้น")
        sel = st.session_state.selected
        polys = st.session_state.polygons
        b1, b2 = st.columns(2)
        if b1.button("ขยาย", icon="➕", width="stretch", disabled=sel is None):
            polys[sel] = resize_polygon(polys[sel], 1 + RESIZE_STEP, w, h)
            st.rerun()
        if b2.button("ย่อ", icon="➖", width="stretch", disabled=sel is None):
            polys[sel] = resize_polygon(polys[sel], 1 - RESIZE_STEP, w, h)
            st.rerun()
        if st.button("ลบพื้นที่ที่เลือก", icon="❌", width="stretch", disabled=sel is None):
            polys.pop(sel)
            st.session_state.selected = None
            st.rerun()
        if st.button("ย้อนจุดล่าสุด", icon="↩️", width="stretch", disabled=not st.session_state.current_poly):
            st.session_state.current_poly.pop()
            st.rerun()
        if st.button("ล้างพื้นที่ทั้งหมด", icon="🗑️", width="stretch"):
            st.session_state.polygons, st.session_state.current_poly = [], []
            st.session_state.selected = None
            st.rerun()
        st.caption(f"วาดไว้แล้ว {len(polys)} พื้นที่"
                   + (f" · เลือกพื้นที่ที่ {sel + 1}" if sel is not None else "")
                   + f" · จุดที่กำลังวาด {len(st.session_state.current_poly)}/{ROI_POINTS}"
                   " · คลิกใกล้ขอบภาพจะดูดติดขอบ")

    line_error = None
    if len(st.session_state.line_pts) == 2:
        line_error = validate_line(*st.session_state.line_pts, w, h)
        if line_error:
            st.error(line_error)
        else:
            st.success("เส้นนับใช้ได้")
    else:
        line_error = "ยังวาดเส้นนับไม่ครบ 2 จุด"
        st.warning(line_error)

img_url, brightness = setup_frame(str(video_path), file_size, second, scale)
if img_url is None:
    st.error("อ่านภาพจากวิดีโอไม่ได้")
    st.stop()

with setup_col:
    # ส่งภาพและสิ่งที่วาดไว้ให้ตัววาดในเบราว์เซอร์ พอผู้ใช้คลิก/ลากเสร็จ จะได้ผลกลับมาใน editor.edit
    editor = ROI_EDITOR(
        key=setup_key, on_edit_change=lambda: None,
        data={"img": img_url, "w": w, "h": h, "mode": "line" if mode == "📏 เส้นนับ" else "roi",
              "line": st.session_state.line_pts, "polygons": st.session_state.polygons,
              "current": st.session_state.current_poly, "selected": st.session_state.selected,
              "roi_points": ROI_POINTS, "snap": SNAP_MARGIN})
    if apply_edit(editor.edit):
        st.rerun()  # รันใหม่ให้ปุ่ม คำอธิบาย และการตรวจเส้นนับด้านขวาใช้ค่าล่าสุด
    if brightness < DARK_THRESHOLD and not use_clahe:
        st.warning(f"🌙 ภาพค่อนข้างมืด (ความสว่างเฉลี่ย {brightness:.0f}/255) แนะนำให้เปิด CLAHE ที่แถบด้านซ้าย")
    else:
        st.caption(f"ความสว่างเฉลี่ยของภาพ {brightness:.0f}/255")


# ---------- ขั้นที่ 3: ประมวลผล ----------

st.markdown('<div class="step">③ ประมวลผล</div>', unsafe_allow_html=True)

has_preset_roi = Path(video_path).stem in VIDEO_PRESETS and get_preset(video_path)["roi_polygon"] is not None
roi_ready = bool(st.session_state.polygons) or has_preset_roi
if use_roi and not st.session_state.polygons:
    st.caption("ยังไม่ได้วาดพื้นที่ไม่สนใจ: " + ("จะใช้รูปถนนที่ตั้งไว้สำหรับวิดีโอนี้" if has_preset_roi
                                                 else "ROI จะไม่ทำงาน"))
if st.session_state.current_poly:
    st.warning(f"มีพื้นที่ที่วาดค้างอยู่ยังไม่ครบ {ROI_POINTS} จุด จะไม่ถูกนำไปใช้")

run = st.button("เริ่มนับรถ", type="primary", icon="▶️", disabled=line_error is not None)

if run:
    to_ratio = lambda pts: [(x / w, y / h) for x, y in pts]
    line_points = tuple(to_ratio(st.session_state.line_pts))
    exclude = [to_ratio(p) for p in st.session_state.polygons]

    progress = st.progress(0.0, text="กำลังโหลดโมเดล...")
    live_cols = st.columns([3, 1])
    preview_slot = live_cols[0].empty()
    stats_slot = live_cols[1].empty()
    t_start = time.time()

    def on_progress(done, total):
        elapsed = time.time() - t_start
        eta = elapsed / done * (total - done)
        progress.progress(done / total, text=f"กำลังประมวลผล {done}/{total} เฟรม · เหลือประมาณ {eta:.0f} วินาที")

    def on_preview(image, summary):
        preview_slot.image(image, width="stretch")
        rows = [{"ประเภท": n, "ขาเข้า": summary["in"].get(n, 0), "ขาออก": summary["out"].get(n, 0)}
                for n in CLASS_COLORS]
        stats_slot.dataframe(pd.DataFrame(rows), hide_index=True)

    stamp = time.strftime("%Y%m%d-%H%M%S")
    raw_out = WORK_DIR / f"{Path(video_path).stem}_{stamp}_raw.mp4"
    web_out = WORK_DIR / f"{Path(video_path).stem}_{stamp}.mp4"
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    try:
        result = process_video(
            video_path, str(ROOT / DEFAULT_MODEL), raw_out, conf=conf,
            line_points=line_points, use_clahe=use_clahe,
            use_roi=use_roi and roi_ready, exclude_polygons=exclude,
            device="gpu" if device_label == "GPU" else "cpu",
            progress_callback=on_progress,
            preview_callback=on_preview if live else None, preview_every=preview_every)
        progress.progress(1.0, text="กำลังแปลงวิดีโอให้เล่นในเบราว์เซอร์ได้...")
        to_browser_video(raw_out, web_out)
        raw_out.unlink(missing_ok=True)
        result.update({"video": str(web_out), "device": device_label, "conf": conf,
                       "clahe": use_clahe, "duration": info["duration"], "name": video_path.name})
        st.session_state.result = result
        progress.empty()
        preview_slot.empty()
        stats_slot.empty()
    except Exception as e:  # แสดงข้อผิดพลาดในหน้าเว็บ แทนที่แอปจะหยุดเงียบ
        progress.empty()
        st.error(f"ประมวลผลไม่สำเร็จ: {e}")

# ---------- ขั้นที่ 4: ผลลัพธ์ ----------

res = st.session_state.get("result")
if res:
    st.markdown('<div class="step">④ ผลลัพธ์</div>', unsafe_allow_html=True)
    minutes = max(res["seconds_processed"], 1e-6) / 60
    m = st.columns(4)
    m[0].metric("⬇️ ขาเข้า", res["total_in"], border=True, help="ข้ามเส้นจากด้านบนลงด้านล่าง (รถวิ่งเข้าหากล้อง)")
    m[1].metric("⬆️ ขาออก", res["total_out"], border=True, help="ข้ามเส้นจากด้านล่างขึ้นด้านบน (รถวิ่งออกจากกล้อง)")
    m[2].metric("🚗 รวม", res["total"], border=True)
    m[3].metric("⏱️ คัน/นาที", f"{res['total'] / minutes:.1f}", border=True, help="ปริมาณรถเฉลี่ยต่อนาที")

    video_col, chart_col = st.columns([3, 2])
    with video_col:
        st.video(res["video"])
        st.caption(f"ประมวลผล {res['frames']} เฟรม ({res['seconds_processed']} วินาที) ใช้เวลา "
                   f"{res['elapsed']} วินาที · {res['device']} · Image Processing: {res['preprocess']} · "
                   f"confidence {res['conf']:.2f}")
        with open(res["video"], "rb") as f:
            st.download_button("ดาวน์โหลดวิดีโอผลลัพธ์", f, file_name=Path(res["video"]).name,
                               mime="video/mp4", icon="⬇️")

    with chart_col:
        names = list(CLASS_COLORS)
        by_class = pd.DataFrame({"ขาเข้า": [res["summary"]["in"].get(n, 0) for n in names],
                                 "ขาออก": [res["summary"]["out"].get(n, 0) for n in names]}, index=names)
        st.markdown("**จำนวนรถแยกประเภท**")
        st.bar_chart(by_class, color=["#3B82F6", "#F59E0B"], stack=True, horizontal=True, height=220)

        totals = by_class.sum(axis=1)
        share = pd.DataFrame({"ประเภท": names, "จำนวน": totals.values,
                              "สัดส่วน": [f"{v / max(res['total'], 1):.0%}" for v in totals.values]})
        st.dataframe(share, hide_index=True)

    if res["events"]:
        st.markdown("**จำนวนรถสะสมตามเวลา** (ดูว่าช่วงไหนรถผ่านหนาแน่น)")
        ev = pd.DataFrame(res["events"], columns=["วินาที", "ทิศทาง", "ประเภท"])
        cum = pd.crosstab(ev["วินาที"], ev["ประเภท"]).cumsum()
        st.line_chart(cum, x_label="วินาทีในวิดีโอ", y_label="จำนวนสะสม",
                      color=[bgr_to_hex(CLASS_COLORS[c]) for c in cum.columns], height=280)
        with st.expander("รายการรถทุกคันที่ถูกนับ"):
            st.dataframe(ev, hide_index=True)
            st.download_button("ดาวน์โหลด CSV", ev.to_csv(index=False).encode("utf-8-sig"),
                               file_name=f"{Path(res['name']).stem}_counts.csv", mime="text/csv", icon="⬇️")
