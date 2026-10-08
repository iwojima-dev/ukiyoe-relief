"""Plan-view (map) woodblock print of a DEM."""
import numpy as np

from .filters import (fill_nodata, gaussian, hillshade, rank01, ridge_strength,
                      sample)
from .linework import StrokeBuffer, add_isolines, taper
from .noise import Noise
from .posterize import classify, quantile_thresholds, sieve, soft_mask
from .presets import get_preset, rgb01, zone_colors
from .printing import Plate, impress
from . import water as W


def _noop(*_a, **_k):
    pass


def ridge_hatching(zg, land, cell, p, rng):
    """Strokes running downhill from ridge crests (ridge strokes)."""
    h, w = zg.shape
    buf = StrokeBuffer()
    if p.hatch_amount <= 0:
        return buf
    r = ridge_strength(zg, cell)
    if not land.any():
        return buf
    r = r / (np.quantile(r[land], 0.995) + 1e-12)
    thr = np.quantile(r[land], 1.0 - p.hatch_amount)
    s = p.hatch_spacing
    ys, xs = np.mgrid[s / 2:h:s, s / 2:w:s]
    xs = (xs + rng.uniform(-0.45, 0.45, xs.shape) * s).ravel()
    ys = (ys + rng.uniform(-0.45, 0.45, ys.shape) * s).ravel()
    xs = np.clip(xs, 0, w - 1.001)
    ys = np.clip(ys, 0, h - 1.001)
    rv = sample(r, xs, ys)
    lv = sample(land.astype(np.float32), xs, ys)
    keep = (rv > thr) & (lv > 0.99)
    xs, ys, rv = xs[keep], ys[keep], rv[keep]
    if xs.size == 0:
        return buf
    gr, gc = np.gradient(zg)
    mag = np.hypot(gr, gc)
    flat = np.quantile(mag[land], 0.05)
    length = p.hatch_length * (0.55 + 0.45 * np.clip(rv, 0, 1))
    steps = int(np.ceil(p.hatch_length))
    pts = np.empty((steps + 1, xs.size, 2))
    pts[0, :, 0], pts[0, :, 1] = xs, ys
    alive = np.ones(xs.size, bool)
    cx, cy = xs.copy(), ys.copy()
    for k in range(steps):
        dx = sample(gc, cx, cy)
        dy = sample(gr, cx, cy)
        m = np.hypot(dx, dy)
        alive &= m > flat
        m = np.maximum(m, 1e-12)
        cx = np.where(alive, cx - dx / m, cx)
        cy = np.where(alive, cy - dy / m, cy)
        pts[k + 1, :, 0], pts[k + 1, :, 1] = cx, cy
    for i in range(xs.size):
        n = int(max(2, min(steps, round(length[i])))) + 1
        q = pts[:n, i, :]
        if np.hypot(*(q[-1] - q[0])) < 2.0:
            continue
        t = np.linspace(0, 1, n)
        wv = p.hatch_width * (1.0 - t) ** 0.7 + 0.12
        buf.add(q, wv)
    return buf


