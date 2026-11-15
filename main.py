"""FastAPI wrapper for the Mars terrain router."""
from __future__ import annotations

import math
import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import mars_router as router


# GeoJSON bbox order is west, south, east, north. This local demo window
# contains the Jezero coordinates used by the Marswalk preset. Terrain remains
# synthetic and is not a real elevation/radiation dataset.
MARS_BBOX = (77.35, 18.35, 77.75, 18.65)
GRID_SIZE = 20
TERRAIN_SEED = 7
# Keep the interactive demo responsive on a laptop. The previous defaults
# (p=2, 150 COBYLA iterations, 8,192 shots and exhaustive QUBO verification)
# made a single statevector request too expensive for an interactive demo.
# This remains a real QAOA run; the smaller search budget makes its heuristic
# quality more variable, which the UI already reports against the A* baseline.
QUANTUM_CONFIG = router.QuantumConfig(
    n_waypoints=4,
    max_qubits=6,
    reps=1,
    maxiter=8,
    shots=1024,
    penalty_factor=2.0,
    verify=False,
)
STATIC_DIR = Path(__file__).parent / "static"


class TerrainWeights(BaseModel):
    slope: float = Field(ge=0.0, le=1.0)
    radiation: float = Field(ge=0.0, le=1.0)

    class Config:
        extra = "forbid"


class RouteRequest(BaseModel):
    # Input order is [latitude, longitude]. Tuple types enforce exactly two values.
    start: tuple[float, float]
    end: tuple[float, float]
    weights: TerrainWeights

    class Config:
        extra = "forbid"


