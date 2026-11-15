"""Marswalk FastAPI application. Run with python main.py (one worker)."""

from __future__ import annotations

import logging
import math
import os
import time
import uuid
from functools import lru_cache
from importlib.util import find_spec
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

import jezero
import mars_router as router
from quantum_jobs import LIMIT_SECONDS, jobs

STATIC_DIR = Path(__file__).parent / "static"
QUANTUM_CONFIG = router.QuantumConfig(verify=True)
app = FastAPI(title="Marswalk · Jezero traverse planner", version="2.0")
logger = logging.getLogger("uvicorn.error")
origins = os.environ.get("MARSWALK_CORS_ORIGINS", "")
if origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins.split(","),
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["Content-Type"],
    )


class TerrainWeights(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, frozen=True)
    slope: float = Field(ge=0, le=1)
    interpolation: float = Field(ge=0, le=1)


class RouteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    start: tuple[float, float]
    end: tuple[float, float]
    weights: TerrainWeights
    dataset_id: str = jezero.DATASET_ID


@app.middleware("http")
async def request_identity(request: Request, call_next):
    request.state.request_id = uuid.uuid4().hex
    response = await call_next(request)
    response.headers["X-Request-ID"] = request.state.request_id
    return response


@app.exception_handler(RequestValidationError)
async def invalid_payload(request, error):
    # Avoid echoing nonfinite JSON values through the response encoder.
    messages = [
        ".".join(map(str, issue["loc"][1:])) + " " + issue["msg"]
        for issue in error.errors()
    ]
    return JSONResponse(
        {
            "code": "invalid_inputs",
            "detail": ". ".join(messages),
            "request_id": request.state.request_id,
        },
        status_code=422,
    )


@app.exception_handler(HTTPException)
async def handled_error(request, error):
    return JSONResponse(
        {"detail": error.detail, "request_id": request.state.request_id},
        status_code=error.status_code,
    )


def cost_model_for(weights):
    remaining = 1.0 - weights.slope - weights.interpolation
    if remaining < -1e-12:
        raise HTTPException(422, "Terrain priority shares must sum to at most 1.0")
    # Historical engine fields w_rad/w_crater are generic weighted raster channels here.
    return router.CostModel(
        w_slope=weights.slope,
        w_rad=weights.interpolation,
        w_crater=max(0, remaining),
        cell_size_m=1000,
        max_grade=jezero.MAX_GRADE,
    )


