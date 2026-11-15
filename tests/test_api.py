from __future__ import annotations

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

import main
import mars_router as router


client = TestClient(main.app)


def test_health_endpoint_reports_service_and_bbox() -> None:
    response = client.get("/api/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["bbox"] == [77.35, 18.35, 77.75, 18.65]
    assert set(body["solvers"]) == {"weighted_astar", "qaoa_waypoint_subgraph"}
    assert body["terrain"]["crater_cells"]
    assert len(body["terrain"]["hazard_grid"]) == 20


def test_root_serves_the_marswalk_ui() -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert "Load Demo Marswalk" in response.text
    assert "What does the quantum part do?" in response.text


def test_route_endpoint_returns_two_clear_geojson_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    def deterministic_subgraph_solver(terrain, start, goal, cfg, connectivity=8):
        """Use the exact waypoint-graph reference so the API test needs no Qiskit runtime."""
        graph = router.build_waypoint_graph(terrain, start, goal, cfg, connectivity)
        result = router.dijkstra_graph(graph)
        assert result is not None
        path = graph.stitch(result[0])
        return {
            "path": path,
            "metrics": router.evaluate_path(terrain, path),
            "execution_time_ms": 1.0,
            "status": "test_subgraph_path",
        }

    monkeypatch.setattr(router, "run_quantum", deterministic_subgraph_solver)
    request = {
        "start": [18.44, 77.45],
        "end": [18.52, 77.62],
        "weights": {"slope": 0.25, "radiation": 0.45},
    }

    response = client.post("/api/route", json=request)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["type"] == "FeatureCollection"
    assert [feature["properties"]["solver"] for feature in body["features"]] == [
        "classical_astar",
        "qaoa_waypoint_subgraph",
    ]
    assert set(body["metrics"]) == {"classical", "quantum", "comparison"}
    assert body["metrics"]["comparison"]["lower_cost_solver"] in {
        "classical", "quantum", "equal"
    }

    start = tuple(body["meta"]["start_cell"])
    goal = tuple(body["meta"]["end_cell"])
    model = main.cost_model_for(main.TerrainWeights(**request["weights"]))
    terrain = router.generate_terrain(
        size=main.GRID_SIZE,
        seed=main.TERRAIN_SEED,
        start=start,
        goal=goal,
        model=model,
    )

    assert len(body["features"]) == 2
    for feature in body["features"]:
        geometry = feature["geometry"]
        assert geometry["type"] == "LineString"
        assert len(geometry["coordinates"]) >= 2
        cells = [
            main.latlon_to_cell(latitude, longitude)
            for longitude, latitude in geometry["coordinates"]
        ]
        assert cells[0] == start
        assert cells[-1] == goal
        assert all(terrain.passable(cell) for cell in cells)
        assert all(terrain.edge(a, b) is not None for a, b in zip(cells, cells[1:]))


def test_route_rejects_coordinates_outside_bbox() -> None:
    response = client.post(
        "/api/route",
        json={
            "start": [91, 0],
            "end": [0, 0],
            "weights": {"slope": 0.25, "radiation": 0.45},
        },
    )

    assert response.status_code == 422


def test_route_rejects_weight_shares_above_one_hundred_percent() -> None:
    response = client.post(
        "/api/route",
        json={
            "start": [18.44, 77.45],
            "end": [18.52, 77.62],
            "weights": {"slope": 0.75, "radiation": 0.75},
        },
    )

    assert response.status_code == 422
    assert "sum to at most 1.0" in response.json()["detail"]


def test_cost_weights_cover_zero_and_full_share_without_overflow() -> None:
    zero = main.cost_model_for(main.TerrainWeights(slope=0, radiation=0))
    full = main.cost_model_for(main.TerrainWeights(slope=1, radiation=0))
    assert (zero.w_slope, zero.w_rad, zero.w_crater) == (0, 0, 1)
    assert (full.w_slope, full.w_rad, full.w_crater) == (1, 0, 0)

    with pytest.raises(HTTPException):
        main.cost_model_for(main.TerrainWeights(slope=0.75, radiation=0.75))


def test_cors_allows_local_frontend_preflight() -> None:
    response = client.options(
        "/api/route",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "*"
