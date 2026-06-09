#!/usr/bin/env python3
"""
Claude Desktop Buddy — GTK3 桌面悬浮窗
使用 Cairo 绘制，RGBA 透明背景，支持 Wayland + X11
"""

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, GLib
import cairo
import json, time, math, random, urllib.request, threading
from pathlib import Path
from PIL import Image

CONFIG = json.loads((Path(__file__).parent / "config.json").read_text())
ASSETS = Path(__file__).parent / "assets" / "cat"

COLORS = {
    "sleep": (0.49, 0.49, 0.60),    # #7c7c9a
    "idle":  (1.00, 0.62, 0.26),    # #FF9F43
    "busy":  (0.88, 0.44, 0.33),    # #e17055
    "attention": (0.99, 0.80, 0.37),# #fdcb6e
    "celebrate": (0.00, 0.81, 0.79),# #00cec9
    "heart": (0.91, 0.26, 0.58),    # #e84393
    "angry": (0.88, 0.44, 0.33),    # #e17055
}
MSGS = {
    "sleep": "zZz...", "idle": "Ready", "busy": "Working...",
    "attention": "Approval!", "celebrate": "Level Up!", "heart": "Approved!",
    "angry": "Hmph!",
}

PET_SIZE = 110
W, H = 170, 240
FPS_MS = 500


def load_sprites():
    """加载所有状态的精灵图，返回 {state: [cairo.ImageSurface, ...]}"""
    sprites = {}
    for state in list(COLORS.keys()) + ["normal"]:
        folder = ASSETS / state
        if not folder.exists():
            continue
        frames = []
        for i in range(20):
            f = folder / f"frame_{i}.png"
            if not f.exists():
                break
            img = Image.open(f).convert("RGBA").resize((PET_SIZE, PET_SIZE), Image.NEAREST)
            # PIL → cairo ImageSurface
            surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, PET_SIZE, PET_SIZE)
            ctx = cairo.Context(surface)
            # 将 PIL 像素写入 cairo surface
            pil_data = img.tobytes('raw', 'BGRA')
            cairo_data = surface.get_data()
            cairo_data[:] = pil_data
            surface.mark_dirty()
            frames.append(surface)
        if frames:
            sprites[state] = frames
    return sprites


