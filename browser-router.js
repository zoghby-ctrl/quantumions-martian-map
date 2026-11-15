/* GitHub Pages transport. Legal moves and preference components come directly
   from the Python Terrain.edge implementation in tools/prepare_demo.py. */
let graphPromise;
async function browserRoute(grid, input) {
  graphPromise ??= fetch("data/graph.json")
    .then((r) => {
      if (!r.ok) throw new Error("Could not load the routing graph");
      return r.json();
    })
    .catch((e) => {
      graphPromise = null;
      throw e;
    });
  const graph = await graphPromise;
  if (
    graph.dataset_id !== input.dataset_id ||
    grid.dataset_id !== input.dataset_id
  )
    throw new Error("Dataset version mismatch");
  const at = (node) => [Math.floor(node / grid.cols), node % grid.cols];
  const id = ([r, c]) => r * grid.cols + c;
  const [s, g] = [input.start, input.end].map((p) => cellAt(...p));
  if (
    !s ||
    !g ||
    grid.excluded[s[0]][s[1]] ||
    grid.excluded[g[0]][g[1]] ||
    id(s) === id(g)
  )
    throw new Error("Invalid or excluded endpoint");
  const start = id(s),
    end = id(g),
    slope = input.weights.slope,
    gaps = input.weights.interpolation,
    margin = 1 - slope - gaps;
  if (![slope, gaps, margin].every((v) => Number.isFinite(v) && v >= -1e-12))
    throw new Error("Invalid priority shares");
  const hazard = (edge) =>
    slope * edge[2] + gaps * edge[3] + Math.max(0, margin) * edge[4];
  const score = (edge) =>
    graph.energy_weight * edge[1] + graph.risk_weight * hazard(edge);
  function heuristic(node) {
    const [r, c] = at(node),
      dr = Math.abs(g[0] - r),
      dc = Math.abs(g[1] - c),
      diagonal = Math.min(dr, dc);
    return (
      (((dr - diagonal) * grid.dy +
        (dc - diagonal) * grid.dx +
        diagonal * Math.hypot(grid.dx, grid.dy)) *
        graph.energy_weight) /
      graph.length_unit_m
    );
  }
  const clock = performance.now(),
    best = new Map([[start, 0]]),
    open = new Map([[start, heuristic(start)]]),
    parent = new Map();
  while (open.size) {
    let node,
      priority = Infinity;
    for (const [cell, value] of open)
      if (value < priority) {
        node = cell;
        priority = value;
      }
    open.delete(node);
    if (node === end) break;
    for (const edge of graph.adjacency[node]) {
      const [neighbor] = edge,
        cost = best.get(node) + score(edge);
      if (cost < (best.get(neighbor) ?? Infinity)) {
        best.set(neighbor, cost);
        parent.set(neighbor, node);
        open.set(neighbor, cost + heuristic(neighbor));
      }
    }
  }
  if (!parent.has(end))
    throw new Error(
      "No route connects those cells under the grade and exclusion rules",
    );
  const nodes = [end];
  while (nodes.at(-1) !== start) nodes.push(parent.get(nodes.at(-1)));
  nodes.reverse();
  const elapsed = performance.now() - clock;
  let energy = 0,
    risk = 0,
    meters = 0,
    ascent = 0,
    maxGrade = 0,
    cellDistance = 0;
  for (let i = 1; i < nodes.length; i++) {
    const [r, c] = at(nodes[i - 1]),
      [nr, nc] = at(nodes[i]),
      dr = Math.abs(nr - r),
      dc = Math.abs(nc - c);
    const length = Math.hypot(dr * grid.dy, dc * grid.dx),
      rise = grid.elevation_m[nr][nc] - grid.elevation_m[r][c];
    if (
      Math.max(dr, dc) !== 1 ||
      grid.excluded[nr][nc] ||
      (dr && dc && (grid.excluded[r][nc] || grid.excluded[nr][c])) ||
      Math.abs(rise) / length > grid.max_grade
    )
      throw new Error("Browser route failed terrain validation");
    const edge = graph.adjacency[nodes[i - 1]].find((e) => e[0] === nodes[i]);
    energy += edge[1];
    risk += hazard(edge);
    meters += length;
    ascent += Math.max(0, rise);
    maxGrade = Math.max(maxGrade, Math.abs(rise) / length);
    cellDistance += Math.hypot(dr, dc);
  }
  const cost = graph.energy_weight * energy + graph.risk_weight * risk;
  if (
    !Number.isFinite(cost) ||
    Math.abs(cost - best.get(end)) > 1e-8 ||
    cost < 0
  )
    throw new Error("Browser route failed cost validation");
  const cells = nodes.map(at);
  const props = {
    solver: "classical_astar",
    status: "optimal_on_grid",
    total_cost: cost,
    energy,
    hazard_score: risk,
    steps: nodes.length - 1,
    distance_cells: cellDistance,
    distance_m: meters,
    ascent_m: ascent,
    max_step_grade_percent: 100 * maxGrade,
    interpolated_vertices: cells.filter(([r, c]) => !grid.shot_count[r][c])
      .length,
    execution_time_ms: elapsed,
  };
  return {
    type: "FeatureCollection",
    features: [
      {
        type: "Feature",
        properties: props,
        geometry: {
          type: "LineString",
          coordinates: cells.map(([r, c]) => centerGeo(r, c).reverse()),
        },
      },
    ],
    meta: {
      mode: "browser_astar",
      dataset_id: grid.dataset_id,
      input,
      start_cell: s,
      end_cell: g,
      coordinate_system: grid.manifest.coordinates,
      geometry_model: grid.manifest.geometry,
      bbox_edges_wsen: grid.bbox,
      spacing_m_east_north: [grid.dx, grid.dy],
      sources: grid.manifest.sources,
      assumptions: grid.assumptions,
      quantum: null,
      ai_disclosure:
        "Codex-assisted routing and processing code. Mission data are sourced in the manifest.",
    },
  };
}
