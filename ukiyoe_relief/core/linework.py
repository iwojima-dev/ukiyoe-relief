"""Key-block line work: isolines, smoothing, hand wobble, variable-width
brush strokes and their anti-aliased rasterisation (matplotlib Agg)."""
import numpy as np

from .filters import sample

try:  # shipped with matplotlib >= 3.6
    import contourpy
except ImportError:  # pragma: no cover
    contourpy = None


def isolines(field, level):
    """Polylines (N x 2 arrays of col, row) where ``field`` crosses ``level``."""
    field = np.asarray(field, dtype=np.float64)
    if contourpy is not None:
        gen = contourpy.contour_generator(z=field, line_type=contourpy.LineType.Separate)
        return [np.asarray(l, dtype=np.float64) for l in gen.lines(level) if len(l) > 1]
    from matplotlib.figure import Figure
    ax = Figure().add_subplot()
    cs = ax.contour(field, levels=[level])
    out = []
    for path in cs.get_paths():
        for poly in path.to_polygons(closed_only=False):
            if len(poly) > 1:
                out.append(np.asarray(poly, dtype=np.float64))
    return out


def _closed(p):
    return len(p) > 3 and np.hypot(*(p[0] - p[-1])) < 1e-6


def resample(p, step):
    """Resample a polyline at constant arc-length spacing."""
    seg = np.hypot(*np.diff(p, axis=0).T)
    s = np.concatenate([[0.0], np.cumsum(seg)])
    total = s[-1]
    if total < step:
        return p
    n = max(2, int(np.ceil(total / step)) + 1)
    t = np.linspace(0.0, total, n)
    return np.column_stack([np.interp(t, s, p[:, 0]), np.interp(t, s, p[:, 1])])


def smooth(p, window):
    """Moving-average smoothing along a polyline (ends kept for open lines)."""
    k = int(window)
    if k < 2 or len(p) < 2 * k + 1:
        return p
    ker = np.ones(2 * k + 1) / (2 * k + 1)
    if _closed(p):
        q = p[:-1]
        ext = np.vstack([q[-k:], q, q[:k]])
        sm = np.column_stack([np.convolve(ext[:, i], ker, mode="valid") for i in (0, 1)])
        return np.vstack([sm, sm[:1]])
    ext = np.vstack([np.repeat(p[:1], k, 0), p, np.repeat(p[-1:], k, 0)])
    sm = np.column_stack([np.convolve(ext[:, i], ker, mode="valid") for i in (0, 1)])
    sm[0], sm[-1] = p[0], p[-1]
    return sm


def arclength(p):
    return np.concatenate([[0.0], np.cumsum(np.hypot(*np.diff(p, axis=0).T))])


def wobble(p, noise, amplitude, scale=25.0, phase=0.0):
    """Displace vertices along the normal by 1-D noise: a hand-cut line."""
    if amplitude <= 0 or len(p) < 3:
        return p
    s = arclength(p)
    t = np.gradient(p, axis=0)
    t /= np.maximum(np.hypot(t[:, 0], t[:, 1]), 1e-9)[:, None]
    n = np.column_stack([-t[:, 1], t[:, 0]])
    off = (noise.value(s / scale + phase, np.full_like(s, phase * 0.37)) - 0.5) * 2.0 * amplitude
    return p + n * off[:, None]


def taper(s, total, length, floor=0.2):
    """Brush pressure profile: thin at both ends of the stroke."""
    if length <= 0:
        return np.ones_like(s)
    e = np.minimum(s, total - s) / length
    return floor + (1.0 - floor) * np.sqrt(np.clip(e, 0.0, 1.0))


