"""Raster filters used by the renderer (pure numpy, no SciPy).

All functions work on 2-D float arrays in image index space: axis 0 = rows
(southward), axis 1 = columns (eastward).
"""
import numpy as np


def gaussian(a, sigma):
    """Separable Gaussian blur with symmetric (mirror) boundary.

    Implemented in the frequency domain on a mirrored extension, which makes
    the boundary handling exact for any sigma.  ``sigma`` may be a scalar or
    a (sigma_rows, sigma_cols) pair, in pixels.
    """
    out = np.asarray(a, dtype=np.float32)
    if np.isscalar(sigma):
        sy = sx = float(sigma)
    else:
        sy, sx = (float(s) for s in sigma)
    touched = False
    for axis, s in ((0, sy), (1, sx)):
        if s < 0.25:
            continue
        n = out.shape[axis]
        ext = np.concatenate([out, np.flip(out, axis=axis)], axis=axis)
        spec = np.fft.rfft(ext, axis=axis)
        f = np.fft.rfftfreq(2 * n)
        g = np.exp(-2.0 * (np.pi * s * f) ** 2).astype(np.float32)
        shape = [1, 1]
        shape[axis] = -1
        spec *= g.reshape(shape)
        res = np.fft.irfft(spec, n=2 * n, axis=axis)
        out = (res[:n] if axis == 0 else res[:, :n]).astype(np.float32)
        touched = True
    return out if touched else out.copy()


def fill_nodata(z, valid, max_iter=10):
    """Fill invalid cells by normalised convolution with growing radius."""
    z = np.asarray(z, dtype=np.float32)
    if valid.all():
        return z.copy()
    if not valid.any():
        raise ValueError("The DEM window contains no valid cells.")
    base = np.where(valid, z, 0.0).astype(np.float32)
    weight = valid.astype(np.float32)
    out = base.copy()
    filled = valid.copy()
    s = 2.0
    for _ in range(max_iter):
        num = gaussian(base, s)
        den = gaussian(weight, s)
        ok = (~filled) & (den > 1e-4)
        out[ok] = num[ok] / den[ok]
        filled |= ok
        if filled.all():
            break
        s *= 2.0
    out[~filled] = float(z[valid].mean())
    return out


def gradients(z, cell):
    """Return dz/dEast and dz/dNorth (cell = (cx, cy) in metres)."""
    cx, cy = cell
    d_row, d_col = np.gradient(z, cy, cx)
    return d_col.astype(np.float32), (-d_row).astype(np.float32)


def hillshade(z, cell, azimuth=315.0, altitude=40.0, z_factor=1.0):
    """Lambertian hillshade in [0, 1]; azimuth clockwise from north."""
    dzdx, dzdn = gradients(z, cell)
    dzdx *= z_factor
    dzdn *= z_factor
    az = np.radians(azimuth)
    alt = np.radians(altitude)
    lx, ly, lz = np.sin(az) * np.cos(alt), np.cos(az) * np.cos(alt), np.sin(alt)
    norm = np.sqrt(dzdx * dzdx + dzdn * dzdn + 1.0)
    hs = (-dzdx * lx - dzdn * ly + lz) / norm
    return np.clip(hs, 0.0, 1.0).astype(np.float32)


def ridge_strength(z, cell):
    """Convexity across the ridge: -min eigenvalue of the Hessian, >= 0."""
    cx, cy = cell
    gx, gn = gradients(z, cell)
    gxx = np.gradient(gx, axis=1) / cx
    gnn = -np.gradient(gn, axis=0) / cy
    gxn = -np.gradient(gx, axis=0) / cy
    tr = 0.5 * (gxx + gnn)
    d = np.sqrt((0.5 * (gxx - gnn)) ** 2 + gxn ** 2)
    return np.maximum(0.0, -(tr - d)).astype(np.float32)


def rank01(a, valid):
    """Percentile rank of valid values, scaled to [0, 1]; invalid -> 0."""
    out = np.zeros(a.shape, dtype=np.float32)
    v = a[valid]
    if v.size == 0:
        return out
    order = np.argsort(v, kind="stable")
    r = np.empty(v.size, dtype=np.float32)
    r[order] = np.linspace(0.0, 1.0, v.size, dtype=np.float32)
    out[valid] = r
    return out


def sample(field, x, y):
    """Bilinear sample of ``field`` at column ``x`` / row ``y`` (arrays)."""
    h, w = field.shape
    x = np.clip(x, 0.0, w - 1.001)
    y = np.clip(y, 0.0, h - 1.001)
    x0 = np.floor(x).astype(np.intp)
    y0 = np.floor(y).astype(np.intp)
    fx = x - x0
    fy = y - y0
    a = field[y0, x0]
    b = field[y0, x0 + 1]
    c = field[y0 + 1, x0]
    d = field[y0 + 1, x0 + 1]
    return (a * (1 - fx) + b * fx) * (1 - fy) + (c * (1 - fx) + d * fx) * fy


def _shift_int(a, ix, iy):
    h, w = a.shape
    out = np.empty_like(a)
    ys = slice(max(0, -iy), min(h, h - iy))
    yd = slice(max(0, iy), min(h, h + iy))
    xs = slice(max(0, -ix), min(w, w - ix))
    xd = slice(max(0, ix), min(w, w + ix))
    out[...] = 0.0
    out[yd, xd] = a[ys, xs]
    return out


def shift(a, dx, dy):
    """Translate by a sub-pixel offset (positive dx = right, dy = down)."""
    ix, iy = int(np.floor(dx)), int(np.floor(dy))
    fx, fy = dx - ix, dy - iy
    a00 = _shift_int(a, ix, iy)
    a10 = _shift_int(a, ix + 1, iy)
    a01 = _shift_int(a, ix, iy + 1)
    a11 = _shift_int(a, ix + 1, iy + 1)
    return ((a00 * (1 - fx) + a10 * fx) * (1 - fy)
            + (a01 * (1 - fx) + a11 * fx) * fy).astype(np.float32)


def smoothstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)
