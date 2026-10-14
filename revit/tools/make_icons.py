"""Draw the ribbon icons (16 and 32 px) into BIMDelta.Revit/Resources. Needs Pillow.

python revit/tools/make_icons.py
"""

from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parent.parent / "BIMDelta.Revit" / "Resources"
BLUE = (37, 99, 235, 255)
WHITE = (255, 255, 255, 255)
GREEN = (22, 163, 74, 255)


def delta(draw: ImageDraw.ImageDraw, s: float, fill, box=(0.18, 0.2, 0.82, 0.78)) -> None:
    x0, y0, x1, y1 = (v * s for v in box)
    draw.polygon(
        [((x0 + x1) / 2, y0), (x1, y1), (x0, y1)], outline=fill, width=max(1, round(s / 11))
    )


def save_icon(size: int) -> Image.Image:
    s = size * 4  # draw large, scale down for smooth edges
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, s - 1, s - 1], radius=s // 6, fill=BLUE)
    delta(d, s, WHITE)
    r = s * 0.16
    cx, cy = s * 0.78, s * 0.78
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=GREEN, outline=WHITE, width=max(1, s // 32))
    return img.resize((size, size), Image.LANCZOS)


def viewer_icon(size: int) -> Image.Image:
    s = size * 4
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle(
        [0, 0, s - 1, s - 1], radius=s // 6, fill=WHITE, outline=BLUE, width=s // 14
    )
    delta(d, s, BLUE)
    for i, x in enumerate((0.3, 0.5, 0.7)):
        r = s * 0.05
        d.ellipse([x * s - r, 0.88 * s - r, x * s + r, 0.88 * s + r], fill=BLUE if i < 2 else GREEN)
    return img.resize((size, size), Image.LANCZOS)


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    for size in (16, 32):
        save_icon(size).save(OUT / f"save-{size}.png")
        viewer_icon(size).save(OUT / f"viewer-{size}.png")
    print(f"wrote icons to {OUT}")
