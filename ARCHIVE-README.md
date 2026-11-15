# Quantumions: Martian Map

NASA Space Apps Challenge 2026 — Universal Event

Challenge: [Interplanetary Survival Guide: Martian Map](https://www.spaceappschallenge.org/2026/challenges/interplanetary-survival-guide-martian-map/)

## Team workflow

- Both teammates can clone this repository and open it in VS Code.
- Use Microsoft Live Share when editing together; share session links privately.
- Commit and push agreed changes so both teammates can access them.
- Never commit passwords, API keys, or other private information.

## Project direction

Explore a layered Marswalk map using NASA mission data, classical route planning, and an exploratory Qiskit optimization comparison. Confirm dataset choices and scope against the challenge statement.

## Mars Router API

This project wraps `mars_router.py` in a FastAPI service and serves the local Marswalk demo UI. The router includes weighted A* and a QAOA waypoint-graph experiment.

## Run locally

Requires Python 3.10 or newer. On the current Windows setup, use the installed Python 3.13 executable directly because the Python launcher does not list it:

```powershell
$python = "$env:LOCALAPPDATA\Programs\Python\Python313\python.exe"
& $python main.py
```

The project's Python environment already has the packages in `requirements.txt`. For a fresh machine, create a virtual environment and install the requirements before starting the server.

The app listens on `http://127.0.0.1:8000`. Open the root page for the UI or `/docs` for the API documentation.

For a stage backup when the backend itself is unavailable, open `static/index.html` directly in a browser and press “Load Demo Marswalk”. Its bundled visual preview does not need the API or an internet connection.

## Endpoints

`GET /api/health` reports service status and grid coverage.

`POST /api/route` accepts coordinates in `[latitude, longitude]` order:

```json
{
  "start": [-80.0, -170.0],
  "end": [80.0, 170.0],
  "weights": {"slope": 0.25, "radiation": 0.45}
}
```

The response is a GeoJSON `FeatureCollection` with `classical_astar` and `qaoa_waypoint_subgraph` `LineString` features, per-route metrics, a solver comparison, and terrain hazard/obstacle cells for rendering. GeoJSON coordinates use `[longitude, latitude]` order. The synthetic 20 × 20 grid covers the Jezero demo window `[77.35, 18.35, 77.75, 18.65]` (west, south, east, north); it is not real Mars elevation or radiation data. The supplied slope and radiation weights must be non-negative and sum to at most 1; the remaining share is assigned to crater hazard.

CORS is enabled for local frontend requests. The “Load Demo Marswalk” button fills the signature coordinates and runs the live API. The interactive API uses a compact QAOA budget (4 waypoints, at most 6 arc qubits, p=1, 8 COBYLA iterations, and 1,024 shots) with a 120-second browser request limit. Flow-conservation penalties use a 2.0 safety factor. The small QAOA budget can reduce solution quality, and A* remains the optimal full-grid baseline. If QAOA samples contain no valid flow-conserving path, the router returns the exact shortest path on its waypoint graph with an explicit fallback status. If the optional solver errors or its path fails validation, the API returns the valid A* route as a labeled fallback. Both cases return HTTP 200 when the request and classical route are valid; invalid inputs retain their 4xx responses. If the API itself is unavailable or takes over 120 seconds, the page shows a clearly labeled, curated visual preview; its numbers are illustrative and are not live solver measurements. The router's standalone defaults are 4 waypoints, at most 6 arc qubits, p=1, 8 optimizer iterations, 1,024 shots, and a 2.0 penalty factor.

Map clicks place the selected endpoint on a clear cell. Clicks on known crater cells, clicks outside the grid, out-of-bounds coordinate entries, and weight shares above 100% show a warning instead of failing silently. The judge explanation describes the waypoint QUBO and explicitly avoids a quantum-speedup claim.

The 60-second backup walkthrough is at `outputs/Marswalk_backup_60s.avi`. It is a 1280 × 720 illustrative video, not a screen capture of a live QAOA run; its preview metrics are labeled as illustrative in the video and UI.

## Run the API tests

```powershell
py -m pytest
```

The endpoint test checks that both solver routes start and end at the requested grid cells, traverse only passable cells, and use legal moves. It uses the waypoint graph's exact shortest path as a deterministic stand-in for the QAOA runtime, keeping API tests quick and independent of optional simulator behavior.
