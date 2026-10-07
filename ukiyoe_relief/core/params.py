"""Render parameters: one table drives both the defaults and the dialog."""
from dataclasses import dataclass

from .presets import PRESETS, DEFAULT_PRESET

# (name, label, kind, default, min, max, decimals_or_step, tab, tooltip)
SPEC = [
    # --- General -------------------------------------------------------
    ("mode", "Mode", "choice", "Plan view", ["Plan view", "Layered landscape"], None, None,
     "General", "Plan view: map-like print, georeferenced GeoTIFF.\n"
                "Layered landscape: oblique view, receding ridges as separate plates (PNG)."),
    ("preset", "Palette", "choice", DEFAULT_PRESET, list(PRESETS), None, None,
     "General", "Pigment set modelled on historical woodblock inks."),
    ("max_size", "Working size, px (longest side)", "int", 1600, 200, 8000, 100,
     "General", "The DEM is resampled to square pixels so that its longest side is at most this.\n"
     "Layered landscape: the sheet is always exactly this wide, for any view direction."),
    ("seed", "Random seed", "int", 7, 0, 999999, 1,
     "General", "Same seed + same parameters = identical print."),
    ("sun_azimuth", "Sun azimuth, deg", "float", 315.0, 0.0, 360.0, 0,
     "General", "Direction of light, clockwise from north."),
    ("sun_altitude", "Sun altitude, deg", "float", 40.0, 5.0, 85.0, 0, "General", ""),
    ("z_factor", "Vertical exaggeration for shading", "float", 1.5, 0.1, 20.0, 1, "General", ""),
    ("generalize_px", "Block generalisation, px", "float", 3.0, 0.0, 30.0, 1,
     "General", "Gaussian smoothing of the DEM: how coarsely the blocks are cut."),
    # --- Colour plates -------------------------------------------------
    ("n_zones", "Colour zones", "int", 5, 2, 16, 1, "Plates",
     "Number of flat colour plates (posterisation levels)."),
    ("light_mix", "Light influence on zones", "float", 0.2, 0.0, 1.0, 2, "Plates",
     "0 = zones by elevation only; 1 = by illumination only."),
    ("snow_cap", "Bare-paper snow on the highest zone", "bool", True, None, None, None, "Plates", ""),
    ("snow_fraction", "Snow-capped area fraction", "float", 0.07, 0.0, 0.5, 2, "Plates",
     "Share of the area left as bare paper (snow) on the summits."),
    ("clean_px", "Plate smoothing, px", "float", 2.5, 0.0, 30.0, 1, "Plates",
     "Smooths zone boundaries before posterisation."),
    ("min_area_px", "Minimum island area, px", "int", 60, 0, 100000, 10, "Plates",
     "Smaller isolated patches are merged into neighbours (GDAL sieve)."),
    ("bokashi", "Bokashi (graded wiping)", "float", 0.55, 0.0, 1.0, 2, "Plates",
     "Strength of the ink gradient inside each zone."),
    ("n_shade", "Shadow levels", "int", 2, 0, 3, 1, "Plates", "Overprinted shadow plates."),
    ("shade_fraction", "Shadowed area fraction", "float", 0.35, 0.05, 0.8, 2, "Plates", ""),
    ("shade_density", "Shadow ink density", "float", 0.55, 0.0, 1.0, 2, "Plates", ""),
    ("water_mode", "Water", "choice", "Sea (auto, connected to edge)",
     ["Sea (auto, connected to edge)", "All cells at or below level", "Off"], None, None, "Plates",
     "Sea (auto): cells at or below the level that are connected to the sheet edge\n"
     "(or to NoData) are printed as sea; inland depressions stay land.\n"
     "All cells: every cell at or below the level becomes water (lakes, reservoirs)."),
    ("water_level", "Water level, DEM units", "float", 0.0, -12000.0, 9000.0, 1, "Plates",
     "Sea level; 0 for most DEMs."),
    ("water_tolerance", "Level tolerance, DEM units", "float", 0.5, 0.0, 100.0, 1, "Plates",
     "Cells up to level + tolerance count as water (noisy sea surfaces)."),
    ("nodata_as_sea", "Treat NoData as sea", "bool", False, None, None, None, "Plates",
     "For coastal DEMs where the sea is masked out as NoData."),
    ("shore_lines", "Shore echo lines", "int", 3, 0, 10, 1, "Plates", ""),
    # --- Line work -----------------------------------------------------
    ("keylines", "Key-block outlines", "bool", True, None, None, None, "Lines", ""),
    ("line_width", "Outline width, px", "float", 1.6, 0.2, 12.0, 1, "Lines", ""),
    ("line_wobble", "Hand wobble, px", "float", 0.6, 0.0, 5.0, 1, "Lines", ""),
    ("min_line_len", "Minimum line length, px", "float", 14.0, 0.0, 500.0, 0, "Lines", ""),
    ("shade_lines", "Outline shadow plates too", "bool", False, None, None, None, "Lines", ""),
    ("hatching", "Ridge strokes", "bool", True, None, None, None, "Lines",
     "Short tapered strokes running downslope from ridge crests."),
    ("hatch_spacing", "Hatch spacing, px", "float", 9.0, 3.0, 60.0, 1, "Lines", ""),
    ("hatch_amount", "Hatched ridge fraction", "float", 0.18, 0.0, 0.8, 2, "Lines", ""),
    ("hatch_length", "Hatch length, px", "float", 14.0, 2.0, 120.0, 1, "Lines", ""),
    ("hatch_width", "Hatch width, px", "float", 1.1, 0.2, 6.0, 1, "Lines", ""),
    # --- Printing ------------------------------------------------------
    ("misregister", "Misregistration (kento), px", "float", 1.0, 0.0, 8.0, 1, "Printing",
     "Random offset of each colour plate relative to the key block."),
    ("grain", "Wood grain", "float", 0.35, 0.0, 1.0, 2, "Printing", ""),
    ("grain_period", "Grain period, px", "float", 7.0, 2.0, 60.0, 1, "Printing", ""),
    ("mottle", "Baren mottling", "float", 0.15, 0.0, 1.0, 2, "Printing", ""),
    ("edge_dark", "Ink pooling at plate edges", "float", 0.25, 0.0, 1.0, 2, "Printing", ""),
    ("paper_texture", "Washi texture", "float", 0.6, 0.0, 2.0, 2, "Printing", ""),
    ("fibres", "Paper fibres", "float", 1.0, 0.0, 5.0, 1, "Printing", ""),
    ("karazuri", "Blind embossing (karazuri)", "float", 0.3, 0.0, 1.0, 2, "Printing", ""),
    # --- Layered landscape ---------------------------------------------
    ("view_azimuth", "View direction, deg", "float", 0.0, 0.0, 360.0, 0, "Landscape",
     "Direction the viewer looks toward (0 = looking north)."),
    ("tilt", "View elevation, deg", "float", 22.0, 3.0, 80.0, 0, "Landscape", ""),
    ("exag_mode", "Vertical exaggeration", "choice", "Auto", ["Auto", "Manual"], None, None,
     "Landscape", "Auto: the highest summit rises a set share of the sheet width, whatever\n"
                  "the scene size.  Manual: a fixed exaggeration factor."),
    ("relief_height", "Relief height, % of sheet width (auto)", "float", 6.0, 0.5, 60.0, 1,
     "Landscape", "Height of the highest summit above sea level, as % of the sheet width."),
    ("exaggeration", "Exaggeration factor (manual)", "float", 2.5, 0.2, 50.0, 1, "Landscape", ""),
    ("n_layers", "Depth layers", "int", 5, 2, 16, 1, "Landscape",
     "Number of receding ridge plates (aerial perspective)."),
    ("land_colour", "Land colouring", "choice", "Palette default",
     ["Palette default", "Distance (kulisse)", "Height (zones)"], None, None, "Landscape",
     "Distance: plates recede from near to far colour (Hiroshige).\n"
     "Height: plates follow elevation zones, faded by distance (Hokusai's Red Fuji).\n"
     "Palette default: whatever the chosen palette was designed for."),
    ("relief_gamma", "Relief curve (gamma)", "float", 1.3, 0.5, 3.0, 2, "Landscape",
     "1 = true proportions.  > 1 keeps foothills low and steepens the upper slopes:\n"
     "the concave flanks of a printed Fuji.  < 1 flattens summits."),
    ("silhouette_px", "Silhouette smoothing, px", "float", 1.5, 0.0, 10.0, 1, "Landscape",
     "Smoothing of the DEM used for the outline and summits (block generalisation\n"
     "is applied to plates and shadows only).  Small = sharp craters and peaks."),
    ("snow_fingers", "Snow fingers", "float", 0.5, 0.0, 2.0, 2, "Landscape",
     "How far the snow line drops into gullies and retreats on ridges."),
    ("interior_lines", "Interior ridge / gully lines", "int", 12, 0, 200, 1, "Landscape",
     "Number of the strongest ridge and gully lines drawn inside the silhouettes."),
    ("aerial", "Aerial perspective", "float", 0.6, 0.0, 1.0, 2, "Landscape",
     "How much distant layers fade."),
    ("ridge_bokashi", "Ridge bokashi depth", "float", 0.05, 0.005, 0.5, 3, "Landscape",
     "Fade length below each ridge, as a fraction of image height."),
    ("sky_fraction", "Sky margin", "float", 0.22, 0.0, 1.0, 2, "Landscape",
     "Extra sky above the highest summit, fraction of image height."),
    ("sky_density", "Sky band density", "float", 0.85, 0.0, 1.0, 2, "Landscape",
     "Ichimonji bokashi at the top of the sheet."),
    ("slice_lines", "Outline distance slices too", "bool", False, None, None, None, "Landscape",
     "Off: outlines only on true silhouettes (ridge edges hiding the ground behind).\n"
     "On: every distance-slice border is outlined as well (comb of profiles)."),
]

