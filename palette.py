"""
Neon palettes and their precomputed 256-entry lookup tables.

Each figure is assigned one LUT (cycled by spawn index) so multiple companions
are visually distinguishable.  LUTs are built once at import; the hot drawing
path only does an index-and-mask, never a colour interpolation.
"""

# Palette key colours (interpolated into smooth LUTs below) -----------------
PAL_BLUE = [
    (0x00, 0xFF, 0xFF), (0xA0, 0xF0, 0xFF), (0x00, 0x00, 0xFF),
    (0x0A, 0x0A, 0x60), (0x0A, 0x0A, 0x0A),
]
PAL_PINK = [
    (0x34, 0xED, 0xF3), (0xF7, 0x15, 0xAB), (0x92, 0x01, 0xCB), (0x03, 0x13, 0xA6),
]
PAL_GREEN = [
    (0x39, 0xFF, 0x14), (0x00, 0xFF, 0xC8), (0x0A, 0x3A, 0x0A), (0xCC, 0xFF, 0x00),
]
PAL_GOLD = [
    (0xFF, 0xD7, 0x00), (0xFF, 0x6A, 0x00), (0x3A, 0x1A, 0x00), (0xFF, 0xF0, 0x99),
]

LUT_MASK = 255


def build_lut(palette, size=256):
    """Interpolate `palette` key colours into a `size`-entry RGB lookup table."""
    n = len(palette)
    lut = []
    for i in range(size):
        t = i / size * n
        lo = int(t) % n
        hi = (lo + 1) % n
        f = t - int(t)
        r = int(palette[lo][0] + (palette[hi][0] - palette[lo][0]) * f)
        g = int(palette[lo][1] + (palette[hi][1] - palette[lo][1]) * f)
        b = int(palette[lo][2] + (palette[hi][2] - palette[lo][2]) * f)
        lut.append((r, g, b))
    return lut


LUT_BLUE  = build_lut(PAL_BLUE)
LUT_PINK  = build_lut(PAL_PINK)
LUT_GREEN = build_lut(PAL_GREEN)
LUT_GOLD  = build_lut(PAL_GOLD)

# Cycled per figure by spawn index.
LUTS = [LUT_BLUE, LUT_PINK, LUT_GREEN, LUT_GOLD]


def lut_for_index(i):
    return LUTS[i % len(LUTS)]