app = FastAPI(title="Mars Router API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def latlon_to_cell(latitude: float, longitude: float, size: int = GRID_SIZE) -> router.Cell:
    """Map [lat, lon] coordinates onto the nearest row/column in the grid."""
    west, south, east, north = MARS_BBOX
    if not (math.isfinite(latitude) and math.isfinite(longitude)):
        raise HTTPException(status_code=422, detail="coordinates must be finite numbers")
    if not (south <= latitude <= north and west <= longitude <= east):
        raise HTTPException(
            status_code=422,
            detail=f"coordinates must fall inside bbox [west, south, east, north]={list(MARS_BBOX)}",
        )
    row = round((north - latitude) / (north - south) * (size - 1))
    col = round((longitude - west) / (east - west) * (size - 1))
    return int(row), int(col)


def cell_to_latlon(cell: router.Cell, size: int = GRID_SIZE) -> list[float]:
    """Return the [longitude, latitude] center of a grid cell for GeoJSON."""
    west, south, east, north = MARS_BBOX
    row, col = cell
    latitude = north - row / (size - 1) * (north - south)
    longitude = west + col / (size - 1) * (east - west)
    return [longitude, latitude]


def cost_model_for(weights: TerrainWeights) -> router.CostModel:
    """Use the supplied slope/radiation shares and assign the remainder to craters."""
    slope, radiation = float(weights.slope), float(weights.radiation)
    if not (math.isfinite(slope) and math.isfinite(radiation)):
        raise HTTPException(status_code=422, detail="weights must be finite numbers")
    if slope + radiation > 1.0 + 1e-12:
        raise HTTPException(
            status_code=422,
            detail="slope and radiation weights must sum to at most 1.0",
        )
    return router.CostModel(
        w_slope=slope,
        w_rad=radiation,
        w_crater=max(0.0, 1.0 - slope - radiation),
    )


def _feature(name: str, path: list[router.Cell], metrics: router.PathMetrics,
             duration_ms: float | None, status: str) -> dict[str, Any]:
    return {
        "type": "Feature",
        "properties": {
            "solver": name,
            "total_cost": round(float(metrics.total_cost), 6),
            "energy": round(float(metrics.energy), 6),
            "hazard_score": round(float(metrics.hazard_score), 6),
            "steps": int(metrics.steps),
            "distance_cells": round(float(metrics.distance_cells), 6),
            "execution_time_ms": None if duration_ms is None else round(float(duration_ms), 3),
            "status": status,
        },
        "geometry": {
            "type": "LineString",
            "coordinates": [cell_to_latlon(cell) for cell in path],
        },
    }


@app.get("/api/health")
def health() -> dict[str, Any]:
    """Report service availability and coordinate coverage."""
    west, south, east, north = MARS_BBOX
    demo_start = latlon_to_cell(18.44, 77.45)
    demo_end = latlon_to_cell(18.52, 77.62)
    terrain = router.generate_terrain(
        size=GRID_SIZE,
        seed=TERRAIN_SEED,
        start=demo_start,
        goal=demo_end,
    )
    return {
        "status": "ok",
        "bbox": [west, south, east, north],
        "grid_size": GRID_SIZE,
        "solvers": ["weighted_astar", "qaoa_waypoint_subgraph"],
        "terrain": {
            "crater_cells": [
                [int(r), int(c)] for r, c in zip(*terrain.crater_mask.nonzero())
            ],
            "hazard_grid": [
                [round(float(value), 4) for value in row]
                for row in terrain.hazard.tolist()
            ],
        },
    }


@app.get("/")
def frontend() -> FileResponse:
    """Serve the local Marswalk frontend."""
    return FileResponse(STATIC_DIR / "index.html")


@app.post("/api/route")
def route(request: RouteRequest) -> dict[str, Any]:
    """Run weighted A* and QAOA, returning both paths as GeoJSON features."""
    start = latlon_to_cell(*request.start)
    goal = latlon_to_cell(*request.end)
    if start == goal:
        raise HTTPException(status_code=422, detail="start and end map to the same terrain cell")

    model = cost_model_for(request.weights)
    terrain = router.generate_terrain(
        size=GRID_SIZE,
        seed=TERRAIN_SEED,
        start=start,
        goal=goal,
        model=model,
    )

    classical_started = time.perf_counter()
    classical_result = router.astar(terrain, start, goal)
    classical_duration_ms = (time.perf_counter() - classical_started) * 1_000.0
    if classical_result is None:
        raise HTTPException(status_code=422, detail="no classical route exists for these coordinates")
    classical_metrics = router.evaluate_path(terrain, classical_result.path)

    quantum_fallback_reason = None
    try:
        quantum_result = router.run_quantum(terrain, start, goal, QUANTUM_CONFIG)
    except Exception as exc:  # Keep a valid classical response if the optional solver errors.
        quantum_result = {
            "path": None,
            "execution_time_ms": None,
            "status": f"error:{type(exc).__name__}",
        }
    if not isinstance(quantum_result, dict):
        quantum_result = {"path": None, "execution_time_ms": None, "status": "error:invalid_solver_result"}
    quantum_path = quantum_result.get("path")
    quantum_status = quantum_result.get("status", "unknown")
    quantum_fallback_reason = (quantum_result.get("details") or {}).get("fallback_reason")

    # QAOA output is only accepted after endpoint, collision and edge checks.
    # The local A* result guarantees a valid HTTP 200 fallback for this request.
    if quantum_path is not None:
        try:
            if (len(quantum_path) < 2 or quantum_path[0] != start
                    or quantum_path[-1] != goal
                    or any(not terrain.passable(cell) for cell in quantum_path)):
                raise ValueError("QAOA path has invalid endpoints or enters an obstacle")
            quantum_metrics = router.evaluate_path(terrain, quantum_path)
        except Exception:
            quantum_fallback_reason = "QAOA returned an invalid route"
            quantum_path = None
    else:
        quantum_fallback_reason = quantum_fallback_reason or f"QAOA returned no valid route ({quantum_status})"

    if quantum_path is None:
        quantum_path = classical_result.path
        quantum_metrics = classical_metrics
        quantum_status = "fallback_classical_astar"

    classical_feature = _feature(
        "classical_astar", classical_result.path, classical_metrics,
        classical_duration_ms, "optimal_on_grid",
    )
    quantum_feature = _feature(
        "classical_astar_fallback" if quantum_status == "fallback_classical_astar"
        else "qaoa_waypoint_subgraph",
        quantum_path, quantum_metrics,
        quantum_result.get("execution_time_ms"), quantum_status,
    )
    cost_delta = float(quantum_metrics.total_cost - classical_metrics.total_cost)
    is_fallback = quantum_status.startswith("fallback_")
    if is_fallback and cost_delta < -1e-9:
        lower_cost_solver = "waypoint_fallback"
    elif cost_delta < -1e-9:
        lower_cost_solver = "quantum"
    elif cost_delta > 1e-9:
        lower_cost_solver = "classical"
    else:
        lower_cost_solver = "equal"
    comparison = {
        "cost_delta_quantum_minus_classical": round(cost_delta, 6),
        "cost_delta_percent": round(100.0 * cost_delta / classical_metrics.total_cost, 3),
        "lower_cost_solver": lower_cost_solver,
        "hazard_delta_quantum_minus_classical": round(
            float(quantum_metrics.hazard_score - classical_metrics.hazard_score), 6
        ),
        "step_delta_quantum_minus_classical": int(quantum_metrics.steps - classical_metrics.steps),
    }

    return {
        "type": "FeatureCollection",
        "features": [classical_feature, quantum_feature],
        "metrics": {
            "classical": classical_feature["properties"],
            "quantum": quantum_feature["properties"],
            "comparison": comparison,
        },
        "meta": {
            "bbox": list(MARS_BBOX),
            "grid_size": GRID_SIZE,
            "start_cell": list(start),
            "end_cell": list(goal),
            "weights": {
                "slope": model.w_slope,
                "radiation": model.w_rad,
                "crater": model.w_crater,
            },
            "quantum_status": quantum_status,
            "quantum_fallback_reason": quantum_fallback_reason,
            "crater_cells": [
                [int(r), int(c)]
                for r, c in zip(*terrain.crater_mask.nonzero())
            ],
            "hazard_grid": [
                [round(float(value), 4) for value in row]
                for row in terrain.hazard.tolist()
            ],
        },
    }


app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="site-assets")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=False)