def render_plan(dem, valid, cell, p, progress=_noop):
    """Return (plates, paper, emboss_field) ready for :func:`impress`."""
    preset = get_preset(p.preset)
    h, w = dem.shape
    rng = np.random.default_rng(p.seed)
    noise = Noise(p.seed + 55)

    progress(3, "Preparing relief")
    z = fill_nodata(dem, valid)
    zg = gaussian(z, p.generalize_px)
    hs = hillshade(zg, cell, p.sun_azimuth, p.sun_altitude, p.z_factor)

    water = W.detect(z, valid, p)
    if water.any():
        valid = valid | water          # NoData treated as sea becomes printable
    land = valid & ~water
    if not land.any():
        land = valid.copy()
        water[:] = False

    progress(10, "Posterising colour zones")
    rank_z = rank01(zg, land)
    rank_h = rank01(hs, land)
    field = (1.0 - p.light_mix) * rank_z + p.light_mix * rank_h
    field = gaussian(field, p.clean_px)
    n = int(p.n_zones)
    thr = quantile_thresholds(field[land], n,
                              p.snow_fraction if (p.snow_cap and n > 1) else None)
    zones = classify(field, thr)
    WATER, VOID = n, n + 1
    zones[water] = WATER
    zones[~valid] = VOID
    zones = sieve(zones, p.min_area_px)
    zones[water] = WATER
    zones[~valid] = VOID
    zones[land & (zones >= n)] = 0

    # Bokashi coordinate inside each zone: 0 at the lower edge, 1 at the upper
    edges = np.concatenate([[field[land].min()], thr, [field[land].max()]])
    k = np.clip(zones, 0, n - 1).astype(np.intp)
    lo, hi = edges[k], edges[k + 1]
    frac = np.clip((field - lo) / np.maximum(hi - lo, 1e-9), 0.0, 1.0)

    plates = []
    colors = zone_colors(preset, n, p.snow_cap)
    for zi, col in enumerate(colors):
        if col is None:
            continue
        m = soft_mask(zones, zi)
        if not m.any():
            continue
        cov = m * ((1.0 - p.bokashi) + p.bokashi * frac ** 0.85)
        plates.append(Plate("zone %d" % (zi + 1), col, cov))

    progress(25, "Shadow plates")
    shade_lv = np.zeros((h, w), np.uint8)
    if p.n_shade > 0:
        hr = gaussian(rank01(hs, valid), p.clean_px)
        qs = [p.shade_fraction * (0.42 ** j) for j in range(int(p.n_shade))]
        for q in qs:
            shade_lv += (hr < q).astype(np.uint8)
        shade_lv = sieve(shade_lv, p.min_area_px)
        shade_lv[~land] = 0
        lvl = gaussian(shade_lv.astype(np.float32), 0.6) / p.n_shade
        deep = np.clip(1.0 - hr / max(qs[0], 1e-6), 0.0, 1.0)
        cov = p.shade_density * np.clip(lvl, 0, 1) ** 0.75 * (0.8 + 0.2 * deep)
        plates.append(Plate("shadow", rgb01(preset["shade"]), cov))

    if water.any():
        progress(30, "Water plate")
        landf = land.astype(np.float32)
        near = gaussian(landf, max(4.0, 0.02 * max(h, w)))
        depth = np.clip(1.0 - 2.0 * near, 0.0, 1.0)
        cov = soft_mask(zones, WATER) * ((1.0 - p.bokashi) + p.bokashi * depth)
        plates.append(Plate("water", rgb01(preset["water"]), cov, grain=0.4))

    progress(35, "Cutting the key block")
    key = StrokeBuffer()
    dark = 1.0 - hs
    if p.keylines:
        for zi in range(1, n):
            ind = gaussian(((zones >= zi) & land).astype(np.float32), 0.8)
            add_isolines(key, ind, 0.5, width=p.line_width * min(1.0, (5.0 / n) ** 0.4),
                         noise=noise,
                         wobble_px=p.line_wobble, min_len=p.min_line_len,
                         width_field=dark, width_gain=0.9, phase=zi * 11.0)
        if water.any() or (~valid).any():
            ind = gaussian(land.astype(np.float32), 0.8)
            add_isolines(key, ind, 0.5, width=p.line_width * 1.15, noise=noise,
                         wobble_px=p.line_wobble, min_len=p.min_line_len, phase=97.0)
        if p.shade_lines and p.n_shade > 0:
            for j in range(1, int(p.n_shade) + 1):
                ind = gaussian((shade_lv >= j).astype(np.float32), 0.8)
                add_isolines(key, ind, 0.5, width=p.line_width * 0.55, noise=noise,
                             wobble_px=p.line_wobble, min_len=p.min_line_len * 2,
                             phase=200.0 + j)
    if water.any() and p.shore_lines > 0:
        landf = land.astype(np.float32)
        step = max(3.0, 0.008 * max(h, w))
        for j in range(1, int(p.shore_lines) + 1):
            ind = gaussian(landf, step * j)
            add_isolines(key, ind, 0.5 * np.exp(-0.35 * j) * 0.8, width=p.line_width * 0.5,
                         noise=noise, wobble_px=p.line_wobble * 1.5,
                         min_len=p.min_line_len * 2, phase=300.0 + j)

    progress(50, "Ridge hatching")
    hatch_cov = None
    if p.hatching:
        hb = ridge_hatching(zg, land, cell, p, rng)
        hatch_cov = hb.rasterize((h, w))

    progress(60, "Rasterising line work")
    key_cov = key.rasterize((h, w))
    if water.any():
        # echo lines belong to the water only
        key_cov = np.where(water, key_cov * 0.85, key_cov)
    if hatch_cov is not None:
        plates.append(Plate("hatching", rgb01(preset["hatch"]), hatch_cov * 0.9,
                            register=True, grain=False, edge=False))
    plates.append(Plate("key block", rgb01(preset["line"]), key_cov,
                        register=False, grain=False, edge=False))

    emboss_field = field.copy()
    emboss_field[~valid] = 0
    return plates, rgb01(preset["paper"]), emboss_field
