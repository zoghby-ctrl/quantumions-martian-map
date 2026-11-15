"""Fixed Mars geography and independent route acceptance for the Jezero planner."""

import hashlib
import json
import math
from functools import lru_cache
from pathlib import Path

import numpy as np

import mars_router as router

DATA_DIR = Path(__file__).parent / "static" / "data"
MANIFEST = json.loads((DATA_DIR / "manifest.json").read_bytes())
DATASET_ID = MANIFEST["dataset_id"]
source_bytes = (DATA_DIR / "jezero.json").read_bytes()
if hashlib.sha256(source_bytes).hexdigest() != MANIFEST["sha256"]["jezero.json"]:
    raise RuntimeError("Jezero grid does not match the manifest")
DATA = json.loads(source_bytes)
WEST, SOUTH, EAST, NORTH = BBOX = tuple(DATA["bbox"])
ROWS, COLS = DATA["rows"], DATA["cols"]
DY = 3396000 * math.radians((NORTH - SOUTH) / ROWS)
DX = (
    3396000
    * math.cos(math.radians((SOUTH + NORTH) / 2))
    * math.radians((EAST - WEST) / COLS)
)
ELEVATION = np.array(DATA["elevation_m"], dtype=float)
COUNTS = np.array(DATA["shot_count"])
INTERPOLATED = (COUNTS == 0).astype(float)
GRADE = np.hypot(*np.gradient(ELEVATION, DY, DX))
MAX_GRADE = 0.18
EXCLUDED = GRADE > MAX_GRADE
# A two-cell exponential margin around excluded terrain. Distance in physical meters.
rr, cc = np.indices(EXCLUDED.shape)
MARGIN = np.zeros_like(GRADE)
for row, col in zip(*EXCLUDED.nonzero()):
    distance = np.hypot((rr - row) * DY, (cc - col) * DX)
    MARGIN = np.maximum(MARGIN, np.exp(-distance / (2 * DX)))
for field in (ELEVATION, COUNTS, INTERPOLATED, GRADE, EXCLUDED, MARGIN):
    field.flags.writeable = False

ASSUMPTIONS = [
    "Exploratory grid model. Each cell is roughly 440 by 463 meters. Sub-cell hazards are unresolved.",
    "Local cell grade or directional edge grade above 18% excludes travel. Diagonals cannot cross blocked corners. This threshold is a scenario assumption.",
    "Effort is horizontal distance in km times (1 + 6 × mean local grade), plus 10 × positive climb in km.",
    "Penalty per km blends normalized grade, zero-shot MOLA bins and proximity to excluded cells. Total score = effort + 4 × integrated penalty. Scores are dimensionless planning indices.",
    "No physiological, radiation-dose, weather, oxygen or walking-time model. The recommended path is hypothetical.",
]


def latlon_to_cell(lat, lon):
    if not (
        math.isfinite(lat)
        and math.isfinite(lon)
        and SOUTH <= lat <= NORTH
        and WEST <= lon <= EAST
    ):
        raise ValueError("Coordinates must fall inside the Jezero map bounds")
    return min(ROWS - 1, int((NORTH - lat) / (NORTH - SOUTH) * ROWS)), min(
        COLS - 1, int((lon - WEST) / (EAST - WEST) * COLS)
    )


def cell_to_lonlat(cell):
    r, c = cell
    return [
        WEST + (c + 0.5) * (EAST - WEST) / COLS,
        NORTH - (r + 0.5) * (NORTH - SOUTH) / ROWS,
    ]


@lru_cache(maxsize=12)
def terrain_for(model):
    return router.Terrain(
        ELEVATION, INTERPOLATED, MARGIN, EXCLUDED, [], model, (DY, DX)
    )


def validate(path, start, goal, terrain, dataset_id, connectivity=8):
    if (
        dataset_id != DATASET_ID
        or len(path) < 2
        or path[0] != start
        or path[-1] != goal
    ):
        raise ValueError("Mismatched dataset or route endpoints")
    for r, c in path:
        if not (0 <= r < ROWS and 0 <= c < COLS) or EXCLUDED[r, c]:
            raise ValueError("Route enters an excluded or out-of-bounds cell")
    distance = ascent = max_grade = 0.0
    for (r, c), (nr, nc) in zip(path, path[1:]):
        dr, dc = abs(nr - r), abs(nc - c)
        if max(dr, dc) != 1 or (connectivity == 4 and dr + dc != 1):
            raise ValueError("Non-neighbor route step")
        if dr and dc and (EXCLUDED[r, nc] or EXCLUDED[nr, c]):
            raise ValueError("Diagonal crosses an excluded corner")
        meters = math.hypot(dr * DY, dc * DX)
        rise = ELEVATION[nr, nc] - ELEVATION[r, c]
        grade = abs(rise) / meters
        if grade > MAX_GRADE:
            raise ValueError("Step exceeds the modeled grade limit")
        distance += meters
        ascent += max(0, rise)
        max_grade = max(max_grade, grade)
    metrics = router.evaluate_path(terrain, path)
    if any(not math.isfinite(v) or v < 0 for v in vars(metrics).values()):
        raise ValueError("Route has invalid metrics")
    return {
        **vars(metrics),
        "distance_m": round(distance, 2),
        "ascent_m": float(ascent),
        "max_step_grade_percent": round(100 * max_grade, 2),
        "interpolated_vertices": int(sum(COUNTS[c] == 0 for c in path)),
    }