def scenario(request):
    if request.dataset_id != jezero.DATASET_ID:
        raise HTTPException(409, "Dataset version changed. Reload the map.")
    model = cost_model_for(request.weights)
    try:
        start, end = (
            jezero.latlon_to_cell(*point) for point in (request.start, request.end)
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    terrain = jezero.terrain_for(model)
    if start == end:
        raise HTTPException(422, "Choose two different routing cells")
    if not all(terrain.passable(c) for c in (start, end)):
        raise HTTPException(422, "An endpoint is inside a modeled exclusion")
    return model, start, end


@lru_cache(maxsize=128)
def baseline(dataset_id, model, start, end):
    terrain = jezero.terrain_for(model)
    before = time.perf_counter()
    result = router.astar(terrain, start, end)
    elapsed = (time.perf_counter() - before) * 1000
    if result is None:
        raise HTTPException(
            422, "No route connects those cells under the grade and exclusion rules"
        )
    return tuple(result.path), elapsed, result.cost


def feature(name, path, stats, elapsed, status):
    return {
        "type": "Feature",
        "properties": {
            "solver": name,
            "status": status,
            **stats,
            "execution_time_ms": None if elapsed is None else round(elapsed, 3),
        },
        "geometry": {
            "type": "LineString",
            "coordinates": [jezero.cell_to_lonlat(c) for c in path],
        },
    }


def make_result(request, quantum=False):
    model, start, end = scenario(request)
    terrain = jezero.terrain_for(model)
    path, elapsed, optimal_cost = baseline(request.dataset_id, model, start, end)
    stats = jezero.validate(path, start, end, terrain, request.dataset_id)
    if not math.isclose(stats["total_cost"], optimal_cost):
        raise RuntimeError("Inconsistent A* cost on validated route")
    features = [feature("classical_astar", path, stats, elapsed, "optimal_on_grid")]
    diagnostics = None
    if quantum:
        before = time.perf_counter()
        try:
            q = router.run_quantum(terrain, start, end, QUANTUM_CONFIG)
        except Exception as exc:
            logger.exception("Quantum comparison failed")
            q = {"status": type(exc).__name__, "details": {}, "path": None}
        diagnostics = dict(q["details"])
        qpath = q.get("path")
        status = q["status"]
        try:
            if not qpath:
                raise ValueError(diagnostics.get("fallback_reason") or status)
            qstats = jezero.validate(qpath, start, end, terrain, request.dataset_id)
            if qstats["total_cost"] < optimal_cost - 1e-8:
                raise ValueError(
                    "Waypoint route violates the full-grid optimality invariant"
                )
        except (ValueError, IndexError, TypeError) as exc:
            diagnostics["fallback_reason"] = str(exc)
            logger.warning("Using A* fallback: %s", exc)
            qpath, qstats, status = path, stats, "fallback_classical_astar"
        name = {
            "fallback_classical_astar": "classical_astar_fallback",
            "fallback_exact_waypoint_graph": "exact_waypoint_dijkstra",
        }.get(status, "qaoa_waypoint_subgraph")
        diagnostics["total_ms"] = round((time.perf_counter() - before) * 1000, 3)
        diagnostics["grid_gap_percent"] = round(
            100 * (qstats["total_cost"] / optimal_cost - 1), 4
        )
        features.append(
            feature(name, qpath, qstats, q.get("execution_time_ms"), status)
        )
    return {
        "type": "FeatureCollection",
        "features": features,
        "meta": {
            "dataset_id": request.dataset_id,
            "input": request.model_dump(),
            "start_cell": start,
            "end_cell": end,
            "coordinate_system": jezero.MANIFEST["coordinates"],
            "geometry_model": jezero.MANIFEST["geometry"],
            "bbox_edges_wsen": jezero.BBOX,
            "spacing_m_east_north": [jezero.DX, jezero.DY],
            "sources": jezero.MANIFEST["sources"],
            "assumptions": jezero.ASSUMPTIONS,
            "quantum": diagnostics,
            "ai_disclosure": "Codex-assisted processing and routing code. Elevations, shot counts, imagery and waypoints are mission products.",
        },
    }


def quantum_available():
    return all(
        find_spec(name) is not None
        for name in ("qiskit", "qiskit_algorithms", "qiskit_optimization")
    )


@app.get("/api/health")
def health():
    available = quantum_available()
    return {
        "status": "ok",
        "dataset_id": jezero.DATASET_ID,
        "bbox": jezero.BBOX,
        "solvers": ["weighted_astar"]
        + (["qaoa_waypoint_subgraph"] if available else []),
        "quantum_packages_present": available,
        "quantum_limit_seconds": LIMIT_SECONDS,
    }


@app.get("/api/terrain")
def terrain():
    return {
        "dataset_id": jezero.DATASET_ID,
        **jezero.DATA,
        "max_grade": jezero.MAX_GRADE,
        "slope_percent": (100 * jezero.GRADE).round(2).tolist(),
        "excluded": jezero.EXCLUDED.astype(int).tolist(),
        "dx": jezero.DX,
        "dy": jezero.DY,
        "manifest": jezero.MANIFEST,
        "assumptions": jezero.ASSUMPTIONS,
    }


@app.post("/api/route")
def route(request: RouteRequest):
    return make_result(request)


@app.post("/api/quantum", status_code=202)
def compare(request: RouteRequest):
    model, start, end = scenario(request)
    baseline(request.dataset_id, model, start, end)
    if not quantum_available():
        raise HTTPException(
            503,
            "Qiskit simulator packages are unavailable. The classical route is ready.",
        )
    try:
        job_id, cached = jobs.submit(request.model_dump())
    except RuntimeError as exc:
        raise HTTPException(429, str(exc)) from exc
    return {
        "job_id": job_id,
        "status": "complete" if cached else "running",
        "cached": cached,
        "limit_seconds": LIMIT_SECONDS,
    }


@app.get("/api/quantum/{job_id}")
def get_job(job_id: str):
    return jobs.read(job_id) or missing_job()


@app.delete("/api/quantum/{job_id}")
def cancel_job(job_id: str):
    return jobs.cancel(job_id) or missing_job()


def missing_job():
    raise HTTPException(404, "Unknown or expired comparison")


@app.get("/")
def frontend():
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.mount("/", StaticFiles(directory=STATIC_DIR), name="assets")

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app, host=os.getenv("HOST", "127.0.0.1"), port=int(os.getenv("PORT", "8000"))
    )
