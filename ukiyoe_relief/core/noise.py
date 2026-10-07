"""Deterministic procedural noise: value noise, fBm, wood grain, washi paper."""
import numpy as np


class Noise:
    """Seeded lattice value noise with a periodic lookup table."""

    def __init__(self, seed, size=512):
        rng = np.random.default_rng(int(seed) & 0xFFFFFFFF)
        self.size = size
        self.table = rng.random((size, size), dtype=np.float32)

    def value(self, u, v):
        """Smooth value noise in [0, 1] at lattice coordinates (u, v)."""
        u = np.asarray(u, dtype=np.float32)
        v = np.asarray(v, dtype=np.float32)
        u, v = np.broadcast_arrays(u, v)
        i0 = np.floor(u)
        j0 = np.floor(v)
        fu = u - i0
        fv = v - j0
        fu = fu * fu * (3.0 - 2.0 * fu)
        fv = fv * fv * (3.0 - 2.0 * fv)
        p = self.size
        i0 = i0.astype(np.int64) % p
        j0 = j0.astype(np.int64) % p
        i1 = (i0 + 1) % p
        j1 = (j0 + 1) % p
        t = self.table
        a = t[j0, i0]
        b = t[j0, i1]
        c = t[j1, i0]
        d = t[j1, i1]
        top = a + (b - a) * fu
        bot = c + (d - c) * fu
        return top + (bot - top) * fv

    def fbm(self, u, v, octaves=4, lacunarity=2.0, gain=0.5):
        """Fractal sum of value noise, normalised to [0, 1]."""
        total = 0.0
        amp = 1.0
        norm = 0.0
        freq = 1.0
        for k in range(octaves):
            off = 17.31 * (k + 1)
            total = total + amp * self.value(u * freq + off, v * freq - off)
            norm += amp
            amp *= gain
            freq *= lacunarity
        return total / norm


def grid(h, w):
    y = np.arange(h, dtype=np.float32)[:, None]
    x = np.arange(w, dtype=np.float32)[None, :]
    return x, y


def wood_grain(shape, seed, angle_deg=0.0, period=7.0, warp=1.0, sharpness=2.0):
    """Plank texture in [0, 1]: warped growth rings plus long fibres.

    High values mark where the block surface holds less ink.  ``angle_deg``
    is the direction of the fibres (0 = horizontal).
    """
    h, w = shape
    nz = Noise(seed)
    x, y = grid(h, w)
    a = np.radians(angle_deg)
    u = x * np.cos(a) + y * np.sin(a)          # along the fibres
    v = -x * np.sin(a) + y * np.cos(a)         # across the fibres
    big = nz.fbm(u / (period * 40.0), v / (period * 6.0), 3)
    rings = 0.5 + 0.5 * np.sin(2.0 * np.pi * (v + warp * period * 3.0 * (big - 0.5)) / period)
    rings = rings ** sharpness
    fibres = nz.fbm(u / (period * 9.0) + 101.0, v / (period * 0.45), 2)
    fibres = np.clip((fibres - 0.35) * 1.8, 0.0, 1.0)
    g = 0.6 * rings + 0.4 * fibres
    return np.clip(g, 0.0, 1.0).astype(np.float32)


def paper_tone(shape, seed, strength=0.5):
    """Multiplicative brightness field of hand-made washi (around 1.0)."""
    h, w = shape
    nz = Noise(seed + 9001)
    x, y = grid(h, w)
    cloud = nz.fbm(x / 160.0, y / 160.0, 4) - 0.5
    mid = nz.fbm(x / 14.0 + 3.3, y / 14.0, 2) - 0.5
    fine = nz.value(x / 1.7 + 7.7, y / 1.7) - 0.5
    return (1.0 + strength * (0.07 * cloud + 0.035 * mid + 0.03 * fine)).astype(np.float32)