class StrokeBuffer:
    """Accumulates variable-width segments for one ink plate."""

    def __init__(self):
        self._segs = []
        self._widths = []

    def add(self, pts, widths):
        if len(pts) < 2:
            return
        w = np.asarray(widths, dtype=np.float64)
        if w.ndim == 0:
            w = np.full(len(pts), float(w))
        seg = np.stack([pts[:-1], pts[1:]], axis=1)
        self._segs.append(seg)
        self._widths.append(0.5 * (w[:-1] + w[1:]))

    def __len__(self):
        return sum(len(s) for s in self._segs)

    def rasterize(self, shape):
        """Anti-aliased coverage in [0, 1] (1 = full ink)."""
        h, w = shape
        if not self._segs:
            return np.zeros(shape, dtype=np.float32)
        from matplotlib.figure import Figure
        from matplotlib.backends.backend_agg import FigureCanvasAgg
        from matplotlib.collections import LineCollection
        dpi = 72.0  # 1 pt == 1 px
        fig = Figure(figsize=(w / dpi, h / dpi), dpi=dpi)
        canvas = FigureCanvasAgg(fig)
        fig.patch.set_facecolor("white")
        ax = fig.add_axes([0, 0, 1, 1])
        ax.set_axis_off()
        ax.set_xlim(0, w)
        ax.set_ylim(h, 0)
        segs = np.concatenate(self._segs) + 0.5  # index -> pixel centre
        widths = np.concatenate(self._widths)
        lc = LineCollection(segs, linewidths=widths, colors="black",
                            capstyle="round", joinstyle="round", antialiased=True)
        ax.add_collection(lc)
        canvas.draw()
        buf = np.asarray(canvas.buffer_rgba())[..., 0].astype(np.float32)
        out = np.zeros(shape, dtype=np.float32)
        hh, ww = min(h, buf.shape[0]), min(w, buf.shape[1])
        out[:hh, :ww] = 1.0 - buf[:hh, :ww] / 255.0
        return out


def add_isolines(buf, field, level, *, width, noise, wobble_px=0.0, min_len=10.0,
                 smooth_px=3, width_field=None, width_gain=0.0, taper_px=12.0,
                 phase=0.0):
    """Trace ``field == level`` and add tapered, wobbly strokes to ``buf``.

    ``width_field`` (0..1) thickens the line where it is high (e.g. shadow).
    """
    for k, line in enumerate(isolines(field, level)):
        p = resample(line, 1.0)
        s = arclength(p)
        if s[-1] < min_len:
            continue
        p = smooth(p, smooth_px)
        p = wobble(p, noise, wobble_px, phase=phase + 3.1 * k)
        p = resample(p, 1.5)
        s = arclength(p)
        wv = np.full(len(p), width, dtype=np.float64)
        if width_field is not None and width_gain:
            f = sample(width_field, p[:, 0], p[:, 1])
            wv *= (1.0 - 0.5 * width_gain) + width_gain * f
        if not _closed(p):
            wv *= taper(s, s[-1], taper_px)
        buf.add(p, wv)


def trace_columns(mask, max_dy=4, min_len=8):
    """Link per-column hits of a thin horizontal-ish mask into polylines.

    Silhouettes found column by column (one pixel per column per edge) are
    chained left-to-right: a hit continues the chain whose last row is the
    closest within ``max_dy``.  Returns a list of (N, 2) arrays (col, row).
    """
    h, w = mask.shape
    active = []          # list of [last_row, points]
    done = []
    for x in range(w):
        ys = np.flatnonzero(mask[:, x])
        # collapse runs of adjacent rows to their centre
        if ys.size:
            br = np.flatnonzero(np.diff(ys) > 1)
            starts = np.concatenate([[0], br + 1])
            ends = np.concatenate([br, [ys.size - 1]])
            ys = 0.5 * (ys[starts] + ys[ends])
        used = np.zeros(len(active), bool)
        new_active = []
        for y in ys:
            best, bd = -1, max_dy + 1
            for k, (ly, _pts) in enumerate(active):
                if not used[k]:
                    d = abs(ly - y)
                    if d < bd:
                        best, bd = k, d
            if best >= 0:
                used[best] = True
                ch = active[best]
                ch[0] = y
                ch[1].append((x, y))
                new_active.append(ch)
            else:
                new_active.append([y, [(x, y)]])
        for k, ch in enumerate(active):
            if not used[k]:
                done.append(ch[1])
        active = new_active
    done.extend(ch[1] for ch in active)
    return [np.asarray(c, dtype=np.float64) for c in done if len(c) >= min_len]


def add_polylines(buf, lines, *, width, noise, wobble_px=0.0, smooth_px=3,
                  width_field=None, width_gain=0.0, taper_px=12.0, phase=0.0):
    """Add already traced polylines as tapered brush strokes."""
    for k, line in enumerate(lines):
        p = resample(line, 1.0)
        p = smooth(p, smooth_px)
        p = wobble(p, noise, wobble_px, phase=phase + 3.1 * k)
        p = resample(p, 1.5)
        if len(p) < 2:
            continue
        s = arclength(p)
        wv = np.full(len(p), width, dtype=np.float64)
        if width_field is not None:
            f = sample(width_field, p[:, 0], p[:, 1])
            wv *= (1.0 - 0.5 * width_gain) + width_gain * f
        wv *= taper(s, s[-1], taper_px)
        buf.add(p, wv)
