import hashlib
import heapq
import json
import math

import numpy as np
import pytest
from fastapi.testclient import TestClient

import jezero as j
import main
import mars_router as r

client = TestClient(main.app)
req = main.RouteRequest(
    start=(18.44462715, 77.45088572),
    end=(18.49197961, 77.32624591),
    weights={"slope": 0.35, "interpolation": 0.45},
)


def flat(mask=None):
    z = np.zeros((5, 5))
    return r.Terrain(
        z, z, z, np.zeros_like(z, bool) if mask is None else mask, [], r.CostModel()
    )


def test_steps_disconnected_and_corners():
    mask = np.zeros((5, 5), bool)
    mask[1, 0] = mask[0, 1] = True
    t = flat(mask)
    for a, b in [
        ((0, 0), (0, 0)),
        ((0, 0), (0, 4)),
        ((-1, 0), (0, 0)),
        ((1, 0), (1, 1)),
        ((1, 1), (0, 1)),
        ((0, 0), (1, 1)),
        ((4, 4), (4, 5)),
    ]:
        assert t.edge(a, b) is None
    assert r.astar(t, (0, 0), (4, 4)) is None
    assert t.edge((3, 3), (4, 4), 4) is None


def test_immutable_geography_and_native_spacing():
    for c in [(0, 0), (7, 15), (j.ROWS - 1, j.COLS - 1)]:
        assert j.latlon_to_cell(*j.cell_to_lonlat(c)[::-1]) == c
    assert j.DY == pytest.approx(
        3396000 * math.pi / (180 * 128)
    ) and j.DX == pytest.approx(j.DY * math.cos(math.radians((j.NORTH + j.SOUTH) / 2)))
    for key, digest in j.MANIFEST["sha256"].items():
        assert hashlib.sha256((j.DATA_DIR / key).read_bytes()).hexdigest() == digest
    before = client.get("/api/terrain").json()
    for start, weights in [
        (req.start, req.weights.model_dump()),
        ((18.48, 77.4), {"slope": 1, "interpolation": 0}),
    ]:
        assert (
            client.post(
                "/api/route",
                json={**req.model_dump(), "start": start, "weights": weights},
            ).status_code
            == 200
        )
    assert client.get("/api/terrain").json() == before
    a = r.generate_terrain(20, start=(0, 0), goal=(10, 12))
    b = r.generate_terrain(20, start=(5, 8), goal=(19, 17))
    np.testing.assert_array_equal(a.elevation, b.elevation)
    np.testing.assert_array_equal(a.crater_mask, b.crater_mask)


def test_reject_nan_blocked_duplicate_and_stale_dataset():
    blocked = next(zip(*j.EXCLUDED.nonzero()))
    for update, code in [
        ({"start": j.cell_to_lonlat(blocked)[::-1]}, 422),
        ({"end": req.start}, 422),
        ({"dataset_id": "old"}, 409),
    ]:
        response = client.post("/api/route", json={**req.model_dump(), **update})
        assert response.status_code == code
        assert response.json()["request_id"] == response.headers["X-Request-ID"]
    raw = json.dumps({**req.model_dump(), "start": [float("nan"), 77.45]})
    assert (
        client.post(
            "/api/route", content=raw, headers={"Content-Type": "application/json"}
        ).status_code
        == 422
    )


@pytest.mark.parametrize("weights", [(0, 0), (1, 0), (0.35, 0.45), (0, 1)])
def test_grid_astar_matches_independent_dijkstra(weights):
    model = main.cost_model_for(
        main.TerrainWeights(slope=weights[0], interpolation=weights[1])
    )
    t = j.terrain_for(model)
    start, goal = [j.latlon_to_cell(*p) for p in [req.start, req.end]]
    queue = [(0, start)]
    visited = set()
    while queue:
        cost, node = heapq.heappop(queue)
        if node == goal:
            break
        if node in visited:
            continue
        visited.add(node)
        for nb, w in t.moves(node):
            if nb not in visited:
                heapq.heappush(queue, (cost + w, nb))
    actual = r.astar(t, start, goal)
    assert node == goal and actual.cost == pytest.approx(cost, abs=1e-9)
    geo = j.validate(actual.path, start, goal, t, j.DATASET_ID)
    assert geo["total_cost"] == pytest.approx(cost)
    with pytest.raises(ValueError):
        j.validate([start, goal], start, goal, t, j.DATASET_ID)
    with pytest.raises(ValueError):
        j.validate(actual.path, start, goal, t, "stale")


def test_full_sample_and_tiny_qubo_ground_state():
    graph = r.WaypointGraph(
        [(0, i) for i in range(5)],
        {(0, 1): 1, (1, 4): 2, (1, 2): 3, (2, 3): 1, (3, 2): 1},
        {},
    )
    good = [(0, 1), (1, 4)]
    assert r.decode_arcs(good, graph) == [0, 1, 4]
    for arcs in [
        good + [(1, 2)],
        good + [(2, 3), (3, 2)],
        good + [(0, 1)],
        [(1, 4)],
        [],
    ]:
        assert r.decode_arcs(arcs, graph) is None
    norm = r.normalise_costs(graph.arcs)
    assert r.exhaustive_qubo_check(graph, norm, r.flow_penalty(norm, 5, 2))[
        "ground_state_matches_dijkstra"
    ]


def test_invalid_solver_output_remains_a_labeled_fallback(monkeypatch):
    monkeypatch.setattr(
        r,
        "run_quantum",
        lambda t, s, g, c: {
            "path": [s, g],
            "details": {},
            "status": "feasible_suboptimal",
        },
    )
    result = main.make_result(req, True)
    assert result["features"][1]["properties"]["status"] == "fallback_classical_astar"
    assert "neighbor" in result["meta"]["quantum"]["fallback_reason"]
    assert result["features"][0]["geometry"] == result["features"][1]["geometry"]


def test_bundled_public_graph_and_terrain_match_runtime():
    from tools.prepare_demo import build_graph

    assert json.loads((j.DATA_DIR / "graph.json").read_bytes()) == build_graph()
    assert (
        json.loads((j.DATA_DIR / "terrain.json").read_bytes())
        == client.get("/api/terrain").json()
    )


def test_two_clear_cells_in_disconnected_jezero_regions_return_no_route():
    start, end = (26, 21), (11, 1)
    assert not j.EXCLUDED[start] and not j.EXCLUDED[end]
    response = client.post(
        "/api/route",
        json={
            **req.model_dump(),
            "start": j.cell_to_lonlat(start)[::-1],
            "end": j.cell_to_lonlat(end)[::-1],
        },
    )
    assert response.status_code == 422
    assert "No route" in response.json()["detail"]
