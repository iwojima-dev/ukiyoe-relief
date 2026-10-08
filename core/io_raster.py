"""DEM reading and image writing (GDAL)."""
import math

import numpy as np


def read_dem(path, band=1, max_size=1600, extent=None):
    """Read one band resampled to square (metric) pixels.

    ``extent`` = (xmin, ymin, xmax, ymax) in the raster CRS, or None.
    Returns dict(dem, valid, cell=(cx, cy) metres, geotransform, wkt).
    """
    from osgeo import gdal, osr
    gdal.UseExceptions()
    src = gdal.Open(path)
    if src is None:
        raise IOError("Cannot open raster: %s" % path)
    gt = src.GetGeoTransform()
    w, h = src.RasterXSize, src.RasterYSize
    xmin, ymax = gt[0], gt[3]
    xmax, ymin = xmin + gt[1] * w, ymax + gt[5] * h
    if extent is not None:
        xmin, ymin = max(xmin, extent[0]), max(ymin, extent[1])
        xmax, ymax = min(xmax, extent[2]), min(ymax, extent[3])
        if xmax <= xmin or ymax <= ymin:
            raise ValueError("The chosen extent does not overlap the DEM.")
    wkt = src.GetProjection()
    srs = osr.SpatialReference(wkt=wkt) if wkt else None
    if srs is not None and srs.IsGeographic():
        lat = 0.5 * (ymin + ymax)
        mx, my = 111320.0 * math.cos(math.radians(lat)), 110540.0
    else:
        unit = srs.GetLinearUnits() if srs is not None else 1.0
        mx = my = unit or 1.0
    width_m, height_m = (xmax - xmin) * mx, (ymax - ymin) * my
    native = min(abs(gt[1]) * mx, abs(gt[5]) * my)
    cell_m = max(max(width_m, height_m) / float(max_size), native)
    out_w = max(8, int(round(width_m / cell_m)))
    out_h = max(8, int(round(height_m / cell_m)))
    downsample = cell_m > native * 1.01

    one = gdal.Translate("", src, format="VRT", bandList=[int(band)])
    nodata = one.GetRasterBand(1).GetNoDataValue()
    opts = dict(format="MEM", outputBounds=(xmin, ymin, xmax, ymax),
                width=out_w, height=out_h, outputType=gdal.GDT_Float32,
                resampleAlg="average" if downsample else "bilinear",
                dstNodata=float("nan"))
    if nodata is not None:
        opts["srcNodata"] = nodata
    ds = gdal.Warp("", one, **opts)
    arr = ds.GetRasterBand(1).ReadAsArray().astype(np.float32)
    valid = np.isfinite(arr)
    if nodata is not None:
        valid &= arr != np.float32(nodata)
    ogt = ds.GetGeoTransform()
    cell = (abs(ogt[1]) * mx, abs(ogt[5]) * my)
    return dict(dem=arr, valid=valid, cell=cell, geotransform=ogt, wkt=ds.GetProjection())


def write_geotiff(path, rgb, geotransform, wkt):
    from osgeo import gdal
    h, w, _ = rgb.shape
    drv = gdal.GetDriverByName("GTiff")
    ds = drv.Create(path, w, h, 3, gdal.GDT_Byte,
                    options=["PHOTOMETRIC=RGB", "COMPRESS=DEFLATE", "TILED=YES"])
    ds.SetGeoTransform(geotransform)
    if wkt:
        ds.SetProjection(wkt)
    for i in range(3):
        b = ds.GetRasterBand(i + 1)
        b.WriteArray(rgb[:, :, i])
        b.SetColorInterpretation(gdal.GCI_RedBand + i)
    ds.FlushCache()
    ds = None


def write_png(path, rgb):
    try:
        from osgeo import gdal
        h, w, _ = rgb.shape
        mem = gdal.GetDriverByName("MEM").Create("", w, h, 3, gdal.GDT_Byte)
        for i in range(3):
            mem.GetRasterBand(i + 1).WriteArray(rgb[:, :, i])
        gdal.GetDriverByName("PNG").CreateCopy(path, mem)
        mem = None
    except ImportError:
        import matplotlib.image as mpimg
        mpimg.imsave(path, rgb)
