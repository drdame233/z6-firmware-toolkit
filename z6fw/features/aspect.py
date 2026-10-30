"""Aspect-ratio presets: 21:9 and the largest frame with both edges divisible by 32.

Both presets reuse the stock 16:9 slot (aspect_id 4, camera area 2) and only change
the height fields of the three 16:9 records. Widths stay at the factory values, so
every edit is a single 16-bit write and the module length never changes.
"""
from __future__ import annotations

from fractions import Fraction

from ..patch import Edit
from ..platform import z6_380 as P

# Presets: name -> (ratio as width/height, note)
PRESETS = {
    "aspect-21x9": (Fraction(7, 3), "21:9 (2.3333)"),
    "aspect-max32": (Fraction(6048, 4000), "6048x4000, both edges divisible by 32"),
}

_HEIGHT_OFFSETS = {
    "L": P.OFF_H_169_L,
    "M": P.OFF_H_169_M,
    "S": P.OFF_H_169_S,
}


def quantize4(value: float) -> int:
    """Round to the nearest multiple of four, as the factory size table does."""
    return int(round(value / 4.0)) * 4


def target_sizes(ratio: Fraction) -> dict[str, tuple[int, int, int]]:
    """Return {'L': (w, h, edge32_ok), ...} for a width/height ratio."""
    out = {}
    for q, w in P.STOCK_169_WIDTH.items():
        h = quantize4(float(Fraction(w, 1) / ratio))
        out[q] = (w, h, w % 32 == 0 and h % 32 == 0)
    return out


def build_edits(preset: str) -> list[Edit]:
    """Edits that turn the stock 16:9 slot into the requested aspect."""
    if preset not in PRESETS:
        raise ValueError("unknown preset %r (known: %s)" % (preset, ", ".join(PRESETS)))
    ratio, _ = PRESETS[preset]
    edits = []
    for q, (w, h, _ok) in target_sizes(ratio).items():
        stock_h = P.STOCK_169_HEIGHT[q]
        if h == stock_h:
            continue
        if not (0 < h <= 4024):
            raise ValueError("%s height %d is outside the sensor" % (q, h))
        off = _HEIGHT_OFFSETS[q]
        edits.append(Edit(off,
                          stock_h.to_bytes(2, "little"),
                          h.to_bytes(2, "little"),
                          "%s %s height %d -> %d" % (preset, q, stock_h, h)))
    return edits


def describe(preset: str) -> dict:
    ratio, note = PRESETS[preset]
    sizes = target_sizes(ratio)
    return {
        "preset": preset,
        "note": note,
        "ratio": float(ratio),
        "sizes": {q: {"width": w, "height": h, "edge32": ok} for q, (w, h, ok) in sizes.items()},
        "slot": "stock 16:9 (aspect_id 4, camera area 2)",
        "edits": len(build_edits(preset)),
        "crop_geometry_patched": P.CROP_GEOMETRY_PATCHED,
        "status": ("size table only; sensor window unchanged"
                   if not P.CROP_GEOMETRY_PATCHED else "size table + crop window"),
        "risk": ("STRETCH: the camera will resample the existing 16:9 window into the new "
                 "height instead of cropping. Do not flash until crop geometry is patched."
                 if not P.CROP_GEOMETRY_PATCHED else "crop window patched"),
    }
