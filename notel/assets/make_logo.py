# SPDX-License-Identifier: Apache-2.0
"""Render the notel storefront logo: the upstream logo with a red "NO" stamp.

Run from the repo root:
  docker run --rm -v "$PWD:/w" -w /w python:3.12-slim sh -c \
    "apt-get update -qq && apt-get install -y -qq fonts-dejavu-core >/dev/null \
     && pip install -q pillow==11.3.0 && python notel/assets/make_logo.py"
"""
from PIL import Image, ImageDraw, ImageFont

SRC = "src/image-provider/static/opentelemetry-demo-logo.png"
OUT = "notel/assets/notel-demo-logo.png"
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

RED = (214, 32, 39)
STAMP_W, STAMP_H = 560, 250
BORDER = 22
ANGLE = 12
CENTER = (1335, 258)


def stamp():
    pad = 40
    layer = Image.new("RGBA", (STAMP_W + 2 * pad, STAMP_H + 2 * pad), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    box = (pad, pad, pad + STAMP_W, pad + STAMP_H)
    d.rounded_rectangle(box, radius=28, fill=(255, 255, 255, 235), outline=RED + (255,), width=BORDER)
    font = ImageFont.truetype(FONT, 200)
    cx, cy = layer.width / 2, layer.height / 2
    d.text((cx, cy), "NO", font=font, fill=RED + (255,), anchor="mm")
    return layer.rotate(ANGLE, resample=Image.BICUBIC, expand=True)


def main():
    logo = Image.open(SRC).convert("RGBA")
    s = stamp()
    pos = (int(CENTER[0] - s.width / 2), int(CENTER[1] - s.height / 2))
    logo.alpha_composite(s, dest=pos)
    logo.save(OUT, optimize=True)
    print(f"wrote {OUT} {logo.size}")


if __name__ == "__main__":
    main()