class BuddyApp:
    def __init__(self):
        self.win = Gtk.Window()
        self.win.set_title("Claude Desktop Buddy")
        self.win.set_default_size(W, H)
        self.win.set_decorated(False)
        self.win.set_app_paintable(True)
        self.win.set_keep_above(True)
        self.win.set_resizable(False)

        # RGBA 透明背景
        screen = self.win.get_screen()
        rgba = screen.get_rgba_visual()
        if rgba:
            self.win.set_visual(rgba)

        # 窗口位置：屏幕右上角
        display = Gdk.Display.get_default()
        monitor = display.get_primary_monitor() or display.get_monitor(0)
        geo = monitor.get_geometry()
        self.win.move(geo.x + geo.width - W - 20, geo.y + 40)

        # 拖拽支持
        self._drag_start = None
        self.win.add_events(Gdk.EventMask.BUTTON_PRESS_MASK |
                            Gdk.EventMask.BUTTON_RELEASE_MASK |
                            Gdk.EventMask.POINTER_MOTION_MASK)
        self.win.connect("button-press-event", self._on_button_press)
        self.win.connect("button-release-event", self._on_button_release)
        self.win.connect("motion-notify-event", self._on_motion)

        # 绘制
        self.win.connect("draw", self._on_draw)

        # 状态
        self.mode = "idle"
        self.frame_idx = 0
        self.particles = []
        self.sd = {}

        # 加载精灵图
        self.sprite_frames = load_sprites()
        # 为缺失的状态准备 fallback
        fallback = self.sprite_frames.get("idle", [None])[0]
        for state in COLORS:
            if state not in self.sprite_frames and fallback:
                self.sprite_frames[state] = [fallback]

        # 定时器
        GLib.timeout_add(FPS_MS, self._tick)
        GLib.timeout_add(500, self._poll)

    # ─── 拖拽 ───────────────────────────────────────────────
    def _on_button_press(self, widget, event):
        if event.button == 1:
            self._drag_start = (event.x_root, event.y_root)
        return True

    def _on_button_release(self, widget, event):
        self._drag_start = None

    def _on_motion(self, widget, event):
        if self._drag_start:
            dx = event.x_root - self._drag_start[0]
            dy = event.y_root - self._drag_start[1]
            x, y = self.win.get_position()
            self.win.move(x + int(dx), y + int(dy))
            self._drag_start = (event.x_root, event.y_root)

    # ─── 状态轮询 ───────────────────────────────────────────
    def _poll(self):
        def fetch():
            try:
                r = urllib.request.urlopen(
                    f"http://{CONFIG['host']}:{CONFIG['port']}/api/state", timeout=1)
                data = json.loads(r.read())
                GLib.idle_add(self._update_state, data)
            except Exception:
                pass
        threading.Thread(target=fetch, daemon=True).start()
        return True  # 继续定时

    def _update_state(self, data):
        self.sd = data
        self.mode = data.get("mode", "sleep")
        self.win.queue_draw()
        return False

    # ─── 审批操作 ────────────────────────────────────────────
    def _decide(self, decision):
        pid = self.sd.get("prompt", {}).get("id")
        if not pid:
            return
        def post():
            try:
                req = urllib.request.Request(
                    f"http://{CONFIG['host']}:{CONFIG['port']}/api/permission",
                    data=json.dumps({"id": pid, "decision": decision}).encode(),
                    headers={"Content-Type": "application/json"})
                urllib.request.urlopen(req, timeout=2)
            except Exception:
                pass
        threading.Thread(target=post, daemon=True).start()

    # ─── 定时刷新 ───────────────────────────────────────────
    def _tick(self):
        self.frame_idx = int(time.time() * 2) % max(
            (len(v) for v in self.sprite_frames.values()), default=1)

        # 粒子效果
        if self.mode == "celebrate" and random.random() < 0.3:
            self.particles.append([random.uniform(20, W-20), 40, 1.0,
                                   random.choice(["*", "+", "~"]),
                                   random.choice(["#fdcb6e", "#e17055", "#00cec9"])])
        if self.mode == "sleep" and random.random() < 0.08:
            self.particles.append([W//2 + random.uniform(-5, 15), 30, 1.0, "z", "#6a6a8a"])
        if self.mode == "heart" and random.random() < 0.12:
            self.particles.append([random.uniform(30, W-30), 45, 1.0, "<3", "#e84393"])

        for p in self.particles:
            p[1] -= 0.8
            p[2] -= 0.015
        self.particles = [p for p in self.particles if p[2] > 0]

        self.win.queue_draw()
        return True  # 继续定时

    # ─── 绘制 ───────────────────────────────────────────────
    def _on_draw(self, widget, cr):
        # 1. 清除为全透明
        cr.set_operator(cairo.OPERATOR_SOURCE)
        cr.set_source_rgba(0, 0, 0, 0)
        cr.paint()

        cr.set_operator(cairo.OPERATOR_OVER)

        # 2. 绘制精灵图
        self._draw_pet(cr)

        # 3. 绘制粒子效果
        self._draw_fx(cr)

        # 4. 绘制 UI 文字
        self._draw_ui(cr)

        # 5. 绘制审批弹窗
        self._draw_approval(cr)

    def _draw_pet(self, cr):
        frames = self.sprite_frames.get(self.mode) or self.sprite_frames.get("idle", [])
        if not frames:
            return
        surface = frames[self.frame_idx % len(frames)]

        cx = W / 2
        cy = H / 2 + 8

        # idle/busy/attention/heart 浮动
        if self.mode in ("idle", "busy", "attention", "heart", "angry"):
            pass  # TODO: bob effect

        # celebrate 跳跃
        if self.mode == "celebrate":
            cy -= abs(math.sin(time.time() * 5)) * 12

        x = cx - PET_SIZE / 2
        y = cy - PET_SIZE / 2
        cr.set_source_surface(surface, x, y)
        cr.paint()

    def _draw_fx(self, cr):
        for p in self.particles:
            x, y, life, ch, color_hex = p
            # 解析颜色
            r = int(color_hex[1:3], 16) / 255
            g = int(color_hex[3:5], 16) / 255
            b = int(color_hex[5:7], 16) / 255
            cr.set_source_rgba(r, g, b, life)
            cr.select_font_face("Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
            cr.set_font_size(12)
            cr.move_to(x, y)
            cr.show_text(ch)

    def _draw_ui(self, cr):
        sd = self.sd

        # 状态文字
        msg = MSGS.get(self.mode, "")
        cr.select_font_face("Monospace", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
        cr.set_font_size(13)
        cr.set_source_rgba(0.545, 0.580, 0.620, 1)  # #8b949e
        ext = cr.text_extents(msg)
        cr.move_to(W / 2 - ext.width / 2, H - 42)
        cr.show_text(msg)

        # 等级 + token 数
        t = sd.get("tokens_total", 0)
        if t >= 1_000_000_000:
            ts = f"{t/1_000_000_000:.1f}B"
        elif t >= 1_000_000:
            ts = f"{t/1_000_000:.1f}M"
        elif t >= 1000:
            ts = f"{t/1000:.1f}K"
        else:
            ts = str(t)
        level_text = f"Lv.{sd.get('level', 1)} {ts}tok"
        cr.set_font_size(11)
        cr.set_source_rgba(0.345, 0.647, 1.0, 1)  # #58a6ff
        ext = cr.text_extents(level_text)
        cr.move_to(W / 2 - ext.width / 2, H - 22)
        cr.show_text(level_text)

        # 审批/拒绝计数
        count_text = f"v{sd.get('approve_count', 0)} x{sd.get('deny_count', 0)}"
        cr.set_source_rgba(0.545, 0.580, 0.620, 1)
        ext = cr.text_extents(count_text)
        cr.move_to(W / 2 - ext.width / 2, H - 6)
        cr.show_text(count_text)

    def _draw_approval(self, cr):
        p = self.sd.get("prompt")
        if not p:
            return

        y0 = H - 155
        # 弹窗背景
        cr.set_source_rgba(0.11, 0.07, 0.03, 0.95)  # #1c1207
        self._rounded_rect(cr, 8, y0, W - 16, 65, 6)
        cr.fill()
        # 边框
        cr.set_source_rgba(0.82, 0.60, 0.13, 1)  # #d29922
        self._rounded_rect(cr, 8, y0, W - 16, 65, 6)
        cr.stroke()

        # 标题
        cr.set_font_size(13)
        cr.set_source_rgba(0.82, 0.60, 0.13, 1)
        ext = cr.text_extents("Approval!")
        cr.move_to(W / 2 - ext.width / 2, y0 + 15)
        cr.show_text("Approval!")

        # 工具名
        cr.set_font_size(10)
        cr.set_source_rgba(0.90, 0.93, 0.95, 1)  # #e6edf3
        tool_text = p.get("tool", "-")
        ext = cr.text_extents(tool_text)
        cr.move_to(W / 2 - ext.width / 2, y0 + 30)
        cr.show_text(tool_text)

        # 提示
        hint = p.get("hint", "-")
        if len(hint) > 26:
            hint = hint[:24] + ".."
        cr.set_source_rgba(0.545, 0.580, 0.620, 1)
        ext = cr.text_extents(hint)
        cr.move_to(W / 2 - ext.width / 2, y0 + 44)
        cr.show_text(hint)

        # Approve 按钮
        self._draw_button(cr, 12, H - 108, W // 2 - 16, 18,
                          "Approve", (0.137, 0.525, 0.212, 1),  # #238636
                          (1, 1, 1, 1), "once")
        # Deny 按钮
        self._draw_button(cr, W // 2 + 4, H - 108, W // 2 - 16, 18,
                          "Deny", (0.19, 0.21, 0.24, 1),  # #30363d
                          (0.90, 0.93, 0.95, 1), "deny")  # #e6edf3

    def _draw_button(self, cr, x, y, w, h, label, bg_color, text_color, decision):
        cr.set_source_rgba(*bg_color)
        self._rounded_rect(cr, x, y, w, h, 3)
        cr.fill()
        cr.set_font_size(10)
        cr.set_source_rgba(*text_color)
        ext = cr.text_extents(label)
        cr.move_to(x + w / 2 - ext.width / 2, y + h / 2 + ext.height / 2)
        cr.show_text(label)

    @staticmethod
    def _rounded_rect(cr, x, y, w, h, r):
        cr.new_sub_path()
        cr.arc(x + w - r, y + r, r, -math.pi / 2, 0)
        cr.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
        cr.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
        cr.arc(x + r, y + r, r, math.pi, 3 * math.pi / 2)
        cr.close_path()

    def run(self):
        self.win.show_all()
        Gtk.main()


if __name__ == "__main__":
    BuddyApp().run()