TABS = ["General", "Plates", "Lines", "Printing", "Landscape"]

# Fields that do nothing under the current settings are disabled in the
# dialog.  Each rule gets ``g(name) -> current value``.
_PLAN = lambda g: g("mode") == "Plan view"
_LAND = lambda g: g("mode") == "Layered landscape"
_WATER = lambda g: g("water_mode") != "Off"
_LINES = lambda g: g("keylines")
_HATCH = lambda g: _PLAN(g) and g("hatching")
_SHADE = lambda g: g("n_shade") > 0


def _height_mode(g):
    lc = g("land_colour")
    if lc == "Height (zones)":
        return True
    if lc == "Distance (kulisse)":
        return False
    return PRESETS.get(g("preset"), {}).get("land_colour") == "height"

DEPENDS = {
    # plan-only colour zoning and line work
    "n_zones": lambda g: _PLAN(g) or (_LAND(g) and _height_mode(g)),
    "light_mix": _PLAN,
    "hatching": _PLAN, "hatch_spacing": _HATCH, "hatch_amount": _HATCH,
    "hatch_length": _HATCH, "hatch_width": _HATCH,
    "shade_lines": lambda g: _PLAN(g) and _LINES(g) and _SHADE(g),
    "shore_lines": lambda g: _PLAN(g) and _WATER(g),
    # shared
    "snow_fraction": lambda g: g("snow_cap"),
    "shade_fraction": _SHADE, "shade_density": _SHADE,
    "water_level": _WATER, "water_tolerance": _WATER,
    "line_width": _LINES, "line_wobble": _LINES, "min_line_len": _LINES,
    # landscape
    "relief_height": lambda g: _LAND(g) and g("exag_mode") == "Auto",
    "exaggeration": lambda g: _LAND(g) and g("exag_mode") == "Manual",
    "slice_lines": lambda g: _LAND(g) and _LINES(g),
    "snow_fingers": lambda g: _LAND(g) and g("snow_cap"),
    "interior_lines": lambda g: _LAND(g) and _LINES(g),
}
for _s in SPEC:
    if _s[7] == "Landscape" and _s[0] not in DEPENDS:
        DEPENDS[_s[0]] = _LAND


@dataclass
class RenderParams:
    pass


# Build the dataclass fields from SPEC
for _s in SPEC:
    setattr(RenderParams, _s[0], _s[3])
RenderParams.__annotations__ = {s[0]: type(s[3]) for s in SPEC}
RenderParams = dataclass(RenderParams)


def defaults():
    return RenderParams()


def from_dict(d):
    p = RenderParams()
    for s in SPEC:
        if s[0] in d:
            setattr(p, s[0], type(s[3])(d[s[0]]))
    return p


def to_dict(p):
    return {s[0]: getattr(p, s[0]) for s in SPEC}
