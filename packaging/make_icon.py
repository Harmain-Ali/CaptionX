"""Writes assets/icon.ico (orange squircle with an X). Run:  python packaging/make_icon.py"""
from pathlib import Path

from PIL import Image, ImageDraw

S = 1024
img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
d = ImageDraw.Draw(img)
d.rounded_rectangle((0, 0, S - 1, S - 1), radius=int(S * 0.3), fill=(255, 76, 0, 255))
w, a, b = int(S * 0.105), int(S * 0.325), int(S * 0.675)
for p, q in (((a, a), (b, b)), ((b, a), (a, b))):
    d.line((*p, *q), fill=(10, 10, 10, 255), width=w)
for x, y in ((a, a), (b, b), (b, a), (a, b)):
    d.ellipse((x - w // 2, y - w // 2, x + w // 2, y + w // 2), fill=(10, 10, 10, 255))
out = Path(__file__).resolve().parent.parent / "assets" / "icon.ico"
out.parent.mkdir(exist_ok=True)
img.save(out, sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)])
print("wrote", out)
