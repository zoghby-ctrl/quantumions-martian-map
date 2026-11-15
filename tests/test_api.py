"""Original API coverage adapted to the fixed dataset and opt-in quantum contract."""

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

import jezero
import main
import mars_router as router

client = TestClient(main.app)
REQUEST = {
    "start": [18.44, 77.45],
    "end": [18.52, 77.62],
    "weights": {"slope": 0.25, "interpolation": 0.45},
}


def test_health_endpoint_reports_service_and_bbox(monkeypatch):
    monkeypatch.setattr(main, "quantum_available", lambda: False)
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    assert body["bbox"] == [77.265625, 18.3359375, 77.640625, 18.5546875]
    assert body["solvers"] == ["weighted_astar"]
    grid = client.get("/api/terrain").json()
    assert body["dataset_id"] == grid["dataset_id"]
    assert sum(map(sum, grid["excluded"])) > 0
    assert client.post("/api/quantum", json=REQUEST).status_code == 503


def test_root_serves_the_marswalk_ui():
    response = client.get("/")
    assert response.status_code == 200
    assert "Plan traverse" in response.text
    assert "Quantum waypoint lab" in response.text
    for asset in (
        "app.js",
        "map.js",
        "styles.css",
        "data/jezero-ctx.webp",
        "quantumions.png",
    ):
        assert client.get("/" + asset).status_code == 200


def test_route_endpoint_returns_two_clear_geojson_paths(monkeypatch):
    # Keep the teammate's deterministic graph integration check, separate from a real simulator run.
    def exact(terrain, start, end, cfg):
        graph = router.build_waypoint_graph(terrain, start, end, cfg)
        nodes, cost = router.dijkstra_graph(graph)
        return {
            "path": graph.stitch(nodes),
            "execution_time_ms": 1,
            "status": "fallback_exact_waypoint_graph",
            "details": {
                "exact_waypoint_graph_cost": cost,
                "fallback_reason": "Deterministic test reference",
            },
        }

    monkeypatch.setattr(router, "run_quantum", exact)
    live = client.post("/api/route", json=REQUEST)
    assert live.status_code == 200
    assert [f["properties"]["solver"] for f in live.json()["features"]] == [
        "classical_astar"
    ]
    body = main.make_result(main.RouteRequest(**REQUEST), quantum=True)
    assert body["type"] == "FeatureCollection"
    assert [f["properties"]["solver"] for f in body["features"]] == [
        "classical_astar",
        "exact_waypoint_dijkstra",
    ]
    assert body["meta"]["quantum"]["fallback_reason"] == "Deterministic test reference"
    for f in body["features"]:
        cells = [
            jezero.latlon_to_cell(lat, lon) for lon, lat in f["geometry"]["coordinates"]
        ]
        assert cells[0] == tuple(body["meta"]["start_cell"]) and cells[-1] == tuple(
            body["meta"]["end_cell"]
        )
        for (r, c), (nr, nc) in zip(cells, cells[1:]):
            assert max(abs(r - nr), abs(c - nc)) == 1
            assert not jezero.EXCLUDED[nr, nc]
            if r != nr and c != nc:
                assert not (jezero.EXCLUDED[r, nc] or jezero.EXCLUDED[nr, c])


def test_route_rejects_coordinates_outside_bbox():
    assert (
        client.post("/api/route", json={**REQUEST, "start": [91, 0]}).status_code == 422
    )


def test_route_rejects_weight_shares_above_one_hundred_percent():
    r = client.post(
        "/api/route",
        json={**REQUEST, "weights": {"slope": 0.75, "interpolation": 0.75}},
    )
    assert r.status_code == 422 and "sum to at most" in r.json()["detail"]


def test_cost_weights_cover_zero_and_full_share_without_overflow():
    zero = main.cost_model_for(main.TerrainWeights(slope=0, interpolation=0))
    full = main.cost_model_for(main.TerrainWeights(slope=1, interpolation=0))
    assert (zero.w_slope, zero.w_rad, zero.w_crater) == (0, 0, 1)
    assert (full.w_slope, full.w_rad, full.w_crater) == (1, 0, 0)
    with pytest.raises(HTTPException):
        main.cost_model_for(main.TerrainWeights(slope=0.75, interpolation=0.75))


def test_cors_same_origin_by_default():
    response = client.options(
        "/api/route",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert "access-control-allow-origin" not in response.headers
