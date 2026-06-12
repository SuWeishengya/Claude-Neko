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
import json
import time
import math
import random
import urllib.request
import threading
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

def _get_version():
    """从 version.json 读取版本号"""
    try:
        vfile = Path(__file__).parent / "version.json"
        return json.loads(vfile.read_text()).get("version", "dev")
    except (FileNotFoundError, json.JSONDecodeError):
        return "dev"

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
    "happy":     "Done! ★",
    "error":     "Error!",
}

PET_SIZE = 110
PAD_TOP = 5     # 顶部留白（粒子飘出用）
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


def _hue_to_rgb(p, q, t):
    """单个 hue 值转 RGB 分量（向量化版本）"""
    t = t % 1.0
    result = np.where(
        t < 1/6, p + (q - p) * 6.0 * t,
        np.where(
            t < 0.5, q,
            np.where(
                t < 2/3, p + (q - p) * (2/3 - t) * 6.0,
                p
            )
        )
    )
    return result


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

        # 标准 HLS→RGB：R 基于 H+1/3，G 基于 H，B 基于 H-1/3
        r_nz = _hue_to_rgb(p, q, h_nz + 1/3)
        g_nz = _hue_to_rgb(p, q, h_nz)
        b_nz = _hue_to_rgb(p, q, h_nz - 1/3)

        r[mask_nonzero] = r_nz
        g[mask_nonzero] = g_nz
        b[mask_nonzero] = b_nz

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


PREFS_FILE = Path.home() / ".local" / "state" / "claude-neko" / "preferences.json"

