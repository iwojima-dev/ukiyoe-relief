"""Water detection: automatic sea at a given level, lakes, NoData as sea."""
import numpy as np

from .filters import gaussian

SEA_AUTO = "Sea (auto, connected to edge)"
BELOW_LEVEL = "All cells at or below level"
OFF = "Off"
MODES = [SEA_AUTO, BELOW_LEVEL, OFF]


def _label(mask):
    """8-connected components of a boolean mask; returns (labels, count)."""
    try:
        from scipy import ndimage
        lab, n = ndimage.label(mask, structure=np.ones((3, 3), int))
        return lab, n
    except ImportError:
        from .posterize import components
        comp = components(mask.astype(np.uint8))
        comp = np.where(mask, comp + 1, 0)
        u, inv = np.unique(comp.ravel(), return_inverse=True)
        lab = inv.reshape(mask.shape)
        if u[0] != 0:
            lab = lab + 1
        return lab, int(lab.max())


def label4(mask):
    """4-connected components of a boolean mask; returns (labels, count)."""
    try:
        from scipy import ndimage
        return ndimage.label(mask)
    except ImportError:
        lab, n = _label(mask)  # 8-connected fallback
        return lab, n


def _edge_connected(mask, seeds):
    """Components of ``mask`` that touch the image border or ``seeds``."""
    lab, n = _label(mask)
    if n == 0:
        return np.zeros_like(mask)
    touch = np.zeros(n + 1, bool)
    border = np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]])
    touch[border] = True
    if seeds is not None and seeds.any():
        ring = (gaussian(seeds.astype(np.float32), 1.0) > 0.05) & mask
        touch[lab[ring]] = True
    touch[0] = False
    return touch[lab]


def detect(z, valid, p, cell=None):
    """Boolean water mask on the DEM grid.

    ``z`` must be NoData-filled.  With ``nodata_as_sea`` the NoData area is
    returned as water too (the caller decides whether to print it).
    """
    mode = getattr(p, "water_mode", OFF)
    nod = (~valid) if p.nodata_as_sea else np.zeros_like(valid)
    if mode == OFF:
        return nod.copy()
    # small tolerance: DEM sea surfaces are rarely exactly 0 (noise, geoid)
    low = valid & (z <= p.water_level + p.water_tolerance)
    if mode == SEA_AUTO:
        low = _edge_connected(low, nod)
    water = low | nod
    # sieve: drop puddles and fill tiny islands in the sea
    if p.min_area_px > 1 and water.any():
        lab, n = _label(water)
        if n:
            area = np.bincount(lab.ravel(), minlength=n + 1)
            keep = area >= p.min_area_px
            keep[0] = False
            water = keep[lab] | nod
        lab, n = _label(~water)
        if n:
            area = np.bincount(lab.ravel(), minlength=n + 1)
            tiny = area < max(4, p.min_area_px // 4)
            tiny[0] = False
            water |= tiny[lab]
    return water
