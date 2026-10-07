"""Pigment palettes modelled on traditional woodblock inks (sRGB 0-255).

Zone anchors run from low ground to summits; ``None`` means "no ink"
(bare paper, used for snow caps).  Colours are interpolated when the number
of zones differs from the number of anchors.
"""
import numpy as np

# Named pigments
WASHI = (241, 233, 214)
SUMI = (34, 32, 33)
BERO_AI = (31, 62, 112)        # Prussian blue
AI_LIGHT = (122, 156, 186)     # pale indigo
KUSA = (112, 136, 88)          # grass green
OLIVE = (160, 158, 102)
KIHADA = (214, 176, 98)        # yellow ochre
TAISHA = (172, 104, 66)        # red ochre
BENI = (190, 70, 58)           # safflower red
USUBENI = (232, 160, 132)

PRESETS = {
    "Hokusai - Prussian blue": dict(
        paper=WASHI,
        zones=[KUSA, OLIVE, KIHADA, BERO_AI, None],
        shade=(26, 44, 84), line=(28, 30, 42), hatch=(30, 46, 82),
        water=(56, 96, 150), sky=(36, 70, 124), glow=None,
        near=(44, 66, 60), far=(130, 158, 186),
    ),
    "Hokusai - Red Fuji": dict(
        paper=WASHI,
        # Gaifu kaisei: forest-green foot, iron-red (bengara) cone darkening
        # towards the summit, snow streaks, deep Prussian-blue sky
        zones=[(46, 84, 62), (120, 96, 58), (178, 62, 38), (160, 44, 30), (118, 32, 26), None],
        shade=(84, 24, 22), line=(34, 24, 24), hatch=(60, 30, 28),
        water=(40, 74, 128), sky=(26, 58, 118), glow=None,
        near=(36, 62, 52), far=(196, 92, 70),
        land_colour="height", sky_band=0.55,
    ),
    "Hiroshige - Dusk": dict(
        paper=(238, 230, 216),
        zones=[(110, 142, 100), (156, 160, 112), (126, 134, 156), (66, 82, 124), None],
        shade=(40, 40, 72), line=(34, 34, 48), hatch=(44, 46, 78),
        water=(68, 108, 158), sky=(30, 42, 92), glow=USUBENI,
        near=(38, 52, 68), far=(150, 156, 186),
    ),
    "Sumi monochrome": dict(
        paper=(238, 234, 224),
        zones=[(204, 200, 192), (166, 162, 156), (124, 120, 116), (84, 82, 80), None],
        shade=(30, 30, 30), line=(18, 18, 18), hatch=(26, 26, 26),
        water=(120, 124, 128), sky=(70, 70, 70), glow=None,
        near=(40, 40, 40), far=(176, 174, 168),
    ),
    "Shin-hanga - Snow": dict(
        paper=(244, 240, 232),
        zones=[(92, 110, 128), (124, 140, 160), (168, 180, 196), (208, 214, 224), None],
        shade=(70, 92, 132), line=(40, 46, 62), hatch=(72, 90, 126),
        water=(80, 112, 150), sky=(96, 120, 160), glow=(226, 190, 170),
        near=(54, 66, 84), far=(186, 196, 214),
    ),
}

DEFAULT_PRESET = "Hokusai - Prussian blue"


def rgb01(c):
    return None if c is None else tuple(v / 255.0 for v in c)


def get_preset(name):
    return PRESETS.get(name, PRESETS[DEFAULT_PRESET])


def zone_colors(preset, n, snow=True):
    """List of ``n`` colours (0..1 tuples or None) from low to high."""
    anchors = [c for c in preset["zones"] if c is not None]
    m = n - 1 if snow else n
    m = max(1, m)
    a = np.asarray(anchors, dtype=np.float64) / 255.0
    if m == 1:
        cols = [tuple(a[-1])]
    else:
        t = np.linspace(0.0, len(a) - 1, m)
        cols = []
        for ti in t:
            i = min(int(np.floor(ti)), len(a) - 2)
            f = ti - i
            cols.append(tuple(a[i] * (1 - f) + a[i + 1] * f))
    if snow:
        cols.append(None)
    return cols


def mix(c0, c1, t):
    return tuple(a * (1 - t) + b * t for a, b in zip(c0, c1))
