"""Generate the application icon (installer/app.ico) — a thermoelectric motif.

Teal rounded tile with a hot->cold gradient bar and 'TE' monogram.
Multi-resolution .ico (16..256) so it looks crisp in the taskbar, Start Menu,
Explorer, and the installer.
"""
import os
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
TEAL = (47, 111, 122)
DARK = (31, 41, 55)
HOT  = (220, 60, 50)
COLD = (37, 99, 235)
WHITE = (255, 255, 255)

def _font(size):
    for name in ("segoeuib.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except Exception:
            continue
    return ImageFont.load_default()

def render(px):
    S = px * 4  # supersample
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    r = int(S * 0.20)
    d.rounded_rectangle([0, 0, S - 1, S - 1], radius=r, fill=DARK)
    # hot -> cold vertical gradient bar on the left
    bx0, bx1 = int(S * 0.16), int(S * 0.30)
    by0, by1 = int(S * 0.18), int(S * 0.82)
    for y in range(by0, by1):
        f = (y - by0) / (by1 - by0)
        col = tuple(int(HOT[i] + (COLD[i] - HOT[i]) * f) for i in range(3))
        d.rectangle([bx0, y, bx1, y + 1], fill=col)
    d.rounded_rectangle([bx0, by0, bx1, by1], radius=int(S*0.03), outline=WHITE, width=max(1, S//128))
    # 'TE' monogram
    f = _font(int(S * 0.42))
    txt = "TE"
    tb = d.textbbox((0, 0), txt, font=f)
    tw, th = tb[2] - tb[0], tb[3] - tb[1]
    d.text((int(S * 0.38) - tb[0], (S - th) // 2 - tb[1]), txt, font=f, fill=(120, 200, 210))
    return img.resize((px, px), Image.LANCZOS)

sizes = [16, 24, 32, 48, 64, 128, 256]
imgs = [render(s) for s in sizes]
out = os.path.join(HERE, "app.ico")
imgs[0].save(out, format="ICO", sizes=[(s, s) for s in sizes], append_images=imgs[1:])
# also a PNG for the installer wizard image / docs
render(256).save(os.path.join(HERE, "app.png"))
print("wrote", out)
