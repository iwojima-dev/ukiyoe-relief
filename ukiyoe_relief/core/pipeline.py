"""High-level entry points (usable from the QGIS Python console too).

Example::

    from ukiyoe_relief.core import pipeline, params
    p = params.defaults(); p.preset = "Hokusai - Red Fuji"
    pipeline.run_file(r"E:/data/dem.tif", r"E:/data/dem_ukiyoe.tif", p)
"""
import os

import numpy as np

from .oblique import render_oblique
from .plan import render_plan
from .printing import impress, to_uint8


def _noop(*_a, **_k):
    pass


def render_array(dem, valid, cell, p, progress=_noop):
    """Render a DEM array; returns uint8 RGB."""
    if p.mode == "Layered landscape":
        plates, paper, emb, shape = render_oblique(dem, valid, cell, p, progress)
    else:
        plates, paper, emb = render_plan(dem, valid, cell, p, progress)
        shape = dem.shape
    img = impress(plates, paper, shape, p, emboss_field=emb, progress=progress)
    rgb = to_uint8(img)
    progress(98, "Writing output")
    return rgb


def run_file(src, dst, p, band=1, extent=None, also_png=False, progress=_noop):
    """Read ``src`` DEM, render, write ``dst``. Returns list of written paths."""
    from .io_raster import read_dem, write_geotiff, write_png
    progress(1, "Reading DEM")
    d = read_dem(src, band=band, max_size=p.max_size, extent=extent)
    rgb = render_array(d["dem"], d["valid"], d["cell"], p, progress)
    written = []
    root, ext = os.path.splitext(dst)
    if p.mode == "Layered landscape":
        out = root + ".png"
        write_png(out, rgb)
        written.append(out)
    else:
        if ext.lower() == ".png":
            write_png(dst, rgb)
            written.append(dst)
        else:
            out = root + ".tif"
            write_geotiff(out, rgb, d["geotransform"], d["wkt"])
            written.append(out)
            if also_png:
                write_png(root + ".png", rgb)
                written.append(root + ".png")
    progress(100, "Done")
    return written
