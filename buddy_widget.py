#!/usr/bin/env python3
"""
Claude Neko — GTK3 桌面悬浮窗
使用 Cairo 绘制，RGBA 透明背景，支持 Wayland + X11
支持多实例：每只小猫独立端口，窗口自动偏移
"""

import os
import argparse

# GNOME Wayland 下强制走 XWayland，以支持置顶和拖拽
if os.environ.get("XDG_SESSION_TYPE") == "wayland" and not os.environ.get("GDK_BACKEND"):
    os.environ["GDK_BACKEND"] = "x11"

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, GLib
import cairo
import json, time, math, random, urllib.request, threading
from pathlib import Path
from PIL import Image

# ─── 命令行参数 ─────────────────────────────────────────────
parser = argparse.ArgumentParser()
parser.add_argument("--port", type=int, default=9100)
parser.add_argument("--offset", type=int, default=0)
parser.add_argument("--state-dir", type=str,
                    default=str(Path.home() / ".local" / "state" / "claude-desktop-pet"))
args = parser.parse_args()

try:
    CONFIG = json.loads((Path(__file__).parent / "config.json").read_text())
except (FileNotFoundError, json.JSONDecodeError):
    CONFIG = {"show_level": False, "show_counts": False}
ASSETS = Path(__file__).parent / "assets" / "cat"

