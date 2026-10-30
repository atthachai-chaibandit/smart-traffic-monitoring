// ตัววาดเส้นนับและพื้นที่ไม่สนใจ (ROI) บน <canvas> ทำงานในเบราว์เซอร์ทั้งหมด
// ระหว่างลาก รูปขยับตามเมาส์ทันทีโดยไม่ต้องรอ Python พอปล่อยเมาส์ค่อยส่งผลทั้งหมดกลับไปที่ app.py
// พิกัดทุกตัวที่รับ-ส่งเป็นพิกเซลจริงของวิดีโอ (เช่น 3840x2160) ไม่ใช่พิกเซลบนจอ

const HANDLE_PX = 14;  // กดห่างจากมุม/ปลายเส้นไม่เกินกี่พิกเซลบนจอ ถือว่าจับจุดนั้น
const CLICK_PX = 5;    // เมาส์ขยับน้อยกว่านี้ระหว่างกด-ปล่อย ถือว่าคลิก ไม่ใช่ลาก

export default function (component) {
  const { data, parentElement, setTriggerValue } = component;
  const canvas = parentElement.querySelector("canvas");
  const ctx = canvas.getContext("2d");
  const W = data.w, H = data.h;

  // คัดลอกสถานะจาก Python มาแก้ในเบราว์เซอร์
  let line = data.line.map((p) => [...p]);
  let polys = data.polygons.map((poly) => poly.map((p) => [...p]));
  let cur = data.current.map((p) => [...p]);
  let sel = data.selected;
  let down = null;  // ข้อมูลตอนกดเมาส์: จุดเริ่ม, สิ่งที่จับ, ขยับไปหรือยัง

  // ---------- เครื่องมือคำนวณ ----------
  const toVideo = (e) => {  // ตำแหน่งเมาส์เทียบมุมซ้ายบนของภาพ -> พิกเซลวิดีโอ
    const r = canvas.getBoundingClientRect();
    return [(e.clientX - r.left) / r.width * W, (e.clientY - r.top) / r.height * H];
  };
  const handleR = () => HANDLE_PX * W / canvas.clientWidth;
  const dist2 = (a, b) => (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2;
  const clamp = (v, lo, hi) => Math.min(Math.max(v, lo), hi);

  function snap([x, y]) {  // ใกล้ขอบภาพไม่เกิน snap% ดูดติดขอบ
    const mx = data.snap * W, my = data.snap * H;
    x = x < mx ? 0 : (x > W - 1 - mx ? W - 1 : x);
    y = y < my ? 0 : (y > H - 1 - my ? H - 1 : y);
    return [Math.round(x), Math.round(y)];
  }

  function inside(poly, [x, y]) {  // ray casting: ลากเส้นไปทางขวา ตัดขอบเป็นจำนวนคี่ = อยู่ข้างใน
    let hit = false;
    for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
      const [xi, yi] = poly[i], [xj, yj] = poly[j];
      if ((yi > y) !== (yj > y) && x < (xj - xi) * (y - yi) / (yj - yi) + xi) hit = !hit;
    }
    return hit;
  }

  function nearSegment(a, b, p, r) {
    const dx = b[0] - a[0], dy = b[1] - a[1];
    const t = clamp(((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / (dx * dx + dy * dy || 1), 0, 1);
    return dist2(p, [a[0] + t * dx, a[1] + t * dy]) <= r * r;
  }

  const order = () => [...(sel !== null ? [sel] : []), ...polys.map((_, i) => polys.length - 1 - i)];

  function findTarget(p) {  // ตอนกดเมาส์ จับโดนอะไร
    const r = handleR();
    if (data.mode === "line") {
      const j = line.findIndex((q) => dist2(q, p) <= r * r);
      if (j >= 0) return { kind: "lineEnd", j };
      if (line.length === 2 && nearSegment(line[0], line[1], p, r)) return { kind: "line", orig: line.map((q) => [...q]) };
      return null;
    }
    for (const i of order()) {
      const j = polys[i].findIndex((q) => dist2(q, p) <= r * r);
      if (j >= 0) return { kind: "vertex", i, j };
    }
    for (const i of order()) {
      if (inside(polys[i], p)) return { kind: "poly", i, orig: polys[i].map((q) => [...q]) };
    }
    return null;
  }

  function shifted(pts, dx, dy) {  // เลื่อนทั้งก้อน แต่ไม่ให้หลุดออกนอกภาพ
    const xs = pts.map((q) => q[0]), ys = pts.map((q) => q[1]);
    dx = clamp(dx, -Math.min(...xs), W - 1 - Math.max(...xs));
    dy = clamp(dy, -Math.min(...ys), H - 1 - Math.max(...ys));
    return pts.map(([x, y]) => [Math.round(x + dx), Math.round(y + dy)]);
  }

  // ---------- วาด ----------
  const img = new Image();

  function draw() {
    if (!img.complete || !img.naturalWidth) return;
    const k = canvas.width / W;  // พิกเซลวิดีโอ -> พิกเซลของ canvas
    const P = ([x, y]) => [x * k, y * k];
    ctx.drawImage(img, 0, 0, canvas.width, canvas.height);

    const path = (pts, close) => {
      ctx.beginPath();
      pts.forEach((q, i) => (i ? ctx.lineTo(...P(q)) : ctx.moveTo(...P(q))));
      if (close) ctx.closePath();
    };
    const dot = (q, r, fill, stroke) => {
      ctx.beginPath(); ctx.arc(...P(q), r, 0, 2 * Math.PI);
      ctx.fillStyle = fill; ctx.fill();
      if (stroke) { ctx.lineWidth = 2; ctx.strokeStyle = stroke; ctx.stroke(); }
    };

    polys.forEach((poly) => { path(poly, true); ctx.fillStyle = "rgba(0,0,0,0.7)"; ctx.fill(); });
    polys.forEach((poly, i) => {
      const isSel = i === sel;
      path(poly, true);
      ctx.lineWidth = isSel ? 3 : 2;
      ctx.strokeStyle = isSel ? "#00C8FF" : "#DCDCDC";
      ctx.stroke();
      poly.forEach((q) => (isSel ? dot(q, 8, "#FFFFFF", "#00C8FF") : dot(q, 4, "#DCDCDC")));
      const c = [poly.reduce((s, q) => s + q[0], 0) / poly.length, poly.reduce((s, q) => s + q[1], 0) / poly.length];
      ctx.font = "bold 18px sans-serif"; ctx.textAlign = "center"; ctx.textBaseline = "middle";
      ctx.fillStyle = isSel ? "#00C8FF" : "#DCDCDC";
      ctx.fillText(String(i + 1), ...P(c));
    });

    if (cur.length) {  // พื้นที่ที่กำลังวาด สีเหลือง เส้นประคือเส้นปิดที่ระบบจะลากให้
      path(cur, false); ctx.lineWidth = 2; ctx.strokeStyle = "#FFDC00"; ctx.stroke();
      if (cur.length >= 3) {
        ctx.setLineDash([6, 6]); path([cur[cur.length - 1], cur[0]], false); ctx.stroke(); ctx.setLineDash([]);
      }
      cur.forEach((q) => dot(q, 6, "#FFDC00"));
    }

    if (line.length) {  // เส้นนับสีแดง
      if (line.length === 2) { path(line, false); ctx.lineWidth = 3; ctx.strokeStyle = "#FF3C3C"; ctx.stroke(); }
      line.forEach((q) => dot(q, 7, "#FF3C3C", data.mode === "line" ? "#FFFFFF" : null));
    }
  }

  img.onload = () => {
    if (canvas.width !== img.naturalWidth || canvas.height !== img.naturalHeight) {  // ตั้งขนาดใหม่จะล้างภาพ ทำเฉพาะตอนจำเป็น
      canvas.width = img.naturalWidth;
      canvas.height = img.naturalHeight;
    }
    draw();
  };
  img.src = data.img;

  const send = () => setTriggerValue("edit", { line, polygons: polys, current: cur, selected: sel, t: Date.now() });

  // ---------- เมาส์ ----------
  function onDown(e) {
    if (e.button !== 0) return;
    try { canvas.setPointerCapture(e.pointerId); } catch (_) { /* บางเบราว์เซอร์ไม่รองรับ ลากได้แต่ต้องอยู่ในภาพ */ }  // ลากออกนอกภาพก็ยังรับเหตุการณ์ต่อ
    const p = toVideo(e);
    down = { p, screen: [e.clientX, e.clientY], moved: false, target: findTarget(p) };
  }

  function onMove(e) {
    const p = toVideo(e);
    if (!down) {  // แค่เลื่อนเมาส์ผ่าน: เปลี่ยนรูปเคอร์เซอร์ให้รู้ว่าจับอะไรได้
      const t = findTarget(p);
      canvas.style.cursor = !t ? "crosshair" : (t.kind === "vertex" || t.kind === "lineEnd" ? "pointer" : "move");
      return;
    }
    if (dist2(down.screen, [e.clientX, e.clientY]) > CLICK_PX * CLICK_PX) down.moved = true;
    const t = down.target;
    if (!down.moved || !t) return;
    const dx = p[0] - down.p[0], dy = p[1] - down.p[1];
    if (t.kind === "vertex") { polys[t.i][t.j] = snap(p); sel = t.i; }
    else if (t.kind === "poly") { polys[t.i] = shifted(t.orig, dx, dy); sel = t.i; }
    else if (t.kind === "lineEnd") line[t.j] = snap(p);
    else if (t.kind === "line") line = shifted(t.orig, dx, dy);
    draw();
  }

  function onUp(e) {
    if (!down) return;
    const p = toVideo(e);
    if (!down.moved) {  // คลิก
      if (data.mode === "line") {
        line = line.length >= 2 ? [snap(p)] : [...line, snap(p)];
      } else {
        const hit = order().find((i) => inside(polys[i], p));
        if (!cur.length && hit !== undefined) {
          sel = hit;  // คลิกในพื้นที่เดิม = เลือก ไม่ใช่เริ่มวาดใหม่
        } else {
          sel = null;
          cur.push(snap(p));
          if (cur.length === data.roi_points) {  // ครบจำนวนจุด ปิดเป็นพื้นที่อัตโนมัติ
            polys.push(cur);
            cur = [];
            sel = polys.length - 1;
          }
        }
      }
      draw();
      send();
    } else if (down.target) {
      send();
    }
    down = null;
  }

  const ac = new AbortController();
  canvas.addEventListener("pointerdown", onDown, { signal: ac.signal });
  canvas.addEventListener("pointermove", onMove, { signal: ac.signal });
  canvas.addEventListener("pointerup", onUp, { signal: ac.signal });
  canvas.addEventListener("pointercancel", () => { down = null; }, { signal: ac.signal });
  return () => ac.abort();  // Streamlit เรียกตอนส่งข้อมูลใหม่มา: ถอดตัวฟังเหตุการณ์ชุดเก่าออก
}
