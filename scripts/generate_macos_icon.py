#!/usr/bin/env python3
"""Generate a macOS .iconset from AnySpark's purple spark visual language."""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter


def make_base(size: int = 1024) -> Image.Image:
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))

    # Rounded macOS icon tile with a subtle diagonal violet gradient.
    tile = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    pixels = tile.load()
    for y in range(size):
        for x in range(size):
            t = (x + y) / (2 * (size - 1))
            pixels[x, y] = (
                int(38 + 54 * t),
                int(17 + 23 * t),
                int(76 + 92 * t),
                255,
            )
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle((48, 48, size - 48, size - 48), radius=220, fill=255)
    image.alpha_composite(Image.composite(tile, Image.new("RGBA", tile.size), mask))

    # Soft cyan/violet energy glow behind the mark.
    glow = Image.new("RGBA", image.size, (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow)
    glow_draw.ellipse((130, 150, 900, 920), fill=(108, 45, 255, 165))
    glow_draw.ellipse((430, 120, 940, 650), fill=(48, 197, 255, 150))
    glow = glow.filter(ImageFilter.GaussianBlur(105))
    image.alpha_composite(glow)

    # The spark/bolt is intentionally close to the existing favicon silhouette.
    bolt = [
        (490, 116),
        (830, 116),
        (630, 398),
        (842, 398),
        (410, 908),
        (410, 614),
        (176, 614),
        (370, 346),
        (174, 346),
    ]
    shadow = Image.new("RGBA", image.size, (0, 0, 0, 0))
    ImageDraw.Draw(shadow).polygon([(x + 18, y + 28) for x, y in bolt], fill=(9, 4, 32, 135))
    shadow = shadow.filter(ImageFilter.GaussianBlur(24))
    image.alpha_composite(shadow)

    mark = Image.new("RGBA", image.size, (0, 0, 0, 0))
    mark_draw = ImageDraw.Draw(mark)
    mark_draw.polygon(bolt, fill=(242, 237, 255, 255))
    mark_draw.line(bolt + [bolt[0]], fill=(255, 255, 255, 210), width=10, joint="curve")
    image.alpha_composite(mark)

    # Gloss kept faint so the icon still reads clearly at 16 px.
    gloss = Image.new("RGBA", image.size, (0, 0, 0, 0))
    ImageDraw.Draw(gloss).ellipse((100, 40, 920, 570), fill=(255, 255, 255, 34))
    gloss = gloss.filter(ImageFilter.GaussianBlur(55))
    image.alpha_composite(gloss)
    return image


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: generate_macos_icon.py OUTPUT.iconset|OUTPUT.icns", file=sys.stderr)
        return 2

    output = Path(sys.argv[1])
    if output.suffix.lower() == ".icns":
        output.parent.mkdir(parents=True, exist_ok=True)
        make_base().save(output, format="ICNS")
        return 0

    output_dir = output
    output_dir.mkdir(parents=True, exist_ok=True)
    base = make_base()

    for logical_size in (16, 32, 128, 256, 512):
        for scale in (1, 2):
            pixels = logical_size * scale
            suffix = "@2x" if scale == 2 else ""
            output = output_dir / f"icon_{logical_size}x{logical_size}{suffix}.png"
            base.resize((pixels, pixels), Image.Resampling.LANCZOS).save(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