API_URL = f"http://127.0.0.1:{args.port}"

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
        self.win.set_title("Claude Neko")
        self.win.set_default_size(W, H)
        self.win.set_decorated(False)
        self.win.set_app_paintable(True)
        self.win.set_resizable(False)

        # RGBA 透明背景
        screen = self.win.get_screen()
        rgba = screen.get_rgba_visual()
        if rgba:
            self.win.set_visual(rgba)

        # 置顶（X11 下 set_keep_above 有效）
        self.win.set_keep_above(True)

        # 窗口位置：屏幕右下角 + 偏移（多实例错开，向上堆叠）
        display = Gdk.Display.get_default()
        monitor = display.get_primary_monitor() or display.get_monitor(0)
        if not monitor:
            # 极端情况：无显示器，使用默认窗口位置
            self.win.move(100, 100)
            return
        geo = monitor.get_geometry()
        offset = args.offset * 30
        x = geo.x + geo.width - W - 20 + offset
        y = geo.y + geo.height - H - 20 - offset
        # 超出屏幕右边缘则换列
        if x + W > geo.x + geo.width:
            x = geo.x + geo.width - W - 20
            y = geo.y + geo.height - H - 20 - (offset % 200)
        self.win.move(x, y)

        # 拖拽支持
        self.win.add_events(Gdk.EventMask.BUTTON_PRESS_MASK |
                            Gdk.EventMask.BUTTON_RELEASE_MASK |
                            Gdk.EventMask.POINTER_MOTION_MASK)
        self.win.connect("button-press-event", self._on_button_press)

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

        # X11/XWayland 下定期刷新 set_keep_above
        GLib.timeout_add(5000, lambda: (self.win.set_keep_above(True), True)[-1])

        # shutdown 检测
        self._shutdown = False
        self._poll_fail_count = 0

    # ─── 点击/拖拽 ──────────────────────────────────────────
    def _on_button_press(self, widget, event):
        if event.button == 1:
            # 先检查是否点击了审批按钮
            if self._check_approval_click(event.x, event.y):
                return True
            self.win.begin_move_drag(int(event.button), int(event.x_root), int(event.y_root), event.time)
        return True

    def _check_approval_click(self, x, y):
        """检查点击是否在审批按钮区域内"""
        p = self.sd.get("prompt")
        if not p:
            return False
        pet_top = H // 2 + 8 - PET_SIZE // 2
        box_h = 52
        box_w = PET_SIZE + 16
        box_x = (W - box_w) // 2 + 4
        y0 = pet_top - box_h - 8
        btn_y = y0 + box_h - 20
        btn_h = 14
        gap = 6
        btn_w = (box_w - gap * 3) // 2
        btn_left_x = box_x + gap
        btn_right_x = box_x + gap * 2 + btn_w

        if btn_left_x <= x <= btn_left_x + btn_w and btn_y <= y <= btn_y + btn_h:
            self._decide("once")
            return True
        if btn_right_x <= x <= btn_right_x + btn_w and btn_y <= y <= btn_y + btn_h:
            self._decide("deny")
            return True
        return False

    # ─── 状态轮询 ───────────────────────────────────────────
    def _poll(self):
        def fetch():
            try:
                r = urllib.request.urlopen(f"{API_URL}/api/state", timeout=1)
                data = json.loads(r.read())
                self._poll_fail_count = 0
                GLib.idle_add(self._update_state, data)
            except Exception:
                self._poll_fail_count += 1
                if self._poll_fail_count >= 4:  # 连续 4 次失败（约 2 秒）认为 server 已死
                    GLib.idle_add(self._do_exit)
        threading.Thread(target=fetch, daemon=True).start()
        return True

    def _update_state(self, data):
        self.sd = data
        self.mode = data.get("mode", "idle")
        # 检查 shutdown 信号
        if data.get("shutdown"):
            self._do_exit()
            return False
        self.win.queue_draw()
        return False

    def _do_exit(self):
        """优雅退出"""
        self._shutdown = True
        Gtk.main_quit()

    # ─── 审批操作 ────────────────────────────────────────────
    def _decide(self, decision):
        pid = self.sd.get("prompt", {}).get("id")
        if not pid:
            return
        def post():
            try:
                req = urllib.request.Request(
                    f"{API_URL}/api/permission",
                    data=json.dumps({"id": pid, "decision": decision}).encode(),
                    headers={"Content-Type": "application/json"})
                urllib.request.urlopen(req, timeout=2)
            except Exception:
                pass
        threading.Thread(target=post, daemon=True).start()

    # ─── 定时刷新 ───────────────────────────────────────────
    def _tick(self):
        if self._shutdown:
            return False
        max_frames = max((len(v) for v in self.sprite_frames.values() if v), default=1)
        self.frame_idx = int(time.time() * 2) % max_frames if max_frames > 0 else 0

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
        # 限制粒子数量，防止长期运行内存增长
        if len(self.particles) > 200:
            self.particles = self.particles[-200:]

        self.win.queue_draw()
        return True

    # ─── 绘制 ───────────────────────────────────────────────
    def _on_draw(self, widget, cr):
        cr.set_operator(cairo.OPERATOR_SOURCE)
        cr.set_source_rgba(0, 0, 0, 0)
        cr.paint()
        cr.set_operator(cairo.OPERATOR_OVER)

        self._draw_pet(cr)
        self._draw_fx(cr)
        self._draw_ui(cr)
        self._draw_approval(cr)

    def _draw_pet(self, cr):
        # idle + "Ready" → 用 sleep 图标（空闲睡觉）
        # idle + "Thinking" → 用 idle 图标（思考中）
        draw_mode = self.mode
        if self.mode == "idle" and self.sd.get("msg") == "Ready":
            draw_mode = "sleep"
        frames = self.sprite_frames.get(draw_mode) or self.sprite_frames.get("idle", [])
        if not frames:
            return
        surface = frames[self.frame_idx % len(frames)]

        cx = W / 2
        cy = H / 2 + 8

        if self.mode == "celebrate":
            cy -= abs(math.sin(time.time() * 5)) * 12

        x = cx - PET_SIZE / 2
        y = cy - PET_SIZE / 2
        cr.set_source_surface(surface, x, y)
        cr.paint()

    def _draw_fx(self, cr):
        for p in self.particles:
            x, y, life, ch, color_hex = p
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
        pet_bottom = H // 2 + 8 + PET_SIZE // 2 + 8
        y = pet_bottom

        # 状态文字（优先显示 msg，否则用默认 MSGS）
        msg = sd.get("msg") or MSGS.get(self.mode, "")
        if not msg:
            msg = MSGS.get(self.mode, "")
        # 截断过长文字
        if len(msg) > 20:
            msg = msg[:18] + ".."
        cr.select_font_face("Monospace", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
        cr.set_font_size(13)
        cr.set_source_rgba(0.545, 0.580, 0.620, 1)
        ext = cr.text_extents(msg)
        cr.move_to(W / 2 - ext.width / 2, y)
        cr.show_text(msg)
        y += 16

        # 等级 + token 数（可选）
        if CONFIG.get("show_level"):
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
            cr.set_source_rgba(0.345, 0.647, 1.0, 1)
            ext = cr.text_extents(level_text)
            cr.move_to(W / 2 - ext.width / 2, y)
            cr.show_text(level_text)
            y += 14

        # 审批/拒绝计数（可选）
        if CONFIG.get("show_counts"):
            count_text = f"v{sd.get('approve_count', 0)} x{sd.get('deny_count', 0)}"
            cr.set_source_rgba(0.545, 0.580, 0.620, 1)
            ext = cr.text_extents(count_text)
            cr.move_to(W / 2 - ext.width / 2, y)
            cr.show_text(count_text)

    def _draw_approval(self, cr):
        p = self.sd.get("prompt")
        if not p:
            return

        # 审批框显示在小猫上方，宽度与小猫一致
        pet_top = H // 2 + 8 - PET_SIZE // 2
        box_h = 52
        box_w = PET_SIZE + 16  # 126px，比小猫宽一点
        box_x = (W - box_w) // 2 + 4
        y0 = pet_top - box_h - 8

        cr.set_source_rgba(0.11, 0.07, 0.03, 0.95)
        self._rounded_rect(cr, box_x, y0, box_w, box_h, 6)
        cr.fill()
        cr.set_source_rgba(0.82, 0.60, 0.13, 1)
        self._rounded_rect(cr, box_x, y0, box_w, box_h, 6)
        cr.stroke()

        # 标题 + 工具名（只显示工具名关键字）
        cr.set_font_size(12)
        cr.set_source_rgba(0.82, 0.60, 0.13, 1)
        tool_text = p.get("tool", "?")
        label = f"Approve: {tool_text}"
        ext = cr.text_extents(label)
        cr.move_to(W / 2 - ext.width / 2, y0 + 14)
        cr.show_text(label)

        # 小提示
        hint = p.get("hint", "")
        if hint:
            if len(hint) > 22:
                hint = hint[:20] + ".."
            cr.set_font_size(9)
            cr.set_source_rgba(0.545, 0.580, 0.620, 1)
            ext = cr.text_extents(hint)
            cr.move_to(W / 2 - ext.width / 2, y0 + 26)
            cr.show_text(hint)

        # 小按钮（居中对称）
        btn_y = y0 + box_h - 20
        btn_h = 14
        gap = 6
        btn_w = (box_w - gap * 3) // 2
        btn_left_x = box_x + gap
        btn_right_x = box_x + gap * 2 + btn_w
        self._draw_button(cr, btn_left_x, btn_y, btn_w, btn_h,
                          "Approve", (0.137, 0.525, 0.212, 1),
                          (1, 1, 1, 1), "once")
        self._draw_button(cr, btn_right_x, btn_y, btn_w, btn_h,
                          "Deny", (0.19, 0.21, 0.24, 1),
                          (0.90, 0.93, 0.95, 1), "deny")

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
