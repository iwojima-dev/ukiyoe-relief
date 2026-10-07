"""Layered-landscape mode: an oblique view in which receding depth bands are
printed as separate plates (aerial perspective), Hiroshige-style."""
import math

import numpy as np

from .filters import fill_nodata, gaussian, hillshade, rank01, sample
from .linework import (StrokeBuffer, add_isolines, add_polylines, arclength, isolines,
                       resample, trace_columns)
from .noise import Noise
from .presets import get_preset, mix, rgb01, zone_colors
from .printing import Plate
from . import water as W


def _noop(*_a, **_k):
    pass


def _inscribed(w, h, angle):
    """Largest axis-aligned rectangle inside a w x h rectangle rotated by angle."""
    if w <= 0 or h <= 0:
        return 0, 0
    a = abs(math.sin(angle))
    c = abs(math.cos(angle))
    long_side, short_side = (w, h) if w >= h else (h, w)
    if short_side <= 2.0 * a * c * long_side or abs(a - c) < 1e-10:
        x = 0.5 * short_side
        wr, hr = (x / a, x / c) if w >= h else (x / c, x / a)
    else:
        cos2 = c * c - a * a
        wr, hr = (w * c - h * a) / cos2, (h * c - w * a) / cos2
    return wr, hr


def rotate_view(arrays, valid, azimuth, out_width=None):
    """Resample so that the view direction (azimuth) points up the image.

    The rotated DEM is cropped to the largest inscribed rectangle and then
    resampled so that its width is ``out_width`` px (the sheet width), so
    the print size does not depend on the view direction.
    Returns (arrays, validity, scale) where scale = output px per DEM cell.
    """
    h, w = valid.shape
    A = math.radians(azimuth)
    ca, sa = math.cos(A), math.sin(A)
    wr, hr = _inscribed(w, h, A)
    wr, hr = wr - 2.0, hr - 2.0
    if wr < 8 or hr < 8:
        raise ValueError("DEM window too small for this view direction.")
    scale = 1.0 if not out_width else float(out_width) / wr
    nw = max(8, int(round(wr * scale)))
    nh = max(8, int(round(hr * scale)))
    dx = (np.arange(nw, dtype=np.float64)[None, :] - (nw - 1) / 2.0) / scale
    dy = (np.arange(nh, dtype=np.float64)[:, None] - (nh - 1) / 2.0) / scale
    xs = (w - 1) / 2.0 + dx * ca - dy * sa
    ys = (h - 1) / 2.0 + dx * sa + dy * ca
    out = [sample(a, xs, ys).astype(np.float32) for a in arrays]
    v = sample(valid.astype(np.float32), xs, ys) > 0.999
    return out, v, scale


def _project(sy_f, owner, c, r, tol):
    """Screen rows of ground-grid points (c, r) and their visibility."""
    hs_, w = owner.shape
    y = sample(sy_f, c, r)
    xi = np.clip(np.round(c).astype(int), 0, w - 1)
    yi = np.round(y).astype(int)
    inside = (yi >= 0) & (yi < hs_)
    yi = np.clip(yi, 0, hs_ - 1)
    own = owner[yi, xi]
    vis = inside & (own >= 0) & (np.abs(own - r) <= tol)
    return y, vis


def _runs(mask):
    """(start, stop) index pairs of True runs."""
    d = np.diff(np.concatenate([[0], mask.astype(np.int8), [0]]))
    return list(zip(np.flatnonzero(d == 1), np.flatnonzero(d == -1)))


