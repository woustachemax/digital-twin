import math
import os
import shutil
import subprocess
import sys
import tempfile

from PIL import Image, ImageChops, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
ICNS_PATH = os.path.join(HERE, "Twin.icns")
PREVIEW_PATH = os.path.join(HERE, "Twin-1024.png")

TILE = (20, 18, 27)
TILE_EDGE = (44, 41, 56)
LIME = (198, 255, 74)
LIME_SHADE = (158, 214, 36)
FACE = (17, 17, 17)
CHEEK = (255, 122, 184)
GROUND = (12, 11, 16)

SUPERSAMPLE = 4
ICONSET = [
    ("icon_16x16.png", 16), ("icon_16x16@2x.png", 32),
    ("icon_32x32.png", 32), ("icon_32x32@2x.png", 64),
    ("icon_128x128.png", 128), ("icon_128x128@2x.png", 256),
    ("icon_256x256.png", 256), ("icon_256x256@2x.png", 512),
    ("icon_512x512.png", 512), ("icon_512x512@2x.png", 1024),
]


def squircle(size, margin, exponent=5.0, steps=720):
    radius = (size - 2 * margin) / 2
    center = size / 2
    points = []
    for i in range(steps):
        angle = 2 * math.pi * i / steps
        c, s = math.cos(angle), math.sin(angle)
        x = center + radius * math.copysign(abs(c) ** (2 / exponent), c)
        y = center + radius * math.copysign(abs(s) ** (2 / exponent), s)
        points.append((x, y))
    return points


def ellipse_mask(size, box):
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse(box, fill=255)
    return mask


def fill(image, mask, color):
    image.paste(Image.new("RGBA", image.size, color + (255,)), (0, 0), mask)


def render(pixels):
    size = pixels * SUPERSAMPLE
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    detail = "full" if pixels >= 64 else ("medium" if pixels >= 48 else "tiny")

    margin = size * (100 / 1024) if pixels >= 64 else size * (60 / 1024)
    draw.polygon(squircle(size, margin), fill=TILE_EDGE + (255,))
    draw.polygon(squircle(size, margin + size * 0.006), fill=TILE + (255,))

    scale = {"full": 0.56, "medium": 0.64, "tiny": 0.74}[detail]
    body_w = size * scale
    body_h = body_w * (108 / 118)
    cx, cy = size / 2, size / 2 + size * 0.02
    left, top = cx - body_w / 2, cy - body_h / 2
    body_box = (left, top, left + body_w, top + body_h)

    if detail != "tiny":
        ground_w = body_w * 0.78
        ground_box = (cx - ground_w / 2, top + body_h * 0.93, cx + ground_w / 2, top + body_h * 1.05)
        fill(image, ellipse_mask(size, ground_box), GROUND)

    body = ellipse_mask(size, body_box)
    fill(image, body, LIME_SHADE)
    shift_x, shift_y = body_w * (10 / 118), body_h * (12 / 108)
    highlight = ellipse_mask(size, (left - shift_x, top - shift_y, left + body_w - shift_x, top + body_h - shift_y))
    fill(image, ImageChops.multiply(body, highlight), LIME)

    def at(fx, fy):
        return left + body_w * fx, top + body_h * fy

    eye_w = body_w * {"full": 12 / 118, "medium": 15 / 118, "tiny": 19 / 118}[detail]
    eye_h = body_h * {"full": 20 / 108, "medium": 22 / 108, "tiny": 24 / 108}[detail]
    eye_y = 0.43 if detail != "tiny" else 0.47
    for fx in (0.345, 0.600):
        ex, ey = at(fx, eye_y)
        draw.rounded_rectangle(
            (ex - eye_w / 2, ey - eye_h / 2, ex + eye_w / 2, ey + eye_h / 2), radius=eye_w / 2, fill=FACE + (255,),
        )

    if detail == "full":
        cheek_w, cheek_h = body_w * (16 / 118), body_h * (8 / 108)
        for fx in (0.235, 0.725):
            chx, chy = at(fx, 0.61)
            cheek = ellipse_mask(size, (chx - cheek_w / 2, chy - cheek_h / 2, chx + cheek_w / 2, chy + cheek_h / 2))
            fill(image, ImageChops.multiply(cheek, body), tuple(round(c * 0.7 + l * 0.3) for c, l in zip(CHEEK, LIME)))

    if detail != "tiny":
        mouth_w = body_w * (22 / 118)
        mx, my = at(0.472, 0.575)
        stroke = max(1, round(body_w * (3.4 / 118)))
        draw.arc((mx - mouth_w / 2, my - mouth_w / 2, mx + mouth_w / 2, my + mouth_w / 2), start=20, end=160,
                 fill=FACE + (255,), width=stroke)

    return image.resize((pixels, pixels), Image.LANCZOS)


def main():
    if shutil.which("iconutil") is None:
        sys.exit("iconutil not found: building .icns files needs macOS.")
    workdir = tempfile.mkdtemp(prefix="twin-icon-")
    iconset = os.path.join(workdir, "Twin.iconset")
    os.makedirs(iconset)
    try:
        cache = {}
        for name, pixels in ICONSET:
            if pixels not in cache:
                cache[pixels] = render(pixels)
            cache[pixels].save(os.path.join(iconset, name))
        cache[1024].save(PREVIEW_PATH)
        subprocess.run(["iconutil", "-c", "icns", iconset, "-o", ICNS_PATH], check=True)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
    print(f"wrote {ICNS_PATH} and {PREVIEW_PATH}")


if __name__ == "__main__":
    main()
