#!/usr/bin/env python3
"""
Claude Neko — GTK3 桌面悬浮窗
使用 Cairo 绘制，RGBA 透明背景，支持 Wayland + X11
支持多实例：每只小猫独立端口，窗口自动偏移
"""

import os
import argparse
import numpy as np

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
                    default=str(Path.home() / ".local" / "state" / "claude-neko"))
args = parser.parse_args()

try:
    CONFIG = json.loads((Path(__file__).parent / "config.json").read_text())
except (FileNotFoundError, json.JSONDecodeError):
    CONFIG = {}
ASSETS = Path(__file__).parent / "assets" / "cat"

API_URL = f"http://127.0.0.1:{args.port}"

COLORS = {
    "sleep":     (0.49, 0.49, 0.60),  # #7c7c9a 灰紫
    "idle":      (0.31, 0.80, 0.77),  # #4ecdc4 青绿
    "think":     (1.00, 0.62, 0.26),  # #FF9F43 橙色
    "busy":      (0.88, 0.44, 0.33),  # #e17055 橙红
    "typing":    (0.42, 0.36, 0.91),  # #6c5ce7 紫色
    "subagent":  (0.04, 0.52, 0.89),  # #0984e3 蓝色
    "attention": (0.99, 0.80, 0.37),  # #fdcb6e 黄色
    "heart":     (0.91, 0.26, 0.58),  # #e84393 粉色
    "happy":     (0.00, 0.72, 0.58),  # #00b894 绿色
    "error":     (0.84, 0.19, 0.19),  # #d63031 红色
}
MSGS = {
    "sleep":     "zZz...",
    "idle":      "Ready",
    "think":     "Thinking...",
    "busy":      "Working...",
    "typing":    "Coding...",
    "subagent":  "Helper...",
    "attention": "Approval!",
    "heart":     "Approved!",
    "happy":     "Done! ✨",
    "error":     "Error!",
}

PET_SIZE = 110
PAD_TOP = 70    # 审批框 + 间距
PAD_BOT = 40    # 状态文字 + 粒子
PAD_SIDE = 15   # 左右边距
W = PET_SIZE + PAD_SIDE * 2
H = PAD_TOP + PET_SIZE + PAD_BOT
FPS_MS = 125

# 多实例颜色方案（固定顺序循环）
# 每个颜色是一个 (色相偏移, 饱和度系数, 亮度系数) 的元组
COLOR_SCHEMES = [
    {"name": "orange",  "hue_shift": 0,    "sat_mult": 1.0, "light_mult": 1.0},   # 原色橘猫
    {"name": "blue",    "hue_shift": 0.6,  "sat_mult": 0.8, "light_mult": 0.9},   # 蓝猫
    {"name": "pink",    "hue_shift": 0.9,  "sat_mult": 0.6, "light_mult": 1.1},   # 粉猫
    {"name": "gray",    "hue_shift": 0,    "sat_mult": 0.1, "light_mult": 0.9},   # 灰猫
    {"name": "black",   "hue_shift": 0,    "sat_mult": 0.2, "light_mult": 0.5},   # 黑猫
    {"name": "white",   "hue_shift": 0,    "sat_mult": 0.1, "light_mult": 1.4},   # 白猫
]


def _rgb_to_hls_vectorized(r, g, b):
    """向量化 RGB→HLS 转换（numpy 数组操作）"""
    maxc = np.maximum(r, np.maximum(g, b))
    minc = np.minimum(r, np.minimum(g, b))
    l = (maxc + minc) / 2.0

    s = np.zeros_like(l)
    mask_diff = maxc != minc
    mask_l50 = l <= 0.5
    diff = maxc - minc
    sumc = maxc + minc

    # 饱和度计算
    cond1 = mask_diff & mask_l50
    cond2 = mask_diff & ~mask_l50
    s[cond1] = diff[cond1] / sumc[cond1]
    s[cond2] = diff[cond2] / (2.0 - sumc[cond2])

    # 色相计算
    h = np.zeros_like(l)
    mask_r = (maxc == r) & mask_diff
    mask_g = (maxc == g) & mask_diff
    mask_b = (maxc == b) & mask_diff

    h[mask_r] = ((g[mask_r] - b[mask_r]) / diff[mask_r]) % 6.0
    h[mask_g] = (b[mask_g] - r[mask_g]) / diff[mask_g] + 2.0
    h[mask_b] = (r[mask_b] - g[mask_b]) / diff[mask_b] + 4.0
    h = h / 6.0

    return h, l, s


