"""Generate the Noteration app icon (.ico + .icns + .png) from scratch.

No source artwork existed, so this draws a simple, recognizable mark: an "N"
monogram in white on the app's indigo accent, in a rounded square. Re-run to
tweak:  python packaging/make_icon.py

Outputs into packaging/assets/.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ASSETS = Path(__file__).resolve().parent / "assets"
ASSETS.mkdir(parents=True, exist_ok=True)

SIZE = 1024
INDIGO_TOP = (99, 102, 241)     # indigo-500
INDIGO_BOTTOM = (67, 56, 202)   # indigo-700
WHITE = (255, 255, 255)


def _rounded_mask(size: int, radius: int) -> Image.Image:
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, size - 1, size - 1], radius=radius, fill=255)
    return mask


def _gradient(size: int) -> Image.Image:
    grad = Image.new("RGB", (size, size), INDIGO_TOP)
    px = grad.load()
    for y in range(size):
        t = y / (size - 1)
        r = round(INDIGO_TOP[0] + (INDIGO_BOTTOM[0] - INDIGO_TOP[0]) * t)
        g = round(INDIGO_TOP[1] + (INDIGO_BOTTOM[1] - INDIGO_TOP[1]) * t)
        b = round(INDIGO_TOP[2] + (INDIGO_BOTTOM[2] - INDIGO_TOP[2]) * t)
        for x in range(size):
            px[x, y] = (r, g, b)
    return grad


def _load_font(px: int) -> ImageFont.FreeTypeFont:
    for candidate in (r"C:\Windows\Fonts\segoeuib.ttf", r"C:\Windows\Fonts\arialbd.ttf"):
        if Path(candidate).is_file():
            return ImageFont.truetype(candidate, px)
    return ImageFont.load_default()


def build() -> Image.Image:
    base = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    bg = _gradient(SIZE).convert("RGBA")
    base.paste(bg, (0, 0), _rounded_mask(SIZE, radius=int(SIZE * 0.22)))

    draw = ImageDraw.Draw(base)
    font = _load_font(int(SIZE * 0.62))
    text = "N"
    box = draw.textbbox((0, 0), text, font=font)
    w, h = box[2] - box[0], box[3] - box[1]
    pos = ((SIZE - w) / 2 - box[0], (SIZE - h) / 2 - box[1])
    draw.text(pos, text, font=font, fill=WHITE)
    return base


def main() -> None:
    icon = build()

    png = ASSETS / "noteration.png"
    icon.save(png)

    ico_sizes = [(s, s) for s in (16, 24, 32, 48, 64, 128, 256)]
    icon.save(ASSETS / "noteration.ico", sizes=ico_sizes)

    # ICNS requires square power-of-two sizes; Pillow picks from the source.
    icns = icon.resize((1024, 1024))
    icns.save(ASSETS / "noteration.icns")

    print(f"Wrote {png.name}, noteration.ico, noteration.icns to {ASSETS}")


if __name__ == "__main__":
    main()
