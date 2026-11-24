"""把绿幕视频抽出的全分辨率 RGBA 帧，处理成各尺寸的「平滑 alpha」帧。

步骤：
1. 去绿边（g 压到 max(r,b)）
2. 在预乘 alpha 空间缩放，避免透明区域的绿色渗进边缘
3. 还原成直通 alpha，保存为 RGBA PNG（供分层窗口逐像素透明使用）

用法：
    ffmpeg -i 02_孙笑川站立_绿幕循环_11.1s_1920x1080.mp4 ^
      -vf "chromakey=0x00ff00:0.10:0.05,crop=355:1001:821:51" ^
      -r 15 -pix_fmt rgba _tmp/raw/f_%%04d.png
    python tools/build_frames.py
"""
import glob
import os

import numpy as np
from PIL import Image, ImageFilter

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW_DIR = os.path.join(BASE, "_tmp", "raw")
OUT_ROOT = os.path.join(BASE, "frames")
SIZES = {
    "75": 0.75,
    "100": 1.00,
    "125": 1.25,
    "150": 1.50,
}
BASE_W, BASE_H = 128, 360  # 100% 档的显示尺寸
ALPHA_FLOOR = 0.004


def process_frame(path, size):
    rgba = np.array(Image.open(path).convert("RGBA"))
    rgb = rgba[:, :, :3].astype(np.float32)
    alpha = rgba[:, :, 3].astype(np.float32) / 255.0

    # 去绿边：g 压到 (r+b)/2，比 max(r,b) 更彻底
    rgb[:, :, 1] = np.minimum(
        rgb[:, :, 1], (rgb[:, :, 0] + rgb[:, :, 2]) / 2
    )

    # 先腐蚀 1px，把最外圈残留的绿边裁掉，再做软边缩放
    alpha_img = Image.fromarray((alpha * 255).astype(np.uint8), "L")
    alpha_img = alpha_img.filter(ImageFilter.MinFilter(3))
    alpha = np.array(alpha_img).astype(np.float32) / 255.0

    # 预乘 alpha 后缩放（RGB 和 A 分开缩放，避免边缘串色）
    premul = np.clip(rgb * alpha[:, :, None], 0, 255).astype(np.uint8)
    alpha_u8 = np.clip(alpha * 255, 0, 255).astype(np.uint8)

    premul_small = np.array(
        Image.fromarray(premul, "RGB").resize(size, Image.LANCZOS)
    ).astype(np.float32)
    alpha_small = (
        np.array(Image.fromarray(alpha_u8, "L").resize(size, Image.LANCZOS)).astype(
            np.float32
        )
        / 255.0
    )

    safe = np.maximum(alpha_small, 1e-3)
    color = np.clip(premul_small / safe[:, :, None], 0, 255)
    color[alpha_small < ALPHA_FLOOR] = 0

    out = np.empty((size[1], size[0], 4), dtype=np.uint8)
    out[:, :, :3] = color.astype(np.uint8)
    out[:, :, 3] = np.clip(alpha_small * 255, 0, 255).astype(np.uint8)
    return out


def main():
    files = sorted(glob.glob(os.path.join(RAW_DIR, "*.png")))
    if not files:
        raise SystemExit(f"没有找到原始帧：{RAW_DIR}")
    base_w, base_h = Image.open(files[0]).size
    print(f"原始帧 {len(files)} 张，{base_w}x{base_h}")

    for tag, scale in SIZES.items():
        out_dir = os.path.join(OUT_ROOT, tag)
        os.makedirs(out_dir, exist_ok=True)
        for old in glob.glob(os.path.join(out_dir, "*.png")):
            os.remove(old)

        size = (round(BASE_W * scale), round(BASE_H * scale))
        for i, path in enumerate(files, 1):
            Image.fromarray(process_frame(path, size), "RGBA").save(
                os.path.join(out_dir, f"f_{i:04d}.png"), optimize=True
            )
        print(f"frames/{tag}: {len(files)} 张，{size[0]}x{size[1]}")


if __name__ == "__main__":
    main()