def _hls_to_rgb_vectorized(h, l, s):
    """向量化 HLS→RGB 转换（numpy 数组操作）"""
    r = np.zeros_like(h)
    g = np.zeros_like(h)
    b = np.zeros_like(h)

    mask_zero = s == 0
    r[mask_zero] = l[mask_zero]
    g[mask_zero] = l[mask_zero]
    b[mask_zero] = l[mask_zero]

    mask_nonzero = ~mask_zero
    if mask_nonzero.any():
        h_nz = h[mask_nonzero]
        l_nz = l[mask_nonzero]
        s_nz = s[mask_nonzero]

        q = np.where(l_nz < 0.5, l_nz * (1.0 + s_nz), l_nz + s_nz - l_nz * s_nz)
        p = 2.0 * l_nz - q

        # 将色相转换为 [0, 6) 范围
        h6 = (h_nz % 1.0) * 6.0

        # 6 个扇区
        for i, (t_min, t_max) in enumerate([
            (0, 1), (1, 2), (2, 3), (3, 4), (4, 5), (5, 6)
        ]):
            mask_sector = (h6 >= t_min) & (h6 < t_max)
            if not mask_sector.any():
                continue
            t = h6[mask_sector]
            if i % 2 == 0:
                val = p[mask_sector] + (q[mask_sector] - p[mask_sector]) * t
            else:
                val = q[mask_sector] + (p[mask_sector] - q[mask_sector]) * (t - 1.0)

            if i == 0:
                r[mask_nonzero] = np.where(mask_sector, val, r[mask_nonzero])
            elif i == 1:
                g[mask_nonzero] = np.where(mask_sector, val, g[mask_nonzero])
            elif i == 2:
                b[mask_nonzero] = np.where(mask_sector, val, b[mask_nonzero])
            elif i == 3:
                b[mask_nonzero] = np.where(mask_sector, val, b[mask_nonzero])
            elif i == 4:
                r[mask_nonzero] = np.where(mask_sector, val, r[mask_nonzero])
            elif i == 5:
                g[mask_nonzero] = np.where(mask_sector, val, g[mask_nonzero])

    return r, g, b


def apply_color_scheme(img_array, scheme):
    """对 RGBA 图像数组应用颜色方案（向量化 HSL 调整）"""
    arr = img_array.copy().astype(np.float32) / 255.0
    alpha = arr[:, :, 3]

    # 只处理非透明像素
    mask = alpha > 0.01
    if not mask.any():
        return img_array

    # 提取 RGB 通道
    r = arr[:, :, 0][mask]
    g = arr[:, :, 1][mask]
    b = arr[:, :, 2][mask]

    # 向量化 RGB → HLS
    h, l, s = _rgb_to_hls_vectorized(r, g, b)

    # 应用颜色方案
    h = (h + scheme["hue_shift"]) % 1.0
    s = np.minimum(1.0, s * scheme["sat_mult"])
    l = np.minimum(1.0, l * scheme["light_mult"])

    # 向量化 HLS → RGB
    r_out, g_out, b_out = _hls_to_rgb_vectorized(h, l, s)

    # 写回
    arr[:, :, 0][mask] = r_out
    arr[:, :, 1][mask] = g_out
    arr[:, :, 2][mask] = b_out

    return (arr * 255).astype(np.uint8)