def interior_lines(d_c, d2_c, land_grid, sy_f, owner, count, min_len):
    """The few strongest ridge / gully lines inside the silhouette.

    Crest and thalweg lines are where the slope across the view changes
    sign (d_c = 0); their strength is the curvature across them.  Only
    visible stretches are kept, ranked by length x strength x nearness.
    Returns [(kind, (N, 2) screen polyline)], kind = 'ridge' | 'gully'.
    """
    if count <= 0 or not land_grid.any():
        return []
    hd = d_c.shape[0]
    tol = max(2.0, 0.004 * hd)
    neg, pos = -d2_c[land_grid], d2_c[land_grid]
    sr = np.clip(-d2_c / (np.quantile(neg[neg > 0], 0.98) + 1e-12 if (neg > 0).any() else 1), 0, 1.5)
    sg = np.clip(d2_c / (np.quantile(pos[pos > 0], 0.98) + 1e-12 if (pos > 0).any() else 1), 0, 1.5)
    lg = land_grid.astype(np.float32)
    cand = []
    for ln in isolines(d_c, 0.0):
        q = resample(ln, 1.0)
        if len(q) < 4:
            continue
        c, r = q[:, 0], q[:, 1]
        y, vis = _project(sy_f, owner, c, r, tol)
        ok_land = sample(lg, c, r) > 0.99
        for kind, st in (("ridge", sample(sr, c, r)), ("gully", sample(sg, c, r))):
            ok = ok_land & vis & (st > 0.3)
            for a, b in _runs(ok):
                if b - a < 3:
                    continue
                pts = np.column_stack([c[a:b], y[a:b]])
                L = arclength(pts)[-1]
                if L < min_len:
                    continue
                near = 1.0 - float(r[a:b].mean()) / hd
                cand.append((L * float(st[a:b].mean()) * near ** 1.5, kind, pts))
    cand.sort(key=lambda x: -x[0])
    return [(k, pts) for _s, k, pts in cand[:int(count)]]


