"""Materialize public map data, the browser graph, and an explicitly recorded live run.

Run with the optional Qiskit environment after changing the dataset or model.
"""

import json
from datetime import datetime, timezone
import jezero as j
import main


def write(name, data):
    (j.DATA_DIR / name).write_text(
        json.dumps(data, separators=(",", ":"), allow_nan=False), encoding="utf-8"
    )


def build_graph():
    # Use the exact same Terrain.edge for every directed step. Export linear basis
    # scores for pure slope / coverage / margin. A convex mix reproduces any request.
    fields = [
        j.terrain_for(
            main.cost_model_for(main.TerrainWeights(slope=s, interpolation=i))
        )
        for s, i in [(1, 0), (0, 1), (0, 0)]
    ]
    graph = []
    for r in range(j.ROWS):
        for c in range(j.COLS):
            neighbors = []
            for (nr, nc), _ in fields[0].moves((r, c)):
                scores = [t.edge((r, c), (nr, nc)) for t in fields]
                neighbors.append(
                    [nr * j.COLS + nc, scores[0][0], *[v[1] for v in scores]]
                )
            graph.append(neighbors)
    return {
        "dataset_id": j.DATASET_ID,
        "risk_weight": fields[0].model.risk_weight,
        "energy_weight": fields[0].model.energy_weight,
        "length_unit_m": fields[0].model.cell_size_m,
        "adjacency": graph,
    }


if __name__ == "__main__":
    write("terrain.json", main.terrain())
    write("graph.json", build_graph())
    request = main.RouteRequest(
        start=j.DATA["stops"][0]["lonlat"][::-1],
        end=j.DATA["stops"][-1]["lonlat"][::-1],
        weights={"slope": 0.35, "interpolation": 0.45},
    )
    answer = main.make_result(request, quantum=True)
    if answer["features"][1]["properties"]["status"] not in (
        "optimal_on_waypoint_graph",
        "feasible_suboptimal",
    ):
        raise RuntimeError(
            "A real sampled QAOA route is required to replace the recording"
        )
    answer["meta"]["recorded_utc"] = datetime.now(timezone.utc).isoformat(
        timespec="seconds"
    )
    answer["meta"]["mode"] = "recorded_simulator_run"
    write("recorded-route.json", answer)
    print(answer["features"][1]["properties"], answer["meta"]["quantum"])