def load_sprites(color_index=0):
    """加载所有状态的精灵图，返回 {state: [cairo.ImageSurface, ...]}"""
    sprites = {}
    scheme = COLOR_SCHEMES[color_index % len(COLOR_SCHEMES)]

    for state in COLORS:
        folder = ASSETS / state
        if not folder.exists():
            continue
        frames = []
        for i in range(20):
            f = folder / f"frame_{i}.png"
            if not f.exists():
                break
            img = Image.open(f).convert("RGBA").resize((PET_SIZE, PET_SIZE), Image.LANCZOS)
            # 应用颜色方案
            if color_index > 0:  # 第一只（index=0）保持原色
                arr = np.array(img, dtype=np.uint8)
                arr = apply_color_scheme(arr, scheme)
                img = Image.fromarray(arr, "RGBA")
            # Cairo FORMAT_ARGB32 需要预乘 alpha（premultiplied alpha）
            # PIL 是直通 alpha，必须先转换，否则半透明边缘会渲染出白边
            arr = np.array(img, dtype=np.uint8)
            alpha = arr[:, :, 3].astype(np.float32) / 255.0
            arr[:, :, 0] = (arr[:, :, 0].astype(np.float32) * alpha).astype(np.uint8)
            arr[:, :, 1] = (arr[:, :, 1].astype(np.float32) * alpha).astype(np.uint8)
            arr[:, :, 2] = (arr[:, :, 2].astype(np.float32) * alpha).astype(np.uint8)
            # Cairo ARGB32 小端序字节序 = BGRA，需要交换 R↔B
            arr_bgra = arr[:, :, [2, 1, 0, 3]]
            surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, PET_SIZE, PET_SIZE)
            cairo_data = surface.get_data()
            cairo_data[:] = arr_bgra.tobytes()
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
        # 偏移量：每只小猫完全不遮挡前一只（PET_SIZE + 间距）
        offset = args.offset * (PET_SIZE + 20)
        x = geo.x + geo.width - W - 20 - offset
        y = geo.y + geo.height - H - 20
        # 超出屏幕左边缘则换行（向上堆叠）
        if x < geo.x:
            x = geo.x + geo.width - W - 20
            y = geo.y + geo.height - H - 20 - (args.offset * (PET_SIZE + 20))
        self.win.move(x, y)

        # 拖拽支持
        self.win.add_events(Gdk.EventMask.BUTTON_PRESS_MASK |
                            Gdk.EventMask.BUTTON_RELEASE_MASK |
                            Gdk.EventMask.POINTER_MOTION_MASK)
        self.win.connect("button-press-event", self._on_button_press)
        self.win.connect("button-release-event", self._on_button_release)

        # 点击/拖拽状态追踪
        self._press_x = 0
        self._press_y = 0
        self._press_time = 0
        self._is_dragging = False

        # 绘制
        self.win.connect("draw", self._on_draw)

        # 状态
        self.mode = "idle"
        self.frame_idx = 0
        self.idle_cycle_start = time.time()  # idle 眨眼计时
        self.think_cycle_start = time.time()  # think 动画计时
        self.particles = []
        self.sd = {}

        # 加载精灵图（根据 offset 选择颜色方案）
        self.sprite_frames = load_sprites(color_index=args.offset)
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
        if event.button == 1:  # 左键
            # 记录按下位置，准备拖拽
            self._press_x = event.x
            self._press_y = event.y
            self._press_time = event.time
            self._is_dragging = False
            self.win.begin_move_drag(int(event.button), int(event.x_root), int(event.y_root), event.time)
        elif event.button == 3:  # 右键
            self._show_context_menu(event)
        return True

    def _on_button_release(self, widget, event):
        if event.button == 1 and not self._is_dragging:
            # 按下和释放位置接近，且时间短 → 视为点击
            dx = abs(event.x - self._press_x)
            dy = abs(event.y - self._press_y)
            dt = event.time - self._press_time
            if dx < 5 and dy < 5 and dt < 500:
                self._show_statistics()
        return True

    def _show_context_menu(self, event):
        """显示右键菜单"""
        menu = Gtk.Menu()

        # 状态信息（只读）
        status_item = Gtk.MenuItem(label=f"状态: {self.mode}")
        status_item.set_sensitive(False)
        menu.append(status_item)

        menu.append(Gtk.SeparatorMenuItem())

        # 复制状态到剪板
        copy_item = Gtk.MenuItem(label="📋 复制状态")
        copy_item.connect("activate", self._copy_status)
        menu.append(copy_item)

        # 查看日志
        log_item = Gtk.MenuItem(label="📄 查看日志")
        log_item.connect("activate", self._open_log)
        menu.append(log_item)

        menu.append(Gtk.SeparatorMenuItem())

        # 重启
        restart_item = Gtk.MenuItem(label="🔄 重启")
        restart_item.connect("activate", self._restart)
        menu.append(restart_item)

        # 停止
        stop_item = Gtk.MenuItem(label="⏹ 停止")
        stop_item.connect("activate", self._stop)
        menu.append(stop_item)

        menu.show_all()
        menu.popup_at_pointer(event)

    def _show_statistics(self):
        """点击小猫显示统计信息"""
        sd = self.sd
        mode = sd.get("mode", "idle")
        msg = sd.get("msg", "")
        tokens = sd.get("tokens_today", 0)
        total = sd.get("total", 0)
        running = sd.get("running", 0)

        # 构建统计文本
        lines = [
            f"🐱 Claude Neko",
            f"━━━━━━━━━━━━━━",
            f"状态: {mode}",
            f"消息: {msg}",
            f"━━━━━━━━━━━━━━",
            f"今日 Token: {tokens:,}",
            f"总会话数: {total}",
            f"运行中工具: {running}",
        ]

        # 创建浮动标签显示统计
        if hasattr(self, '_stats_label') and self._stats_label:
            self._stats_label.destroy()

        self._stats_label = Gtk.Window()
        self._stats_label.set_decorated(False)
        self._stats_label.set_keep_above(True)
        self._stats_label.set_type_hint(Gdk.WindowTypeHint.TOOLTIP)

        label = Gtk.Label(label="\n".join(lines))
        label.set_margin_start(12)
        label.set_margin_end(12)
        label.set_margin_top(8)
        label.set_margin_bottom(8)

        # 设置等宽字体
        label.set_markup(
            '<span font_family="monospace" size="small">'
            + "\n".join(lines).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            + '</span>'
        )

        self._stats_label.add(label)

        # 定位到小猫旁边
        win_x, win_y = self.win.get_position()
        self._stats_label.move(win_x + W + 5, win_y + PAD_TOP)

        self._stats_label.show_all()

        # 3 秒后自动关闭
        GLib.timeout_add(3000, self._hide_statistics)

    def _hide_statistics(self):
        """隐藏统计信息"""
        if hasattr(self, '_stats_label') and self._stats_label:
            self._stats_label.destroy()
            self._stats_label = None
        return False

    def _copy_status(self, widget):
        """复制当前状态到剪贴板"""
        sd = self.sd
        text = f"mode={sd.get('mode','idle')} msg={sd.get('msg','')} tokens={sd.get('tokens_today',0)}"
        clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        clipboard.set_text(text, -1)
        clipboard.store()

    def _open_log(self, widget):
        """打开日志文件"""
        import subprocess
        log_file = Path.home() / ".local" / "state" / "claude-neko" / "server.log"
        if log_file.exists():
            subprocess.Popen(["xdg-open", str(log_file)])

    def _restart(self, widget):
        """重启小猫"""
        import subprocess
        subprocess.Popen(["bash", "-c", f"sleep 0.5 && {ASSETS.parent.parent}/start.sh"])
        self._do_exit()

    def _stop(self, widget):
        """停止小猫"""
        def post():
            try:
                req = urllib.request.Request(
                    f"{API_URL}/api/shutdown",
                    data=b'{}',
                    headers={"Content-Type": "application/json"})
                urllib.request.urlopen(req, timeout=2)
            except Exception:
                pass
        threading.Thread(target=post, daemon=True).start()

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

    # ─── 定时刷新 ───────────────────────────────────────────
    def _tick(self):
        if self._shutdown:
            return False
        max_frames = max((len(v) for v in self.sprite_frames.values() if v), default=1)

        if self.mode == "idle":
            # idle 特殊节奏：frame_0 停留 4s，然后快速闪烁其余帧（眨眼）
            idle_frames = self.sprite_frames.get("idle", [])
            n = len(idle_frames)
            if n <= 1:
                self.frame_idx = 0
            else:
                now = time.time()
                elapsed = now - self.idle_cycle_start
                if elapsed < 4.0:
                    self.frame_idx = 0
                elif elapsed < 4.0 + 0.08 * (n - 1):
                    blink_pos = int((elapsed - 4.0) / 0.08)
                    self.frame_idx = min(blink_pos + 1, n - 1)
                else:
                    self.idle_cycle_start = now
                    self.frame_idx = 0
        elif self.mode == "think":
            # think 特殊节奏：frame_0 停留 2s，然后快速闪烁其余帧
            think_frames = self.sprite_frames.get("think", [])
            n = len(think_frames)
            if n <= 1:
                self.frame_idx = 0
            else:
                now = time.time()
                elapsed = now - self.think_cycle_start
                if elapsed < 2.0:
                    self.frame_idx = 0
                elif elapsed < 2.0 + 0.12 * (n - 1):
                    pos = int((elapsed - 2.0) / 0.12)
                    self.frame_idx = min(pos + 1, n - 1)
                else:
                    self.think_cycle_start = now
                    self.frame_idx = 0
        else:
            self.idle_cycle_start = time.time()
            self.think_cycle_start = time.time()
            self.frame_idx = int(time.time() * 8) % max_frames if max_frames > 0 else 0

        # 粒子效果
        # sleep 猫咪蜷缩姿态，猫头在左下区域
        cat_head_x = W // 2 - 20  # 猫头偏左
        cat_head_y = PAD_TOP + PET_SIZE * 0.55  # 猫头在精灵图中下方
        if self.mode == "sleep" and random.random() < 0.08:
            self.particles.append([cat_head_x + random.uniform(-8, 8), cat_head_y, 1.0, "z", "#6a6a8a"])

        # busy 旋转加载点（贴合猫头）
        if self.mode == "busy":
            if random.random() < 0.15:
                dots = ["·", "•", "●"]
                dot = random.choice(dots)
                self.particles.append([W//2 + random.uniform(-10, 10), PAD_TOP + 20, 0.8, dot, "#e17055"])

        # typing 代码符号（从小猫手部/胸口出现）
        if self.mode == "typing":
            if random.random() < 0.18:
                code_chars = ["{", "}", "<", ">", "/", ";", "=", "(", ")"]
                char = random.choice(code_chars)
                self.particles.append([W//2 + random.uniform(-15, 15), PAD_TOP + PET_SIZE * 0.65, 1.0, char, "#6c5ce7"])

        if self.mode == "heart" and random.random() < 0.12:
            self.particles.append([W//2 + random.uniform(-PET_SIZE//2, PET_SIZE//2), PAD_TOP + 5, 1.0, "<3", "#e84393"])

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
        draw_mode = self.mode
        frames = self.sprite_frames.get(draw_mode) or self.sprite_frames.get("idle", [])
        if not frames:
            return
        surface = frames[self.frame_idx % len(frames)]

        cx = W / 2
        x = cx - PET_SIZE / 2
        y = PAD_TOP
        cr.set_source_surface(surface, x, y)
        cr.paint()

    def _draw_fx(self, cr):
        for p in self.particles:
            x, y, life, ch, color_hex = p
            r = int(color_hex[1:3], 16) / 255
            g = int(color_hex[3:5], 16) / 255
            b = int(color_hex[5:7], 16) / 255
            cr.set_source_rgba(r, g, b, life)
            cr.select_font_face("Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
            cr.set_font_size(16)
            cr.move_to(x, y)
            cr.show_text(ch)

    def _draw_ui(self, cr):
        sd = self.sd
        pet_bottom = PAD_TOP + PET_SIZE + 8
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

    def _draw_approval(self, cr):
        """绘制审批提示（纯展示，无交互按钮）"""
        p = self.sd.get("prompt")
        if not p:
            return

        # 提示框显示在小猫上方
        pet_top = PAD_TOP
        box_h = 36
        box_w = PET_SIZE + 16
        box_x = (W - box_w) // 2 + 4
        y0 = pet_top - box_h - 8

        # 背景
        cr.set_source_rgba(0.11, 0.07, 0.03, 0.90)
        self._rounded_rect(cr, box_x, y0, box_w, box_h, 6)
        cr.fill()
        # 边框（闪烁效果）
        pulse = abs(math.sin(time.time() * 3)) * 0.3 + 0.5
        cr.set_source_rgba(0.99, 0.80, 0.37, pulse)
        self._rounded_rect(cr, box_x, y0, box_w, box_h, 6)
        cr.stroke()

        # 工具名
        cr.set_font_size(11)
        cr.set_source_rgba(0.99, 0.80, 0.37, 1)
        tool_text = p.get("tool", "?")
        label = f"⏳ 等待审批: {tool_text}"
        if len(label) > 18:
            label = label[:16] + ".."
        ext = cr.text_extents(label)
        cr.move_to(W / 2 - ext.width / 2, y0 + 14)
        cr.show_text(label)

        # 提示文字
        cr.set_font_size(9)
        cr.set_source_rgba(0.7, 0.7, 0.7, 0.8)
        hint = "请在终端中操作"
        ext = cr.text_extents(hint)
        cr.move_to(W / 2 - ext.width / 2, y0 + 27)
        cr.show_text(hint)

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