def _load_prefs():
    """读取用户偏好"""
    try:
        return json.loads(PREFS_FILE.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def _save_prefs(prefs):
    """保存用户偏好"""
    PREFS_FILE.parent.mkdir(parents=True, exist_ok=True)
    PREFS_FILE.write_text(json.dumps(prefs, ensure_ascii=False, indent=2))


class BuddyApp:
    def __init__(self):
        self.win = Gtk.Window()
        self.win.set_title("Claude Neko")
        self.win.set_default_size(W, H)
        self.win.set_decorated(False)
        self.win.set_app_paintable(True)
        self.win.set_resizable(False)

        # 加载用户偏好
        prefs = _load_prefs()
        self._color_idx = prefs.get("color_idx", args.offset)
        saved_x = prefs.get("win_x")
        saved_y = prefs.get("win_y")
        self._lang = prefs.get("lang", "zh")

        # RGBA 透明背景
        screen = self.win.get_screen()
        rgba = screen.get_rgba_visual()
        if rgba:
            self.win.set_visual(rgba)

        # 置顶（X11 下 set_keep_above 有效）
        self.win.set_keep_above(True)

        # 窗口位置：优先使用上次保存的位置，否则屏幕右下角 + 偏移
        if saved_x is not None and saved_y is not None:
            self.win.move(saved_x, saved_y)
        else:
            display = Gdk.Display.get_default()
            monitor = display.get_primary_monitor() or display.get_monitor(0)
            if not monitor:
                self.win.move(100, 100)
                return
            geo = monitor.get_geometry()
            offset = args.offset * (PET_SIZE + 20)
            x = geo.x + geo.width - W - 20 - offset
            y = geo.y + geo.height - H - 20
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
        self.win.connect("motion-notify-event", self._on_motion)

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
        GLib.timeout_add(200, self._poll)

        # X11/XWayland 下定期刷新 set_keep_above
        GLib.timeout_add(5000, lambda: (self.win.set_keep_above(True), True)[-1])

        # shutdown 检测
        self._shutdown = False
        self._poll_fail_count = 0

    # ─── 点击/拖拽 ──────────────────────────────────────────
    def _on_button_press(self, widget, event):
        # 关闭已打开的弹窗
        if event.button in (1, 3):
            self._close_ctx_menu()
        if event.button == 1:  # 左键
            self._press_x = event.x_root
            self._press_y = event.y_root
            self._press_time = event.time
            self._is_dragging = False
            self.win.begin_move_drag(int(event.button), int(event.x_root), int(event.y_root), event.time)
        elif event.button == 3:  # 右键
            self._show_context_menu(event)
        return True

    def _on_motion(self, widget, event):
        if not self._is_dragging:
            dx = abs(event.x_root - self._press_x)
            dy = abs(event.y_root - self._press_y)
            if dx > 4 or dy > 4:
                self._is_dragging = True
        return True

    def _on_button_release(self, widget, event):
        if event.button == 1 and not self._is_dragging:
            self._show_statistics()
        else:
            # 拖拽结束，保存窗口位置
            GLib.timeout_add(500, self._save_position)
        self._is_dragging = False
        return True

    def _close_ctx_menu(self):
        """关闭右键菜单及遮罩层"""
        if hasattr(self, '_ctx_overlay') and self._ctx_overlay:
            self._ctx_overlay.destroy()
            self._ctx_overlay = None
        if hasattr(self, '_ctx_menu') and self._ctx_menu:
            self._ctx_menu.destroy()
            self._ctx_menu = None
        if hasattr(self, '_ctx_menu_da'):
            self._ctx_menu_da = None

    def _mode_color_hex(self):
        """获取当前 mode 的主题色 hex 字符串"""
        r, g, b = COLORS.get(self.mode, COLORS["idle"])
        return f"#{int(r*255):02x}{int(g*255):02x}{int(b*255):02x}"

    def _toggle_lang(self, widget=None):
        """切换中英文"""
        self._lang = 'en' if getattr(self, '_lang', 'zh') == 'zh' else 'zh'

    def _check_update(self, widget=None):
        """检查 GitHub 更新，弹窗显示结果"""
        import threading
        threading.Thread(target=self._do_check_update, daemon=True).start()

    def _do_check_update(self):
        """后台检查更新"""
        try:
            from updater import check_github_update
            result = check_github_update(timeout=8)
        except Exception:
            result = None
        GLib.idle_add(self._show_update_result, result)

    def _show_update_result(self, result):
        """弹窗显示更新检查结果"""
        if hasattr(self, '_update_win') and self._update_win:
            self._update_win.destroy()

        cc = self._cat_color_hex()
        cc_r, cc_g, cc_b = self._cat_color_rgb()

        win = Gtk.Window()
        win.set_decorated(False)
        win.set_keep_above(True)
        win.set_type_hint(Gdk.WindowTypeHint.TOOLTIP)
        self._update_win = win

        screen = win.get_screen()
        rgba = screen.get_rgba_visual()
        if rgba:
            win.set_visual(rgba)
        win.set_app_paintable(True)

        da = Gtk.DrawingArea()
        win.add(da)

        if result is None:
            lines = [
                ("检查更新", cc, 11, True),
                ("", None, 0, False),
                ("网络错误", "#e05050", 10, True),
                ("请检查网络连接", "#888898", 9, False),
            ]
        elif result["available"]:
            lines = [
                ("发现新版本", cc, 11, True),
                ("", None, 0, False),
                (f"v{result['version']}", "#ffffff", 10, True),
                (f"当前 v{result['current']}", "#888898", 9, False),
                ("", None, 0, False),
                ("请运行 neko update", cc, 9, True),
            ]
        else:
            lines = [
                ("检查更新", cc, 11, True),
                ("", None, 0, False),
                ("已是最新版本", "#00b894", 10, True),
                (f"v{result['current']}", "#888898", 9, False),
            ]

        line_h = 17
        _pad_x, pad_y = 10, 8
        win_w = 140
        win_h = pad_y + len(lines) * line_h + pad_y
        da.set_size_request(win_w, win_h)

        def _draw(widget, cr):
            w = widget.get_allocated_width()
            h = widget.get_allocated_height()
            cr.set_operator(cairo.OPERATOR_SOURCE)
            cr.set_source_rgba(0, 0, 0, 0)
            cr.paint()
            cr.set_operator(cairo.OPERATOR_OVER)
            cr.set_source_rgba(0.07, 0.07, 0.10, 0.85)
            self._rounded_rect(cr, 0, 0, w, h, 6)
            cr.fill()
            cr.set_source_rgba(cc_r, cc_g, cc_b, 0.25)
            self._rounded_rect(cr, 0, 0, w, h, 6)
            cr.set_line_width(1)
            cr.stroke()
            for i, (text, color, size, bold) in enumerate(lines):
                if not text:
                    continue
                cr.select_font_face("Sans", cairo.FONT_SLANT_NORMAL,
                                    cairo.FONT_WEIGHT_BOLD if bold else cairo.FONT_WEIGHT_NORMAL)
                cr.set_font_size(size)
                r = int(color[1:3], 16) / 255
                g = int(color[3:5], 16) / 255
                b = int(color[5:7], 16) / 255
                cr.set_source_rgba(r, g, b, 1)
                ext = cr.text_extents(text)
                cr.move_to((w - ext.width) / 2, pad_y + i * line_h + 12)
                cr.show_text(text)

        da.connect("draw", _draw)
        da.connect("button-press-event", lambda w, e: (win.destroy(), setattr(self, '_update_win', None)))

        win_x, win_y = self.win.get_position()
        win.move(win_x + W + 5, win_y + PAD_TOP)
        win.resize(win_w, win_h)
        win.show_all()
        GLib.timeout_add(6000, lambda: (win.destroy(), setattr(self, '_update_win', None), False)[2] if self._update_win else False)
        return False

    def _show_help(self, widget=None):
        """显示 neko 指令表"""
        if hasattr(self, '_help_win') and self._help_win:
            self._help_win.destroy()

        cc = self._cat_color_hex()
        cc_r, cc_g, cc_b = self._cat_color_rgb()

        win = Gtk.Window()
        win.set_decorated(False)
        win.set_keep_above(True)
        win.set_type_hint(Gdk.WindowTypeHint.TOOLTIP)
        self._help_win = win

        screen = win.get_screen()
        rgba = screen.get_rgba_visual()
        if rgba:
            win.set_visual(rgba)
        win.set_app_paintable(True)

        da = Gtk.DrawingArea()
        win.add(da)

        # (left_text, right_text, color, size, bold)
        rows = [
            (f"neko v{_get_version()}", "", cc, 11, True),
            ("", "", None, 0, False),
            ("start", "拉起小猫", "#ffffff", 9, True),
            ("stop", "关闭小猫", "#ffffff", 9, True),
            ("restart", "重启小猫", "#ffffff", 9, True),
            ("enable", "开机自启", "#ffffff", 9, True),
            ("disable", "关闭自启", "#ffffff", 9, True),
            ("status", "运行状态", "#ffffff", 9, True),
            ("", "", None, 0, False),
            ("", "监听所有Claude会话", "#888898", 8, False),
            ("", "SuWeishengya/Claude-Neko", "#888898", 8, False),
        ]

        line_h = 15
        pad_x, pad_y = 10, 8
        col_split = 60  # 左右列分界
        win_w = 160
        win_h = pad_y + len(rows) * line_h + pad_y
        da.set_size_request(win_w, win_h)

        def _draw(widget, cr):
            w = widget.get_allocated_width()
            h = widget.get_allocated_height()
            cr.set_operator(cairo.OPERATOR_SOURCE)
            cr.set_source_rgba(0, 0, 0, 0)
            cr.paint()
            cr.set_operator(cairo.OPERATOR_OVER)
            cr.set_source_rgba(0.07, 0.07, 0.10, 0.88)
            self._rounded_rect(cr, 0, 0, w, h, 6)
            cr.fill()
            cr.set_source_rgba(cc_r, cc_g, cc_b, 0.25)
            self._rounded_rect(cr, 0, 0, w, h, 6)
            cr.set_line_width(1)
            cr.stroke()
            for i, (left, right, color, size, bold) in enumerate(rows):
                if not left and not right:
                    continue
                y = pad_y + i * line_h + 11
                # 左列（指令名）
                if left:
                    cr.select_font_face("Sans", cairo.FONT_SLANT_NORMAL,
                                        cairo.FONT_WEIGHT_BOLD if bold else cairo.FONT_WEIGHT_NORMAL)
                    cr.set_font_size(size)
                    r = int(color[1:3], 16) / 255
                    g = int(color[3:5], 16) / 255
                    b = int(color[5:7], 16) / 255
                    cr.set_source_rgba(r, g, b, 1)
                    cr.move_to(pad_x, y)
                    cr.show_text(left)
                # 右列（说明）
                if right:
                    cr.select_font_face("Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
                    cr.set_font_size(size)
                    cr.set_source_rgba(0.53, 0.53, 0.60, 1)
                    cr.move_to(pad_x + col_split, y)
                    cr.show_text(right)

        da.connect("draw", _draw)
        da.connect("button-press-event", lambda w, e: (win.destroy(), setattr(self, '_help_win', None)))

        win_x, win_y = self.win.get_position()
        win.move(win_x + W + 5, win_y + PAD_TOP)
        win.resize(win_w, win_h)
        win.show_all()
        GLib.timeout_add(8000, lambda: (win.destroy(), setattr(self, '_help_win', None), False)[2] if self._help_win else False)

    def _cycle_color(self, widget=None):
        """切换猫咪颜色方案"""
        self._color_idx = (getattr(self, '_color_idx', args.offset) + 1) % len(COLOR_SCHEMES)
        self.sprite_frames = load_sprites(color_index=self._color_idx)
        fallback = self.sprite_frames.get("idle", [None])[0]
        for state in COLORS:
            if state not in self.sprite_frames and fallback:
                self.sprite_frames[state] = [fallback]
        self.win.queue_draw()
        if hasattr(self, '_ctx_menu_da') and self._ctx_menu_da:
            self._ctx_menu_da.queue_draw()
        # 保存颜色偏好
        self._save_my_prefs()

    def _open_feedback(self, widget=None):
        """打开 GitHub Issues 页面"""
        import subprocess
        subprocess.Popen(["xdg-open", "https://github.com/SuWeishengya/Claude-Neko/issues"])

    def _cat_color_hex(self):
        """获取当前猫咪颜色方案的主色（橘/蓝/粉/灰/黑/白）"""
        idx = getattr(self, '_color_idx', args.offset)
        scheme = COLOR_SCHEMES[idx % len(COLOR_SCHEMES)]
        from colorsys import hls_to_rgb
        # 基准色：橘 #FF9F43 → HLS(0.08, 0.63, 1.0)
        base_h, base_l, base_s = 0.08, 0.63, 1.0
        h = (base_h + scheme["hue_shift"]) % 1.0
        l = min(1.0, base_l * scheme["light_mult"])
        s = min(1.0, base_s * scheme["sat_mult"])
        r, g, b = hls_to_rgb(h, l, s)
        return f"#{int(r*255):02x}{int(g*255):02x}{int(b*255):02x}"

    def _apply_css(self, css_text):
        """应用全局 CSS（覆盖上一次的样式）"""
        if hasattr(self, '_css_provider') and self._css_provider:
            Gtk.StyleContext.remove_provider_for_screen(
                Gdk.Screen.get_default(), self._css_provider)
        self._css_provider = Gtk.CssProvider()
        self._css_provider.load_from_data(css_text.encode())
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(), self._css_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    def _show_context_menu(self, event):
        """显示右键菜单（透明背景 + 猫咪色）"""
        self._close_ctx_menu()
        if hasattr(self, '_stats_label') and self._stats_label:
            self._stats_label.destroy()
            self._stats_label = None

        c = self._cat_color_hex()

        # items: (text, callback, color, keep_open)
        items = [
            (self.mode.upper(), None, c, False),
            ('检查更新', self._check_update, None, False),
            ('帮助', self._show_help, None, False),
            ('颜色切换', self._cycle_color, None, True),
            ('反馈问题', self._open_feedback, None, False),
            ('停止', self._stop, "#e05050", False),
        ]

        win = Gtk.Window(type=Gtk.WindowType.POPUP)
        win.set_decorated(False)
        win.set_keep_above(True)
        self._ctx_menu = win

        screen = win.get_screen()
        rgba = screen.get_rgba_visual()
        if rgba:
            win.set_visual(rgba)
        win.set_app_paintable(True)

        da = Gtk.DrawingArea()
        win.add(da)
        self._ctx_menu_da = da

        item_h = 22
        pad_x, pad_y = 8, 5
        win_w = 95
        win_h = pad_y + len(items) * item_h + pad_y
        da.set_size_request(win_w, win_h)

        hover_idx = [-1]

        def _redraw():
            """重绘菜单（颜色切换后更新主题色）"""
            da.queue_draw()

        def _draw(widget, cr):
            w = widget.get_allocated_width()
            h = widget.get_allocated_height()
            cr.set_operator(cairo.OPERATOR_SOURCE)
            cr.set_source_rgba(0, 0, 0, 0)
            cr.paint()
            cr.set_operator(cairo.OPERATOR_OVER)
            cr.set_source_rgba(0.07, 0.07, 0.10, 0.82)
            self._rounded_rect(cr, 0, 0, w, h, 6)
            cr.fill()
            cr.set_source_rgba(*self._cat_color_rgb(), 0.25)
            self._rounded_rect(cr, 0, 0, w, h, 6)
            cr.set_line_width(1)
            cr.stroke()
            for i, (text, _, color_override, _) in enumerate(items):
                y = pad_y + i * item_h
                is_header = (i == 0)
                if i == hover_idx[0]:
                    cr.set_source_rgba(*self._cat_color_rgb(), 0.2)
                    self._rounded_rect(cr, 3, y, w - 6, item_h, 3)
                    cr.fill()
                cr.select_font_face("Sans", cairo.FONT_SLANT_NORMAL,
                                    cairo.FONT_WEIGHT_BOLD if is_header else cairo.FONT_WEIGHT_NORMAL)
                cr.set_font_size(11 if is_header else 10)
                color = color_override or ("#ffffff" if is_header else "#a0a0b0")
                if i == hover_idx[0] and not color_override:
                    color = "#ffffff"
                r = int(color[1:3], 16) / 255
                g = int(color[3:5], 16) / 255
                b = int(color[5:7], 16) / 255
                cr.set_source_rgba(r, g, b, 1)
                cr.move_to(pad_x, y + 16)
                cr.show_text(text)

        da.connect("draw", _draw)

        def _item_at(x, y):
            if x < 0 or x > win_w or y < pad_y:
                return -1
            idx = int((y - pad_y) / item_h)
            return idx if 0 <= idx < len(items) else -1

        def _on_motion(widget, ev):
            new_idx = _item_at(ev.x, ev.y)
            if new_idx != hover_idx[0]:
                hover_idx[0] = new_idx
                da.queue_draw()

        def _on_release(widget, ev):
            idx = _item_at(ev.x, ev.y)
            if idx >= 0 and items[idx][1]:
                items[idx][1](None)
                if items[idx][3]:  # keep_open: 刷新颜色但不关闭
                    _redraw()
                    return True
            self._close_ctx_menu()
            return True

        def _on_press(widget, ev):
            idx = _item_at(ev.x, ev.y)
            if idx < 0:
                self._close_ctx_menu()
                return True
            return False

        win.add_events(Gdk.EventMask.POINTER_MOTION_MASK |
                       Gdk.EventMask.BUTTON_PRESS_MASK |
                       Gdk.EventMask.BUTTON_RELEASE_MASK)
        win.connect("motion-notify-event", _on_motion)
        win.connect("button-release-event", _on_release)
        win.connect("button-press-event", _on_press)

        # 透明全屏遮罩层
        overlay = Gtk.Window(type=Gtk.WindowType.POPUP)
        overlay.set_decorated(False)
        overlay.set_keep_above(True)
        overlay_screen = overlay.get_screen()
        overlay_rgba = overlay_screen.get_rgba_visual()
        if overlay_rgba:
            overlay.set_visual(overlay_rgba)
        overlay.set_app_paintable(True)
        overlay.connect("draw", lambda w, cr: (
            cr.set_operator(cairo.OPERATOR_SOURCE),
            cr.set_source_rgba(0, 0, 0, 0),
            cr.paint()
        ))
        display = Gdk.Display.get_default()
        monitor = display.get_primary_monitor() or display.get_monitor(0)
        geo = monitor.get_geometry()
        overlay.move(geo.x, geo.y)
        overlay.resize(geo.width, geo.height)
        overlay.add_events(Gdk.EventMask.BUTTON_PRESS_MASK)
        overlay.connect("button-press-event", lambda w, e: self._close_ctx_menu())
        overlay.show_all()
        self._ctx_overlay = overlay

        win.set_transient_for(overlay)
        win.move(int(event.x_root) - 10, int(event.y_root) - 10)
        win.resize(win_w, win_h)
        win.show_all()

    def _save_position(self):
        """延迟保存窗口位置（拖拽结束后调用）"""
        self._save_my_prefs()
        return False  # 停止 GLib timeout

    def _save_my_prefs(self):
        """保存当前偏好"""
        prefs = _load_prefs()
        prefs["color_idx"] = getattr(self, '_color_idx', args.offset)
        prefs["lang"] = getattr(self, '_lang', 'zh')
        win_x, win_y = self.win.get_position()
        prefs["win_x"] = win_x
        prefs["win_y"] = win_y
        _save_prefs(prefs)

    def _cat_color_rgb(self):
        """获取猫咪颜色方案的 RGB 元组 (r,g,b) 0~1"""
        c = self._cat_color_hex()
        return (int(c[1:3], 16) / 255, int(c[3:5], 16) / 255, int(c[5:7], 16) / 255)

    def _show_statistics(self):
        """点击小猫显示统计信息（透明背景 + 猫咪色）"""
        sd = self.sd
        mode = sd.get("mode", "idle")
        msg = sd.get("msg", "")
        tokens = sd.get("tokens_today", 0)
        total = sd.get("total", 0)
        running = sd.get("running", 0)

        cc = self._cat_color_hex()
        cc_r, cc_g, cc_b = self._cat_color_rgb()
        mc = self._mode_color_hex()

        if hasattr(self, '_stats_label') and self._stats_label:
            self._stats_label.destroy()

        win = Gtk.Window()
        win.set_decorated(False)
        win.set_keep_above(True)
        win.set_type_hint(Gdk.WindowTypeHint.TOOLTIP)
        self._stats_label = win

        screen = win.get_screen()
        rgba = screen.get_rgba_visual()
        if rgba:
            win.set_visual(rgba)
        win.set_app_paintable(True)

        da = Gtk.DrawingArea()
        win.add(da)

        lines = [
            ("Claude Neko", cc, 11, True),
            (f"[{mode.upper()}]", mc, 10, True),
        ]
        if msg:
            lines.append((msg, "#888898", 9, False))
        lines.append((f"Token: {tokens:,}", cc, 9, False))
        lines.append((f"Sessions: {total}", cc, 9, False))
        lines.append((f"Running: {running}", cc, 9, False))

        line_h = 17
        _pad_x, pad_y = 8, 6
        win_w = 105
        win_h = pad_y + len(lines) * line_h + pad_y
        da.set_size_request(win_w, win_h)

        def _draw(widget, cr):
            w = widget.get_allocated_width()
            h = widget.get_allocated_height()
            cr.set_operator(cairo.OPERATOR_SOURCE)
            cr.set_source_rgba(0, 0, 0, 0)
            cr.paint()
            cr.set_operator(cairo.OPERATOR_OVER)
            cr.set_source_rgba(0.07, 0.07, 0.10, 0.82)
            self._rounded_rect(cr, 0, 0, w, h, 6)
            cr.fill()
            cr.set_source_rgba(cc_r, cc_g, cc_b, 0.25)
            self._rounded_rect(cr, 0, 0, w, h, 6)
            cr.set_line_width(1)
            cr.stroke()
            for i, (text, color, size, bold) in enumerate(lines):
                cr.select_font_face("Sans", cairo.FONT_SLANT_NORMAL,
                                    cairo.FONT_WEIGHT_BOLD if bold else cairo.FONT_WEIGHT_NORMAL)
                cr.set_font_size(size)
                r = int(color[1:3], 16) / 255
                g = int(color[3:5], 16) / 255
                b = int(color[5:7], 16) / 255
                cr.set_source_rgba(r, g, b, 1)
                ext = cr.text_extents(text)
                cr.move_to((w - ext.width) / 2, pad_y + i * line_h + 12)
                cr.show_text(text)

        da.connect("draw", _draw)

        win_x, win_y = self.win.get_position()
        win.move(win_x + W + 5, win_y + PAD_TOP)
        win.resize(win_w, win_h)
        win.show_all()

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
        """绘制审批提示（叠加在猫胸口）"""
        p = self.sd.get("prompt")
        if not p:
            return

        # 审批框居中在猫胸口
        box_h = 28
        box_w = 100
        box_x = (W - box_w) // 2
        # 猫手部 ≈ 猫精灵图垂直 82% 处
        chest_y = PAD_TOP + PET_SIZE * 0.82
        y0 = chest_y - box_h / 2

        # 半透明背景（不完全遮挡猫）
        cr.set_source_rgba(0.07, 0.07, 0.10, 0.80)
        self._rounded_rect(cr, box_x, y0, box_w, box_h, 5)
        cr.fill()
        # 边框（闪烁）
        pulse = abs(math.sin(time.time() * 3)) * 0.3 + 0.4
        cr.set_source_rgba(0.99, 0.80, 0.37, pulse)
        self._rounded_rect(cr, box_x, y0, box_w, box_h, 5)
        cr.set_line_width(1)
        cr.stroke()

        # 工具名
        cr.set_font_size(10)
        cr.set_source_rgba(0.99, 0.80, 0.37, 1)
        tool_text = p.get("tool", "?")
        label = f">> {tool_text}"
        if len(label) > 14:
            label = label[:12] + ".."
        ext = cr.text_extents(label)
        cr.move_to(W / 2 - ext.width / 2, y0 + 12)
        cr.show_text(label)

        # 提示文字
        cr.set_font_size(8)
        cr.set_source_rgba(0.7, 0.7, 0.7, 0.8)
        hint = "waiting..."
        ext = cr.text_extents(hint)
        cr.move_to(W / 2 - ext.width / 2, y0 + 22)
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
