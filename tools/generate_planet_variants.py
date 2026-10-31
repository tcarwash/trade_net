#!/usr/bin/env python3
"""Create deterministic, pixel-level planet variants from the six PixelLab bases."""

from __future__ import annotations

import colorsys
import random
from pathlib import Path

from PIL import Image, ImageOps


ROOT = Path(__file__).resolve().parents[1] / "tradenet" / "web" / "assets" / "planets"
BASES = ("temperate", "desert", "ringed", "ice", "volcanic", "lush")
VARIANT_COUNT = 16
HUE_SHIFTS = (0.0, 0.045, -0.045, 0.075, -0.075, 0.105, -0.105, 0.025,
              0.055, -0.055, 0.09, -0.09, 0.125, -0.125, 0.035, -0.035)
HUE_SHIFT_SCALE = {"temperate": 1.0, "desert": 0.45, "ringed": 0.7,
                   "ice": 0.4, "volcanic": 0.35, "lush": 0.7}
SATURATION_SCALES = (1.0, 0.94, 1.06, 0.9, 1.1, 0.84, 1.15, 0.98,
                     0.88, 1.12, 0.92, 1.08, 0.82, 1.14, 0.96, 1.04)


def tinted(image: Image.Image, hue_shift: float, saturation_scale: float) -> Image.Image:
    """Shift surface hues while preserving alpha, luminance, and pixel edges."""
    result = image.copy()
    pixels = result.load()
    for y in range(result.height):
        for x in range(result.width):
            red, green, blue, alpha = pixels[x, y]
            if alpha == 0:
                continue
            hue, saturation, value = colorsys.rgb_to_hsv(red / 255, green / 255, blue / 255)
            if 0.12 < value < 0.94 and saturation > 0.12:
                red, green, blue = colorsys.hsv_to_rgb(
                    (hue + hue_shift) % 1.0,
                    min(1.0, saturation * saturation_scale),
                    value,
                )
                pixels[x, y] = (round(red * 255), round(green * 255), round(blue * 255), alpha)
    return result


def add_surface_marks(image: Image.Image, rng: random.Random) -> Image.Image:
    """Add small land, crater, or ice pixel clusters inside the globe silhouette."""
    result = image.copy()
    pixels = result.load()
    center_x, center_y = result.width // 2, result.height // 2
    candidates = []
    for y in range(result.height):
        for x in range(result.width):
            if (x - center_x) ** 2 + (y - center_y) ** 2 > 14**2:
                continue
            red, green, blue, alpha = pixels[x, y]
            if alpha > 180:
                hue, saturation, value = colorsys.rgb_to_hsv(red / 255, green / 255, blue / 255)
                if 0.2 < value < 0.82 and saturation > 0.15:
                    candidates.append((x, y, (red, green, blue, alpha)))
    if not candidates:
        return result

    patterns = (
        ((0, 0), (1, 0), (2, 0), (0, 1), (1, 1), (2, 1), (1, 2)),
        ((0, 0), (1, 0), (2, 0), (3, 0), (0, 1), (1, 1), (2, 1), (2, 2)),
        ((1, 0), (2, 0), (0, 1), (1, 1), (2, 1), (3, 1), (1, 2), (2, 2)),
        ((0, 0), (1, 0), (2, 0), (3, 0), (0, 1), (1, 1), (2, 1), (3, 1)),
        ((0, 0), (1, 0), (0, 1), (1, 1), (2, 1), (3, 1), (2, 2), (3, 2)),
    )
    for _ in range(rng.randint(9, 14)):
        x, y, color = rng.choice(candidates)
        pattern = rng.choice(patterns)
        mark_color = color[:3] + (min(color[3], rng.randint(160, 230)),)
        reflect_x, reflect_y = rng.choice((False, True)), rng.choice((False, True))
        for dx, dy in pattern:
            px = x + (-dx if reflect_x else dx)
            py = y + (-dy if reflect_y else dy)
            if not (0 <= px < result.width and 0 <= py < result.height):
                continue
            if (px - center_x) ** 2 + (py - center_y) ** 2 > 14**2:
                continue
            old = pixels[px, py]
            if old[3] > 180:
                pixels[px, py] = mark_color
    return result


def main() -> None:
    for planet_type in BASES:
        source = Image.open(ROOT / f"{planet_type}.png").convert("RGBA")
        for variant in range(VARIANT_COUNT):
            image = source.copy()
            style = variant % 8
            if style & 1:
                image = ImageOps.mirror(image)
            if style & 2:
                image = ImageOps.flip(image)
            if style == 4:
                image = image.transpose(Image.Transpose.ROTATE_90)
            elif style == 5:
                image = image.transpose(Image.Transpose.ROTATE_270)
            elif style == 6:
                image = image.transpose(Image.Transpose.TRANSPOSE)
            elif style == 7:
                image = image.transpose(Image.Transpose.TRANSVERSE)
            seed = sum((index + 1) * byte for index, byte in enumerate(f"{planet_type}:{variant}".encode()))
            rng = random.Random(seed)
            if variant:
                image = tinted(image, HUE_SHIFTS[variant] * HUE_SHIFT_SCALE[planet_type],
                               SATURATION_SCALES[variant])
                image = add_surface_marks(image, rng)
            image.save(ROOT / f"{planet_type}-{variant}.png", optimize=True)


if __name__ == "__main__":
    main()
