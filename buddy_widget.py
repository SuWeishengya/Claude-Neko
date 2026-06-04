#!/usr/bin/env python3
"""
Claude Desktop Buddy — tkinter 桌面悬浮窗（精灵图版）
"""

import tkinter as tk
from tkinter import font as tkfont
import json, time, urllib.request, threading
from pathlib import Path

try:
    from PIL import Image, ImageTk
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

CONFIG = json.loads((Path(__file__).parent / "config.json").read_text())
ASSETS = Path(__file__).parent / "assets" / "cat"

COLORS = {
    "sleep":"#7c7c9a","idle":"#FF9F43","busy":"#e17055",
    "attention":"#fdcb6e","celebrate":"#00cec9","heart":"#e84393",
    "angry":"#e17055",
}
MSGS = {
    "sleep":"zZz...","idle":"Ready","busy":"Working...",
    "attention":"Approval!","celebrate":"Level Up!","heart":"Approved!",
    "angry":"Hmph!",
}

# 宠物精灵图尺寸
PET_SIZE = 110
W, H = 170, 240
FPS_MS = 500  # 帧动画刷新间隔 ms


def load_sprites():
    """加载所有状态的精灵图，返回 {state: [ImageTk, ...]}"""
    sprites = {}
    if not HAS_PIL:
        return sprites
    for state in list(COLORS.keys()) + ["normal"]:
        folder = ASSETS / state
        if not folder.exists():
            continue
        frames = []
        for i in range(20):
            f = folder / f"frame_{i}.png"
            if not f.exists():
                break
            img = Image.open(f).convert("RGBA")
            img = img.resize((PET_SIZE, PET_SIZE), Image.NEAREST)
            frames.append(img)
        if frames:
            sprites[state] = frames
    return sprites


class BuddyApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-transparentcolor", "#0d1117")
        self.root.configure(bg="#0d1117")

        sw = self.root.winfo_screenwidth()
        x = sw - W - 20
        self.root.geometry(f"{W}x{H}+{x}+40")

        self._dx = self._dy = 0
        self.root.bind("<Button-1>", self._drag_start)
        self.root.bind("<B1-Motion>", self._drag_move)

        self.canvas = tk.Canvas(self.root, width=W, height=H, bg="#0d1117", highlightthickness=0)
        self.canvas.pack()

        self.f_sm = tkfont.Font(family="Consolas", size=12, weight="bold")
        self.f_xs = tkfont.Font(family="Consolas", size=10)

        self.mode = "idle"
        self.bob = 0.0
        self.frame_idx = 0
        self.particles = []
        self.sd = {}

        # 加载精灵图
        raw = load_sprites()
        self.sprite_frames = {}  # {state: [ImageTk, ...]}
        for state, imgs in raw.items():
            self.sprite_frames[state] = [ImageTk.PhotoImage(im) for im in imgs]

        # 为缺失的状态准备 fallback（用 idle 的第一帧）
        fallback = self.sprite_frames.get("idle", [None])[0] if "idle" in self.sprite_frames else None
        for state in COLORS:
            if state not in self.sprite_frames and fallback:
                self.sprite_frames[state] = [fallback]

        self._pet_img_id = None
        self._tick()
        self._poll()

    def _drag_start(self, e):
        self._dx, self._dy = e.x, e.y

    def _drag_move(self, e):
        self.root.geometry(f"+{self.root.winfo_x()+e.x-self._dx}+{self.root.winfo_y()+e.y-self._dy}")

    def _get_sprite(self):
        """获取当前状态的当前帧 ImageTk"""
        frames = self.sprite_frames.get(self.mode)
        if not frames:
            frames = self.sprite_frames.get("idle", [None])
        return frames[self.frame_idx % len(frames)]

    def _draw_pet(self):
        c = self.canvas
        c.delete("pet")
        img = self._get_sprite()
        if not img:
            return

        cx, cy = W // 2, H // 2 + 8

        # idle/busy/attention/heart 上下浮动
        if self.mode in ("idle", "busy", "attention", "heart", "angry"):
            cy += int(self.bob)

        # celebrate 跳跃
        if self.mode == "celebrate":
            import math
            cy -= int(abs(math.sin(time.time() * 5)) * 12)

        self._pet_img_id = c.create_image(cx, cy, image=img, tags="pet")

    def _draw_ui(self):
        c = self.canvas
        c.delete("ui")

        # 状态文字
        c.create_text(W//2, H - 42, text=MSGS.get(self.mode, ""), fill="#8b949e", font=self.f_sm, tags="ui")

        # 等级 + token 数
        sd = self.sd
        t = sd.get("tokens_total", 0)
        if t >= 1_000_000_000:
            ts = f"{t/1_000_000_000:.1f}B"
        elif t >= 1_000_000:
            ts = f"{t/1_000_000:.1f}M"
        elif t >= 1000:
            ts = f"{t/1000:.1f}K"
        else:
            ts = str(t)
        c.create_text(W//2, H - 22, text=f"Lv.{sd.get('level',1)} {ts}tok", fill="#58a6ff", font=self.f_xs, tags="ui")

        # 审批/拒绝计数
        c.create_text(W//2, H - 6, text=f"v{sd.get('approve_count',0)} x{sd.get('deny_count',0)}", fill="#8b949e", font=self.f_xs, tags="ui")

        # 权限审批弹窗
        p = sd.get("prompt")
        if p:
            y0 = H - 155
            c.create_rectangle(8, y0, W-8, H-90, fill="#1c1207", outline="#d29922", tags="ui")
            c.create_text(W//2, y0+12, text="Approval!", fill="#d29922", font=self.f_sm, tags="ui")
            hint = p.get("hint", "-")
            if len(hint) > 26:
                hint = hint[:24] + ".."
            c.create_text(W//2, y0+30, text=p.get("tool", "-"), fill="#e6edf3", font=self.f_xs, tags="ui")
            c.create_text(W//2, y0+44, text=hint, fill="#8b949e", font=self.f_xs, tags="ui")
            c.create_rectangle(12, H-108, W//2-4, H-90, fill="#238636", tags="btn_approve")
            c.create_text(W//4+4, H-99, text="Approve", fill="white", font=self.f_xs, tags="btn_approve")
            c.create_rectangle(W//2+4, H-108, W-12, H-90, fill="#30363d", outline="#484f58", tags="btn_deny")
            c.create_text(W*3//4-4, H-99, text="Deny", fill="#e6edf3", font=self.f_xs, tags="btn_deny")
            c.tag_bind("btn_approve", "<Button-1>", lambda e: self._decide("once"))
            c.tag_bind("btn_deny", "<Button-1>", lambda e: self._decide("deny"))

    def _decide(self, d):
        pid = self.sd.get("prompt", {}).get("id")
        if not pid:
            return
        def post():
            try:
                req = urllib.request.Request(
                    f"http://{CONFIG['host']}:{CONFIG['port']}/api/permission",
                    data=json.dumps({"id": pid, "decision": d}).encode(),
                    headers={"Content-Type": "application/json"})
                urllib.request.urlopen(req, timeout=2)
            except Exception:
                pass
        threading.Thread(target=post, daemon=True).start()

    def _draw_fx(self):
        c = self.canvas
        c.delete("fx")
        for p in self.particles:
            x, y, life, ch, co = p
            c.create_text(x, y, text=ch, fill=co, font=("Arial", 10), tags="fx")

    def _tick(self):
        import math
        t = time.time()

        # 浮动
        self.bob = 0

        # 帧动画切换
        self.frame_idx = int(t * 2) % max(len(v) for v in self.sprite_frames.values()) if self.sprite_frames else 0

        # 粒子效果
        if self.mode == "celebrate" and __import__("random").random() < 0.3:
            self.particles.append([__import__("random").uniform(20, W-20), 40, 1.0,
                                   __import__("random").choice(["*", "+", "~"]),
                                   __import__("random").choice(["#fdcb6e", "#e17055", "#00cec9"])])
        if self.mode == "sleep" and __import__("random").random() < 0.08:
            self.particles.append([W//2 + __import__("random").uniform(-5, 15), 30, 1.0, "z", "#6a6a8a"])
        if self.mode == "heart" and __import__("random").random() < 0.12:
            self.particles.append([__import__("random").uniform(30, W-30), 45, 1.0, "<3", "#e84393"])

        for p in self.particles:
            p[1] -= 0.8
            p[2] -= 0.015
        self.particles = [p for p in self.particles if p[2] > 0]

        self._draw_pet()
        self._draw_fx()
        self._draw_ui()
        self.root.after(FPS_MS, self._tick)

    def _poll(self):
        try:
            r = urllib.request.urlopen(f"http://{CONFIG['host']}:{CONFIG['port']}/api/state", timeout=1)
            self.sd = json.loads(r.read())
            self.mode = self.sd.get("mode", "sleep")
        except Exception:
            pass
        self.root.after(500, self._poll)

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    BuddyApp().run()
