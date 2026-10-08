"""Simulated impression: plates are inked, offset, grained and overprinted
onto washi with a subtractive (multiplicative) ink model."""
from dataclasses import dataclass

import numpy as np

from .filters import gaussian, shift
from .linework import StrokeBuffer
from .noise import Noise, grid, paper_tone, wood_grain


@dataclass
class Plate:
    name: str
    color: tuple            # 0..1 RGB
    cov: np.ndarray         # ink coverage 0..1
    register: bool = True   # subject to misregistration (key block: False)
    grain: float = 1.0      # wood-grain strength factor (0 = none)
    edge: bool = True       # ink pools at edges


def fibre_coverage(shape, seed, amount):
    """Sparse long fibres embedded in the paper."""
    h, w = shape
    n = int(amount * h * w / 9000.0)
    if n <= 0:
        return np.zeros(shape, np.float32)
    rng = np.random.default_rng(seed + 4242)
    buf = StrokeBuffer()
    steps = 24
    pos = np.column_stack([rng.uniform(0, w, n), rng.uniform(0, h, n)])
    ang = rng.uniform(0, 2 * np.pi, n)
    curl = rng.normal(0, 0.12, n)
    step = rng.uniform(0.8, 2.6, n)
    path = [pos.copy()]
    for _ in range(steps):
        ang = ang + curl + rng.normal(0, 0.05, n)
        pos = pos + np.column_stack([np.cos(ang), np.sin(ang)]) * step[:, None]
        path.append(pos.copy())
    path = np.stack(path, axis=1)
    widths = rng.uniform(0.25, 0.7, n)
    for i in range(n):
        buf.add(path[i], widths[i])
    return buf.rasterize(shape)


def emboss(field, azimuth=315.0):
    """Relief shading of a (blurred) field, roughly in [-1, 1]."""
    f = gaussian(field.astype(np.float32), 1.5)
    gy, gx = np.gradient(f)
    a = np.radians(azimuth)
    s = -(gx * np.sin(a) - gy * np.cos(a))
    q = np.quantile(np.abs(s), 0.995) + 1e-9
    return np.clip(s / q, -1.0, 1.0)


def impress(plates, paper_rgb, shape, p, emboss_field=None, progress=None):
    """Composite ``plates`` on paper; returns float RGB in [0, 1]."""
    h, w = shape
    rng = np.random.default_rng(p.seed + 101)
    paper = np.asarray(paper_rgb, dtype=np.float32)
    tone = paper_tone(shape, p.seed, p.paper_texture)
    img = tone[..., None] * paper[None, None, :]
    if p.fibres > 0:
        fib = fibre_coverage(shape, p.seed, p.fibres)
        dark = (rng.random() < 0.5)
        img *= (1.0 - 0.05 * fib)[..., None] if dark else (1.0 + 0.03 * fib)[..., None]
    x, y = grid(h, w)
    base_angle = rng.uniform(-8, 8)
    total = np.zeros(shape, np.float32)
    n = len(plates)
    for i, pl in enumerate(plates):
        if progress:
            progress(70 + int(25 * i / max(1, n)), "Printing plate: " + pl.name)
        cov = np.clip(pl.cov.astype(np.float32), 0.0, 1.0)
        if not cov.any():
            continue
        if pl.register and p.misregister > 0:
            d = np.clip(rng.normal(0, p.misregister, 2), -2.5 * p.misregister, 2.5 * p.misregister)
            cov = shift(cov, float(d[0]), float(d[1]))
        if pl.edge and p.edge_dark > 0:
            rim = np.clip(cov - gaussian(cov, 2.5), 0.0, 1.0)
            cov = np.clip(cov + 1.6 * p.edge_dark * rim, 0.0, 1.0)
        if pl.grain and p.grain > 0:
            g = wood_grain(shape, p.seed * 31 + i * 7 + 3,
                           angle_deg=base_angle + rng.uniform(-14, 14),
                           period=p.grain_period * rng.uniform(0.8, 1.25))
            cov = cov * (1.0 - p.grain * 0.75 * float(pl.grain) * g)
        if pl.grain and p.mottle > 0:
            m = Noise(p.seed * 17 + i).fbm(x / 55.0, y / 55.0, 3)
            cov = cov * (1.0 - p.mottle * np.clip((m - 0.35) * 2.0, 0.0, 1.0))
        col = np.asarray(pl.color, dtype=np.float32)
        img *= 1.0 - cov[..., None] * (1.0 - col[None, None, :])
        total = np.maximum(total, cov)
    if emboss_field is not None and p.karazuri > 0:
        s = emboss(emboss_field)
        bare = np.clip(1.0 - total, 0.0, 1.0)
        img *= (1.0 + 0.12 * p.karazuri * s * bare)[..., None]
    return np.clip(img, 0.0, 1.0)


def to_uint8(img):
    return (np.clip(img, 0, 1) * 255.0 + 0.5).astype(np.uint8)