def render_oblique(dem, valid, cell, p, progress=_noop):
    """Return (plates, paper, emboss_field, shape)."""
    preset = get_preset(p.preset)
    noise = Noise(p.seed + 77)

    progress(3, "Preparing relief")
    z = fill_nodata(dem, valid)
    wgrid = W.detect(z, valid, p)
    if wgrid.any():
        valid = valid | wgrid
        z = np.where(wgrid, np.minimum(z, p.water_level), z)  # flat sea surface
    zg = gaussian(z, p.generalize_px)
    if wgrid.any():
        zg = np.where(wgrid, p.water_level, np.maximum(zg, p.water_level))
    hs = hillshade(zg, cell, p.sun_azimuth, p.sun_altitude, p.z_factor)
    cs = 0.5 * (cell[0] + cell[1])
    # Geometry (silhouettes, summits, craters) uses a lightly smoothed DEM;
    # the strong generalisation above only drives plates and shadows.
    zgeo = gaussian(z, p.silhouette_px)
    if wgrid.any():
        zgeo = np.where(wgrid, p.water_level, np.maximum(zgeo, p.water_level))

    progress(8, "Turning toward the view")
    (zr, hsr, wr, zgr), vr, scale = rotate_view(
        [zg, hs, wgrid.astype(np.float32), zgeo], valid, p.view_azimuth,
        out_width=p.max_size)
    cs = cs / scale              # ground size of one resampled cell
    hd, w = zr.shape
    zr = np.flipud(zr)          # row 0 = nearest
    hsr = np.flipud(hsr)
    zgr = np.flipud(zgr)
    wr = np.flipud(wr) > 0.5
    vr = np.flipud(vr)

    th = math.radians(p.tilt)
    zmin = float(zgr[vr].min()) if vr.any() else 0.0
    ztop = float(np.quantile(zgr[vr], 0.999)) if vr.any() else zmin + 1.0
    zrange = max(ztop - zmin, 1e-6)
    # normalised height and the relief curve: gamma > 1 keeps the foothills
    # low and steepens the upper slopes - the concave flanks of a print Fuji
    zn = np.clip((zgr - zmin) / zrange, 0.0, None)
    zc = zmin + zrange * zn ** p.relief_gamma
    i = np.arange(hd, dtype=np.float64)[:, None]
    ex = p.exaggeration
    if p.exag_mode == "Auto" and vr.any():
        # automatic exaggeration: highest relief = given share of sheet width
        ex = p.relief_height / 100.0 * w / (zrange / cs * math.cos(th))
    lift = (zc - zmin) / cs * ex * math.cos(th)
    up = i * math.sin(th) + lift                 # height above the near edge, px
    up = np.where(vr, up, -np.inf)
    # crop the foreground "skirt": start the sheet at the highest point
    # of the near edge so no vertical streaks hang below the terrain
    near_up = up[0][np.isfinite(up[0])]
    floor_up = float(near_up.max()) if near_up.size else 0.0
    up = up - floor_up
    top = float(np.max(up[np.isfinite(up)]))
    terrain_h = top + 2.0
    sky = p.sky_fraction * terrain_h
    hs_ = int(math.ceil(terrain_h + sky))
    # limit runaway heights
    hs_ = min(hs_, 4 * max(w, hd))
    base = hs_ - 1.0
    sy = base - up                                # screen row of every DEM cell

    progress(15, "Painter's sweep")
    # owner[i] = nearest row whose running-minimum screen row reaches pixel y
    m = np.minimum.accumulate(np.where(np.isfinite(sy), sy, np.inf), axis=0)
    yy = np.arange(hs_, dtype=np.float64)
    owner = np.full((hs_, w), -1, dtype=np.int32)
    neg = -m
    for x in range(w):
        idx = np.searchsorted(neg[:, x], -yy, side="left")
        idx[idx >= hd] = -1
        owner[:, x] = idx
    sky_m = owner < 0
    oi = np.where(sky_m, 0, owner)
    cols = np.broadcast_to(np.arange(w)[None, :], owner.shape)
    zpix = zr[oi, cols]
    hpix = hsr[oi, cols]

    progress(25, "Depth layers")
    n = int(p.n_layers)
    terrain = ~sky_m
    water = terrain & wr[oi, cols]
    land = terrain & ~water
    depth = np.where(sky_m, 1.0, oi / max(hd - 1, 1)).astype(np.float32)

    # --- silhouettes: a visible point whose upper neighbour is sky or lies
    # much farther away.  Only these are real edges of a "kulisse".
    jump = max(2, int(0.01 * hd))
    above = np.vstack([np.full((1, w), -1, np.int32), owner[:-1]])
    sil = land & ((above < 0) | (above - owner > jump))
    # drop speckle: keep pixels that continue sideways (+-1 row, 7 px)
    sky_edge = land & (above < 0)          # skyline: always a real edge
    sv = sil.copy()
    for dy in range(1, 4):                 # tolerate steep flanks
        sv[dy:] |= sil[:-dy]
        sv[:-dy] |= sil[dy:]
    run = np.zeros((hs_, w), np.int16)
    for dx in range(-3, 4):
        run += np.roll(sv, dx, axis=1)
    sil &= (run >= 5) | sky_edge
    # trace silhouettes into polylines; short bumps are dropped
    min_sil = int(max(p.min_line_len, 0.02 * w))
    sil_lines = [ln for ln in trace_columns(sil, max_dy=12, min_len=3)
                 if arclength(ln)[-1] >= min_sil]
    sil_long = np.zeros((hs_, w), bool)
    for ln in sil_lines:
        xi = np.clip(np.round(ln[:, 0]).astype(int), 0, w - 1)
        yi = np.clip(np.round(ln[:, 1]).astype(int), 0, hs_ - 1)
        sil_long[yi, xi] = True

    # --- colour plates: distance slices with equal LAND area.  Inside a
    # slice the plate is flat; between slices on an open slope the colours
    # blend over a soft riser, so no false ridge appears.  At silhouettes
    # depth itself jumps, so the colour changes crisply there by itself.
    qs = (np.quantile(depth[land], np.linspace(0, 1, n + 1)) if land.any()
          else np.linspace(0, 1, n + 1))
    qs = np.maximum.accumulate(qs + np.arange(n + 1) * 1e-7)
    lc = np.clip(np.interp(depth, qs, np.arange(n + 1)) - 0.5, 0.0, n - 1.0)
    fl = np.floor(lc)
    riser = 0.4
    lc = fl + np.clip((lc - fl - (1.0 - riser)) / riser, 0.0, 1.0) ** 2 * \
        (3.0 - 2.0 * np.clip((lc - fl - (1.0 - riser)) / riser, 0.0, 1.0))
    lc = np.minimum(lc, n - 1.0).astype(np.float32)
    t = np.where(land, lc / max(n - 1, 1), np.where(water, depth, 0.0)).astype(np.float32)

    # --- bokashi: ink fades downward from every silhouette (and from the
    # shore line of land seen beyond water)
    land_above = np.vstack([np.zeros((1, w), bool), land[:-1]])
    src = sil_long | (land & ~land_above)
    rows = np.arange(hs_)[:, None] * np.ones((1, w), dtype=np.int64)
    last = np.maximum.accumulate(np.where(src, rows, 0), axis=0)
    dist = rows - last
    L = max(2.0, p.ridge_bokashi * hs_)
    ridge_fade = gaussian(np.exp(-dist / L).astype(np.float32), (0.7, max(3.0, 0.6 * L)))

    # --- terrain form on the (rotated) ground grid, shared by snow,
    # and interior lines
    land_grid = vr & ~wr
    zs = gaussian(zgr, max(1.0, 1.5 * scale))
    d_c = np.gradient(zs, axis=1)            # across the view
    d2_c = np.gradient(d_c, axis=1)
    lap = d2_c + np.gradient(np.gradient(zs, axis=0), axis=0)
    lap_sd = float(np.std(lap[land_grid])) + 1e-9 if land_grid.any() else 1.0
    conc = np.clip(lap / lap_sd, -3.0, 3.0)  # > 0 gully, < 0 ridge

    # --- snow: the snow line drops into gullies and retreats on ridges,
    # giving the "fingers" of a printed Fuji
    snow = np.zeros_like(land)
    if p.snow_cap and p.snow_fraction > 0 and land_grid.any():
        # fingers follow the larger gullies only: curvature at a coarser scale
        zs2 = gaussian(zgr, max(3.0, 0.006 * w))
        lap2 = np.gradient(np.gradient(zs2, axis=1), axis=1) + \
            np.gradient(np.gradient(zs2, axis=0), axis=0)
        conc2 = np.clip(lap2 / (float(np.std(lap2[land_grid])) + 1e-9), -3.0, 3.0)
        score = zn + p.snow_fingers * 0.05 * conc2
        thr = np.quantile(score[land_grid], 1.0 - p.snow_fraction)
        snow_grid = land_grid & (score >= thr)
        snow_grid = gaussian(snow_grid.astype(np.float32), max(1.0, 1.2 * scale)) > 0.5
        snow = land & snow_grid[oi, cols]

    near_c = rgb01(preset["near"])
    far_c = rgb01(preset["far"])
    plates = []
    by_height = (p.land_colour == "Height (zones)" or
                 (p.land_colour == "Palette default" and preset.get("land_colour") == "height"))
    if by_height:
        # elevation zones (equal visible area), ink graded inside each zone
        # (bokashi darkening upwards) and faded with distance
        hz = zn[oi, cols]
        nz = int(p.n_zones)
        zcols = zone_colors(preset, nz, snow=False)
        hv = hz[land]
        qz = np.quantile(hv, np.linspace(0, 1, nz + 1)) if hv.size else np.linspace(0, 1, nz + 1)
        qz = np.maximum.accumulate(qz + np.arange(nz + 1) * 1e-7)
        # continuous zone coordinate: neighbouring plates blend and overlap,
        # as printers overlapped blocks - no paper seams between zones
        zc_ = np.clip(np.interp(hz, qz, np.arange(nz + 1)) - 0.5, 0.0, nz - 1.0)
        cont_depth = np.where(land, depth, 0.0)
        dens = 1.0 - p.aerial * 0.35 * cont_depth
        grad = (1.0 - p.bokashi) + p.bokashi * (0.6 + 0.4 * np.clip(hz, 0, 1))
        body = land & ~snow
        for b in range(nz):
            hat = np.where(body, np.clip(1.0 - np.abs(zc_ - b) * 0.8, 0.0, 1.0), 0.0)
            if not hat.any():
                continue
            m_b = np.clip(gaussian(hat.astype(np.float32), 1.0) * 1.15, 0, 1)
            cov = m_b * dens * grad * (0.85 + 0.15 * ridge_fade)
            plates.append(Plate("zone %d" % (b + 1), zcols[b], cov))
    for b in (range(0) if by_height else range(n)):
        tb = b / max(n - 1, 1)
        hat = np.where(land & ~snow, np.clip(1.0 - np.abs(lc - b), 0.0, 1.0), 0.0)
        if not hat.any():
            continue
        m_b = np.clip(gaussian(hat.astype(np.float32), 0.6) * 1.1, 0, 1)
        dens = 1.0 - p.aerial * tb * 0.75
        cov = m_b * dens * ((1.0 - p.bokashi) + p.bokashi * ridge_fade)
        col = mix(near_c, far_c, tb)
        plates.append(Plate("layer %d" % (b + 1), col, cov))

    if water.any():
        wm = np.clip(gaussian(water.astype(np.float32), 0.5) * 1.25 - 0.125, 0, 1)
        cov = wm * (1.0 - 0.45 * p.aerial * depth) * ((1.0 - 0.5 * p.bokashi)
                                                       + 0.5 * p.bokashi * depth)
        plates.append(Plate("water", rgb01(preset["water"]), cov, grain=0.4))

    progress(35, "Shadow plate")
    if p.n_shade > 0 and terrain.any():
        # classify shadows on the terrain grid, then project: shapes stay
        # coherent and get foreshortened like the surface itself
        hr = gaussian(rank01(gaussian(hsr, 2.0 * p.generalize_px * scale), vr),
                      2.0 * max(p.clean_px, 1.0) * scale)
        lv_grid = np.zeros_like(hr)
        for j in range(int(p.n_shade)):
            lv_grid += (hr < p.shade_fraction * (0.42 ** j))
        lvl = lv_grid[oi, cols] / p.n_shade
        lvl = np.where(snow, 0.6 * lvl, lvl)
        lvl = gaussian(np.where(land, lvl, 0.0), 0.6)
        fade = 1.0 - 0.6 * p.aerial * t
        cov = p.shade_density * np.clip(lvl, 0, 1) ** 0.75 * fade
        plates.append(Plate("shadow", rgb01(preset["shade"]), cov))

    progress(42, "Sky")
    horizon = np.where(terrain.any(axis=0), np.argmax(terrain, axis=0), hs_)
    yv = np.arange(hs_, dtype=np.float32)[:, None]
    skyf = np.clip(gaussian(sky_m.astype(np.float32), 0.6) * 1.25 - 0.125, 0, 1)
    band_h = max(4.0, preset.get("sky_band", 0.18) * (np.median(horizon) + 1))
    cov = p.sky_density * np.exp(-yv / band_h) * skyf
    plates.append(Plate("sky", rgb01(preset["sky"]), cov))
    if preset.get("glow"):
        hz = float(np.median(horizon))
        g = np.exp(-((yv - hz) / max(6.0, 0.25 * hz)) ** 2) * skyf * 0.8
        plates.append(Plate("glow", rgb01(preset["glow"]), g * np.ones((1, w))))

    progress(50, "Cutting the key block")
    key = StrokeBuffer()
    dark = 1.0 - hpix
    nearness = 1.0 - 0.6 * t
    if p.keylines:
        # true silhouettes, traced into smooth brush strokes
        add_polylines(key, sil_lines, width=p.line_width * 1.15, noise=noise,
                      wobble_px=p.line_wobble, width_field=nearness, width_gain=0.8,
                      phase=7.0)
        sb = gaussian(snow.astype(np.float32), 0.8)
        add_isolines(key, sb, 0.5, width=p.line_width * 0.6, noise=noise,
                     wobble_px=p.line_wobble, min_len=p.min_line_len, phase=401.0)
        if water.any():
            wb = gaussian(water.astype(np.float32), 0.8)
            add_isolines(key, wb, 0.5, width=p.line_width * 0.8, noise=noise,
                         wobble_px=p.line_wobble, min_len=p.min_line_len, phase=503.0)
        # a few interior lines along the strongest ridges and gullies
        sy_f = np.where(np.isfinite(sy), sy, -1e6)
        for kind, pts in interior_lines(d_c, d2_c, land_grid, sy_f, owner,
                                        p.interior_lines, 1.5 * min_sil):
            add_polylines(key, [pts], width=p.line_width * (0.8 if kind == "ridge" else 0.6),
                          noise=noise, wobble_px=p.line_wobble, phase=611.0 + len(pts))
        if p.slice_lines:
            # old style: every distance-slice border as a thin line
            lay = np.where(land, np.floor(lc + 0.5), np.where(sky_m, n + 1, -1))
            for b in range(1, n):
                ind = gaussian((lay >= b).astype(np.float32), 0.8)
                add_isolines(key, ind, 0.5, width=p.line_width * 0.5, noise=noise,
                             wobble_px=p.line_wobble, min_len=p.min_line_len,
                             phase=b * 13.0)
    key_cov = key.rasterize((hs_, w))
    if water.any():
        open_water = gaussian(water.astype(np.float32), 1.5) > 0.98
        key_cov = np.where(open_water, 0.0, key_cov)

    plates.append(Plate("key block", rgb01(preset["line"]), key_cov,
                        register=False, grain=False, edge=False))
    emboss_field = np.where(sky_m, 0.0, 1.0 - t).astype(np.float32)
    return plates, rgb01(preset["paper"]), emboss_field, (hs_, w)
