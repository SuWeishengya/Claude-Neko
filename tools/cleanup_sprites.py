#!/usr/bin/env python3
"""
精灵图边缘清理工具 v2 — 基于黑色轮廓线的 flood fill 清理。

策略：
  1. 找出黑色轮廓线 + 不透明主体 → 构成不可穿透的屏障
  2. 从图片四边 flood fill，屏障外所有像素 → 删除
  3. 星星（happy）和冒泡（think）的不透明彩色元素自然处于屏障内，自动保护

效果：只有黑线闭合区域外的噪点/色块被清除，线内全部保留。
"""

import argparse
import os
import sys
import numpy as np
from PIL import Image
from scipy import ndimage
from collections import deque

# ---------------------------------------------------------------------------
# 可调参数
# ---------------------------------------------------------------------------
BLACK_EDGE_DARKNESS = 100   # 亮度 < 此值判定为黑线
BLACK_EDGE_MIN_ALPHA = 60   # 黑线最低 alpha（兼顾半透明黑边）
OPAQUE_MIN_ALPHA = 200      # 不透明主体阈值
BARRIER_DILATION = 0         # 屏障膨胀像素（0=不膨胀，更激进）
BARRIER_CLOSE = 1            # 形态学闭运算迭代（填补黑线小缺口）


def build_barrier(arr: np.ndarray) -> np.ndarray:
    """构建屏障 mask：黑线 + 不透明主体。"""
    h, w = arr.shape[:2]
    r, g, b, a = arr[:, :, 0], arr[:, :, 1], arr[:, :, 2], arr[:, :, 3]
    darkness = (r + g + b) / 3.0

    # 黑色轮廓线
    black_edge = (darkness < BLACK_EDGE_DARKNESS) & (a > BLACK_EDGE_MIN_ALPHA)
    # 不透明主体（猫、爱心、星星、冒泡等）
    opaque = a > OPAQUE_MIN_ALPHA

    barrier = black_edge | opaque

    # 形态学闭运算：填补黑线上的小缺口
    if BARRIER_CLOSE > 0:
        barrier = ndimage.binary_closing(barrier, iterations=BARRIER_CLOSE)

    # 膨胀：可选，关闭极小缝隙
    if BARRIER_DILATION > 0:
        barrier = ndimage.binary_dilation(barrier, iterations=BARRIER_DILATION)

    return barrier


def flood_fill_outside(barrier: np.ndarray) -> np.ndarray:
    """从四边 flood fill，返回屏障外所有像素的 mask。"""
    h, w = barrier.shape
    outside = np.zeros((h, w), dtype=bool)

    q = deque()

    def seed(y, x):
        if not barrier[y, x] and not outside[y, x]:
            outside[y, x] = True
            q.append((y, x))

    # 初始化：四条边
    for y in range(h):
        seed(y, 0)
        seed(y, w - 1)
    for x in range(w):
        seed(0, x)
        seed(h - 1, x)

    # BFS
    while q:
        y, x = q.popleft()
        for ny, nx in [(y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)]:
            if 0 <= ny < h and 0 <= nx < w:
                if not barrier[ny, nx] and not outside[ny, nx]:
                    outside[ny, nx] = True
                    q.append((ny, nx))

    return outside


def cleanup_image(src_path: str, dst_path: str) -> dict:
    """清理单张精灵图。"""
    img = Image.open(src_path).convert("RGBA")
    arr = np.array(img, dtype=np.float32)
    h, w = arr.shape[:2]
    alpha = arr[:, :, 3]

    # 构建屏障
    barrier = build_barrier(arr)

    # Flood fill 找外部区域
    outside = flood_fill_outside(barrier)

    # 统计
    n_outside = int(np.sum(outside & (alpha > 0)))

    # 删除外部所有像素
    arr[outside, 3] = 0

    # 保存
    arr = np.clip(arr, 0, 255).astype(np.uint8)
    os.makedirs(os.path.dirname(dst_path), exist_ok=True)
    Image.fromarray(arr, "RGBA").save(dst_path)

    return {
        "file": src_path,
        "outside_removed": n_outside,
        "barrier_pct": barrier.sum() / (h * w) * 100,
    }


def main():
    parser = argparse.ArgumentParser(description="清理精灵图 — 基于黑色轮廓线的 flood fill")
    parser.add_argument("input", help="输入文件或目录")
    parser.add_argument("-o", "--output", help="输出目录（默认: <input>_clean）")
    parser.add_argument("--dry-run", action="store_true", help="只分析不保存")
    args = parser.parse_args()

    # 收集文件
    input_path = args.input
    if os.path.isfile(input_path):
        files = [input_path]
    elif os.path.isdir(input_path):
        files = []
        for root, _, filenames in os.walk(input_path):
            for fn in sorted(filenames):
                if fn.lower().endswith(".png"):
                    files.append(os.path.join(root, fn))
    else:
        print(f"错误: 找不到 {input_path}")
        sys.exit(1)

    if not files:
        print("没有找到 PNG 文件")
        sys.exit(1)

    # 输出目录
    if args.output:
        out_dir = args.output
    elif os.path.isdir(input_path):
        out_dir = input_path.rstrip("/") + "_clean"
    else:
        out_dir = os.path.dirname(input_path)

    print(f"找到 {len(files)} 个 PNG 文件")
    print(f"参数: black_edge_darkness<{BLACK_EDGE_DARKNESS}, "
          f"black_edge_alpha>{BLACK_EDGE_MIN_ALPHA}, "
          f"opaque_alpha>{OPAQUE_MIN_ALPHA}, "
          f"barrier_close={BARRIER_CLOSE}, barrier_dilation={BARRIER_DILATION}")
    if args.dry_run:
        print(">>> DRY RUN 模式，不保存文件 <<<")
    print()

    total_removed = 0
    for f in files:
        rel = os.path.relpath(f, input_path) if os.path.isdir(input_path) else os.path.basename(f)
        out = os.path.join(out_dir, rel)

        stats = cleanup_image(f, out)
        nr = stats["outside_removed"]
        total_removed += nr

        action = "跳过" if args.dry_run else "已保存"
        print(f"  {rel}: 移除外部像素 {nr}, 屏障占比 {stats['barrier_pct']:.1f}% → {action}")

    print()
    print(f"总计移除外部像素: {total_removed}")


if __name__ == "__main__":
    main()
