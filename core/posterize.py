"""Posterisation into flat plates and cleanup of small islands."""
import numpy as np

from .filters import gaussian


def quantile_thresholds(values, n, top_fraction=None):
    """``n - 1`` thresholds splitting ``values`` into equal-area classes.

    If ``top_fraction`` is given, the highest class gets exactly that share
    of the area and the remaining classes split the rest equally.
    """
    if values.size == 0:
        return np.zeros(n - 1)
    if top_fraction is None or n < 2:
        q = np.linspace(0.0, 1.0, n + 1)[1:-1]
    else:
        top = 1.0 - float(np.clip(top_fraction, 0.001, 0.9))
        q = np.concatenate([np.linspace(0.0, top, n)[1:-1], [top]])
    return np.quantile(values, q)


def classify(field, thresholds):
    return np.digitize(field, thresholds).astype(np.uint8)


_OFFSETS = [(0, 1), (1, 0), (1, 1), (1, -1)]


def _pairs(h, w, dy, dx):
    a = (slice(0, h - dy), slice(max(0, -dx), w - max(0, dx)))
    b = (slice(dy, h), slice(max(0, dx), w - max(0, -dx)))
    return a, b


def components(labels, max_iter=500):
    """8-connected components of equal values (numpy label propagation)."""
    h, w = labels.shape
    lab = np.arange(h * w, dtype=np.int64).reshape(h, w)
    pairs = [_pairs(h, w, dy, dx) for dy, dx in _OFFSETS]
    same = [labels[a] == labels[b] for a, b in pairs]
    for _ in range(max_iter):
        new = lab.copy()
        big = np.int64(h * w)
        for (a, b), s in zip(pairs, same):
            new[a] = np.minimum(new[a], np.where(s, lab[b], big))
            new[b] = np.minimum(new[b], np.where(s, lab[a], big))
        flat = new.ravel()
        for _ in range(4):
            flat = flat[flat]
        new = flat.reshape(h, w)
        if np.array_equal(new, lab):
            break
        lab = new
    return lab


def _sieve_numpy(labels, min_area):
    comp = components(labels)
    _, inv, counts = np.unique(comp.ravel(), return_inverse=True, return_counts=True)
    small = (counts[inv] < min_area).reshape(labels.shape)
    if not small.any():
        return labels
    out = labels.copy()
    known = ~small
    classes = np.unique(labels[known])
    sigma = max(1.0, np.sqrt(min_area) / 2.0)
    best = np.full(labels.shape, -1.0, np.float32)
    for k in classes:
        s = gaussian(((labels == k) & known).astype(np.float32), sigma)
        upd = small & (s > best)
        out[upd] = k
        best = np.where(upd, s, best)
    return out


def sieve(labels, min_area):
    """Merge connected patches smaller than ``min_area`` px into neighbours.

    Uses GDAL's SieveFilter when available (always inside QGIS), otherwise
    an equivalent pure-numpy implementation.
    """
    if min_area <= 1:
        return labels
    try:
        from osgeo import gdal
    except ImportError:
        return _sieve_numpy(labels, min_area)
    h, w = labels.shape
    ds = gdal.GetDriverByName("MEM").Create("", w, h, 1, gdal.GDT_Byte)
    band = ds.GetRasterBand(1)
    band.WriteArray(labels.astype(np.uint8))
    gdal.SieveFilter(band, None, band, int(min_area), 8)
    out = band.ReadAsArray().astype(np.uint8)
    ds = None
    return out


def soft_mask(labels, k, aa=0.6):
    """Anti-aliased indicator of class ``k``."""
    m = (labels == k).astype(np.float32)
    return np.clip(gaussian(m, aa) * 1.25 - 0.125, 0.0, 1.0) if aa > 0 else m
