"use strict";

const BBOX = { west: 77.35, south: 18.35, east: 77.75, north: 18.65 };
const API_BASE = window.location.protocol === "file:" ? "http://127.0.0.1:8000" : "";
const GRID_SIZE = 20;
const DEMO = {
  start: [18.44, 77.45],
  end: [18.52, 77.62],
  weights: { slope: 0.35, radiation: 0.45 },
};
const OFFLINE_OBSTACLES = [[10, 10], [9, 10], [10, 9], [11, 10], [10, 11]];
const OFFLINE_HAZARD = [[8, 9], [8, 10], [8, 11], [9, 9], [9, 10], [9, 11], [10, 8], [10, 9], [10, 10], [10, 11], [11, 9], [11, 10], [11, 11], [12, 10]];
const OFFLINE_PATHS = {
  classical: [[13, 5], [12, 6], [11, 7], [10, 8], [9, 8], [8, 9], [8, 10], [8, 11], [8, 12], [8, 13]],
  quantum: [[13, 5], [13, 6], [13, 7], [13, 8], [13, 9], [13, 10], [12, 11], [11, 12], [10, 13], [9, 13], [8, 13]],
};
const $ = (id) => document.getElementById(id);
const mapSvg = $("terrainMap");
let currentResponse = null;
let selectedEndpoint = "start";
let currentCraterCells = new Set();

function setAlert(message, kind = "error") {
  const alert = $("alert");
  alert.textContent = message;
  alert.className = `alert ${kind === "warning" ? "warning" : kind === "success" ? "success" : ""}`;
  alert.hidden = !message;
}

function setService(online, message) {
  $("serviceDot").className = `dot ${online ? "online" : "offline"}`;
  $("serviceText").textContent = message;
}

function cellFromLatLon([lat, lon]) {
  return [
    Math.round((BBOX.north - lat) / (BBOX.north - BBOX.south) * (GRID_SIZE - 1)),
    Math.round((lon - BBOX.west) / (BBOX.east - BBOX.west) * (GRID_SIZE - 1)),
  ];
}

function latLonFromCell([row, col]) {
  return [
    BBOX.north - row / (GRID_SIZE - 1) * (BBOX.north - BBOX.south),
    BBOX.west + col / (GRID_SIZE - 1) * (BBOX.east - BBOX.west),
  ];
}

function geoPoint([lon, lat]) {
  const x = 41 + (lon - BBOX.west) / (BBOX.east - BBOX.west) * (19 * 48);
  const y = 41 + (BBOX.north - lat) / (BBOX.north - BBOX.south) * (19 * 48);
  return [x, y];
}

function currentEndpoints() {
  return {
    start: [Number($("startLat").value), Number($("startLon").value)],
    end: [Number($("endLat").value), Number($("endLon").value)],
  };
}

function fillInputs(start, end) {
  $("startLat").value = Number(start[0]).toFixed(2);
  $("startLon").value = Number(start[1]).toFixed(2);
  $("endLat").value = Number(end[0]).toFixed(2);
  $("endLon").value = Number(end[1]).toFixed(2);
}

function updateWeights() {
  const slope = Number($("slopeWeight").value);
  const radiation = Number($("radiationWeight").value);
  const total = slope + radiation;
  $("slopeValue").textContent = `${slope}%`;
  $("radiationValue").textContent = `${radiation}%`;
  $("weightTotal").textContent = `${total}%`;
  $("weightTotal").style.color = total > 100 ? "var(--red)" : "var(--green)";
  setAlert(total > 100 ? "Slope and radiation shares add to more than 100%. Lower one slider before running the route." : "", "warning");
}

function classForHazard(value) {
  if (value >= 0.72) return "#91483b";
  if (value >= 0.48) return "#65523a";
  if (value >= 0.25) return "#39483b";
  return "#263832";
}

function renderMap(response = currentResponse) {
  const meta = response?.meta || {};
  const hazard = meta.hazard_grid || [];
  currentCraterCells = new Set((meta.crater_cells || []).map((cell) => cell.join(",")));
  const { start, end } = currentEndpoints();
  const startPoint = geoPoint([start[1], start[0]]);
  const endPoint = geoPoint([end[1], end[0]]);
  const content = [];
  content.push(`<defs>
    <pattern id="craterPattern" width="8" height="8" patternTransform="rotate(45)" patternUnits="userSpaceOnUse"><rect width="8" height="8" fill="#733d35"/><path d="M0 0V8" stroke="#f08a6f" stroke-width="2" opacity=".65"/></pattern>
    <filter id="routeGlow" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="3" result="blur"/><feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
  </defs>`);
  for (let row = 0; row < GRID_SIZE; row++) {
    for (let col = 0; col < GRID_SIZE; col++) {
      const x = 20 + col * 48;
      const y = 20 + row * 48;
      const isCrater = currentCraterCells.has(`${row},${col}`);
      const value = Number(hazard[row]?.[col] ?? 0.12);
      const fill = isCrater ? "url(#craterPattern)" : classForHazard(value);
      content.push(`<rect x="${x}" y="${y}" width="43" height="43" rx="3" fill="${fill}" stroke="#83968b" stroke-opacity=".15" stroke-width="1"/>`);
      if (value >= 0.58 && !isCrater) content.push(`<rect x="${x}" y="${y}" width="43" height="43" rx="3" fill="#e7a450" opacity=".15"/>`);
    }
  }
  if (response?.features) {
    for (const feature of response.features) {
      const solver = feature.properties.solver;
      const isClassical = solver === "classical_astar" || solver === "classical_astar_fallback";
      const color = isClassical ? "#72b9f7" : "#ffb76b";
      const dash = isClassical ? "" : `stroke-dasharray="8 7"`;
      const points = feature.geometry.coordinates.map(geoPoint).map((p) => p.join(",")).join(" ");
      content.push(`<polyline points="${points}" fill="none" stroke="#111917" stroke-width="10" stroke-linejoin="round" stroke-linecap="round" opacity=".82"/>`);
      content.push(`<polyline points="${points}" fill="none" stroke="${color}" stroke-width="4.5" stroke-linejoin="round" stroke-linecap="round" ${dash} filter="url(#routeGlow)"/>`);
    }
  }
  for (const key of currentCraterCells) {
    const [row, col] = key.split(",").map(Number);
    content.push(`<rect x="${20 + col * 48}" y="${20 + row * 48}" width="43" height="43" rx="3" fill="none" stroke="#ff8c6f" stroke-width="1.5"/>`);
  }
  content.push(`<circle cx="${startPoint[0]}" cy="${startPoint[1]}" r="9" fill="#72b9f7" stroke="#eaf4fa" stroke-width="3"/><circle cx="${startPoint[0]}" cy="${startPoint[1]}" r="17" fill="none" stroke="#72b9f7" stroke-opacity=".45"/>`);
  content.push(`<rect x="${endPoint[0] - 8}" y="${endPoint[1] - 8}" width="16" height="16" rx="2" fill="#ffb76b" stroke="#fff0d9" stroke-width="3" transform="rotate(45 ${endPoint[0]} ${endPoint[1]})"/>`);
  mapSvg.innerHTML = content.join("");
}

function addOfflineHazardGrid() {
  const grid = Array.from({ length: GRID_SIZE }, () => Array(GRID_SIZE).fill(0.12));
  for (const [row, col] of OFFLINE_HAZARD) grid[row][col] = 0.72;
  for (const [row, col] of [[9, 8], [10, 8], [11, 8], [12, 9], [12, 10], [12, 11]]) grid[row][col] = 0.52;
  for (const [row, col] of OFFLINE_OBSTACLES) grid[row][col] = 1;
  return grid;
}

function pathFeature(solver, cells, stats, status) {
  return {
    type: "Feature",
    properties: { solver, ...stats, status },
    geometry: {
      type: "LineString",
      coordinates: cells.map((cell) => {
        const [lat, lon] = latLonFromCell(cell);
        return [lon, lat];
      }),
    },
  };
}

function offlinePreview() {
  const classic = pathFeature("classical_astar", OFFLINE_PATHS.classical,
    { total_cost: 22.84, energy: 12.7, hazard_score: 1.81, steps: 9, distance_cells: 10.66, execution_time_ms: 2.1 }, "curated_offline_preview");
  const quantum = pathFeature("qaoa_waypoint_subgraph", OFFLINE_PATHS.quantum,
    { total_cost: 25.31, energy: 15.9, hazard_score: 1.29, steps: 10, distance_cells: 11.24, execution_time_ms: 842.0 }, "curated_offline_preview");
  const delta = quantum.properties.total_cost - classic.properties.total_cost;
  return {
    type: "FeatureCollection",
    features: [classic, quantum],
    metrics: {
      classical: classic.properties,
      quantum: quantum.properties,
      comparison: { cost_delta_quantum_minus_classical: delta, cost_delta_percent: delta / classic.properties.total_cost * 100, lower_cost_solver: "classical", hazard_delta_quantum_minus_classical: -0.52, step_delta_quantum_minus_classical: 1 },
    },
    meta: { bbox: [BBOX.west, BBOX.south, BBOX.east, BBOX.north], grid_size: GRID_SIZE,
      start_cell: OFFLINE_PATHS.classical[0], end_cell: OFFLINE_PATHS.classical.at(-1),
      weights: { slope: 0.35, radiation: 0.45, crater: 0.2 }, quantum_status: "curated_offline_preview",
      crater_cells: OFFLINE_OBSTACLES, hazard_grid: addOfflineHazardGrid() },
  };
}

function displayResults(response, preview) {
  const [classic, quantum] = response.features;
  const cm = classic.properties;
  const qm = quantum.properties;
  const metrics = response.metrics;
  const fallback = String(qm.status).startsWith("fallback_");
  const astarFallback = qm.status === "fallback_classical_astar";
  $("quantumMetricTitle").textContent = astarFallback ? "A* FALLBACK" : fallback ? "WAYPOINT FALLBACK" : "QAOA WAYPOINT";
  $("quantumLegendLabel").textContent = astarFallback ? "A* fallback" : fallback ? "Waypoint graph fallback" : "QAOA waypoint route";
  $("deltaUnit").textContent = fallback ? "fallback cost vs A*" : "QAOA cost vs A*";
  $("comparison").hidden = false;
  $("classicalCost").textContent = Number(cm.total_cost).toFixed(2);
  $("quantumCost").textContent = Number(qm.total_cost).toFixed(2);
  $("costDelta").textContent = `${metrics.comparison.cost_delta_percent >= 0 ? "+" : ""}${Number(metrics.comparison.cost_delta_percent).toFixed(1)}%`;
  $("classicalDistance").textContent = `${Number(cm.distance_cells).toFixed(1)} cells`;
  $("quantumDistance").textContent = `${Number(qm.distance_cells).toFixed(1)} cells`;
  $("classicalHazard").textContent = Number(cm.hazard_score).toFixed(2);
  $("quantumHazard").textContent = Number(qm.hazard_score).toFixed(2);
  $("quantumSteps").textContent = qm.steps;
  $("solverStatus").textContent = qm.status.replaceAll("_", " ").slice(0, 20);
  const delta = Number(metrics.comparison.cost_delta_percent);
  $("comparisonText").textContent = fallback
    ? astarFallback
      ? "QAOA did not return a valid path, so the API returned the valid A* route for both lines. This is a safe fallback, not a quantum comparison."
      : "QAOA samples did not contain a valid flow-conserving route, so the exact waypoint-graph path is shown as a classical fallback."
    : delta >= 0
      ? `The waypoint route costs ${delta.toFixed(1)}% more on this map while its hazard score changes by ${Number(metrics.comparison.hazard_delta_quantum_minus_classical).toFixed(2)}. A* remains the full-grid optimum.`
      : `The waypoint route costs ${Math.abs(delta).toFixed(1)}% less in this sample. Check the same terrain weights and grid when interpreting the result.`;
  $("resultSource").textContent = preview
    ? "VISUAL BACKUP PREVIEW · Curated illustration only; no live solver ran and values are not measured outputs."
    : fallback
      ? `LIVE API RESULT · ${qm.status.replaceAll("_", " ")} · fallback route validated against the terrain.`
      : `LIVE API RESULT · QAOA status: ${qm.status} · costs rescored from each returned route.`;
  $("resultBanner").hidden = false;
  $("resultBanner").className = `result-banner${preview ? " preview" : ""}`;
  $("resultBanner").textContent = preview
    ? "Backend unavailable or slow. Showing the labeled offline walkthrough so the route comparison remains visible."
    : fallback
      ? "The solver returned a valid fallback route. The route comparison is labeled to show that QAOA did not supply this path."
      : "Live comparison complete. Both paths are drawn over the same generated terrain.";
  currentResponse = response;
  renderMap(response);
  $("comparison").scrollIntoView({ behavior: "smooth", block: "nearest" });
}

function validateForm() {
  const { start, end } = currentEndpoints();
  if (![...start, ...end].every(Number.isFinite)) return "Enter a numeric latitude and longitude for both endpoints.";
  const inside = ([lat, lon]) => lat >= BBOX.south && lat <= BBOX.north && lon >= BBOX.west && lon <= BBOX.east;
  if (!inside(start) || !inside(end)) return "One endpoint is outside the Jezero map window. Use 18.35–18.65° N and 77.35–77.75° E.";
  if (cellFromLatLon(start).join(",") === cellFromLatLon(end).join(",")) return "Start and destination land in the same grid cell. Pick a farther destination.";
  const total = Number($("slopeWeight").value) + Number($("radiationWeight").value);
  if (total > 100) return "Slope and radiation shares add to more than 100%. Lower one slider before running the route.";
  return "";
}

async function runRoute({ allowPreview = false } = {}) {
  const error = validateForm();
  if (error) { setAlert(error, "warning"); return; }
  const start = currentEndpoints().start;
  const end = currentEndpoints().end;
  const request = {
    start,
    end,
    weights: {
      slope: Number($("slopeWeight").value) / 100,
      radiation: Number($("radiationWeight").value) / 100,
    },
  };
  const button = $("runRoute");
  button.disabled = true;
  button.innerHTML = "Solving both routes <span aria-hidden=\"true\">…</span>";
  setAlert("Building the terrain and running A* plus QAOA. The route will appear here when the solver responds.", "warning");
  let backendResponded = false;
  let timeoutId;
  try {
    const controller = new AbortController();
    timeoutId = window.setTimeout(() => controller.abort(), 120000);
    const response = await fetch(`${API_BASE}/api/route`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
      signal: controller.signal,
    });
    backendResponded = true;
    const body = await response.json();
    if (!response.ok) {
      const detail = typeof body.detail === "string" ? body.detail : body.detail?.message || "The route solver returned an error.";
      throw new Error(detail);
    }
    if (!Array.isArray(body.features) || body.features.length !== 2) throw new Error("The server response did not include both route features.");
    setAlert("", "success");
    displayResults(body, false);
    setService(true, "Local router connected");
  } catch (error) {
    const detail = error.name === "AbortError" ? "The live route took over 120 seconds." : error.message;
    setAlert(`${detail}${allowPreview ? " Loading the labeled offline walkthrough." : ""}`, "warning");
    if (error.name === "AbortError") {
      setService(true, "Router connected · QAOA timed out");
    } else if (backendResponded) {
      setService(true, "Router connected · solver error");
    } else {
      setService(false, "Router unavailable");
    }
    if (allowPreview) {
      window.setTimeout(() => {
        const preview = offlinePreview();
        displayResults(preview, true);
      }, 350);
    }
  } finally {
    window.clearTimeout(timeoutId);
    button.disabled = false;
    button.innerHTML = "Run route comparison <span aria-hidden=\"true\">→</span>";
  }
}

function onMapClick(event) {
  const rect = mapSvg.getBoundingClientRect();
  const x = (event.clientX - rect.left) / rect.width * 1040;
  const y = (event.clientY - rect.top) / rect.height * 1040;
  const col = Math.floor((x - 20) / 48);
  const row = Math.floor((y - 20) / 48);
  if (row < 0 || col < 0 || row >= GRID_SIZE || col >= GRID_SIZE) {
    setAlert("That click is outside the terrain grid. Choose a cell inside the map boundary.", "warning"); return;
  }
  if (currentCraterCells.has(`${row},${col}`)) {
    setAlert("That cell is inside an impassable crater wall. Choose a clear cell for the endpoint.", "warning"); return;
  }
  const [lat, lon] = latLonFromCell([row, col]);
  const prefix = selectedEndpoint === "start" ? "start" : "end";
  $(`${prefix}Lat`).value = lat.toFixed(2);
  $(`${prefix}Lon`).value = lon.toFixed(2);
  setAlert(`${selectedEndpoint === "start" ? "Start" : "Destination"} moved to grid cell ${row}, ${col}.`, "success");
  renderMap(currentResponse);
}

function chooseEndpoint(which) {
  selectedEndpoint = which;
  $("pickStart").classList.toggle("active", which === "start");
  $("pickEnd").classList.toggle("active", which === "end");
}

async function checkHealth() {
  try {
    const response = await fetch(`${API_BASE}/api/health`, { signal: AbortSignal.timeout(2500) });
    if (!response.ok) throw new Error("API unavailable");
    const health = await response.json();
    const [west, south, east, north] = health.bbox;
    if (Math.abs(west - BBOX.west) > 1e-8 || Math.abs(south - BBOX.south) > 1e-8 || Math.abs(east - BBOX.east) > 1e-8 || Math.abs(north - BBOX.north) > 1e-8) {
      throw new Error("Frontend and API map bounds differ. Restart the local server with this project version.");
    }
    if (health.terrain) {
      currentResponse = { meta: health.terrain };
      renderMap(currentResponse);
    }
    setService(true, "Local router connected");
  } catch (error) {
    setService(false, "Offline / solver unavailable");
  }
}

$("slopeWeight").addEventListener("input", updateWeights);
$("radiationWeight").addEventListener("input", updateWeights);
$("pickStart").addEventListener("click", () => chooseEndpoint("start"));
$("pickEnd").addEventListener("click", () => chooseEndpoint("end"));
$("runRoute").addEventListener("click", () => runRoute());
$("loadDemo").addEventListener("click", () => {
  fillInputs(DEMO.start, DEMO.end);
  $("slopeWeight").value = String(DEMO.weights.slope * 100);
  $("radiationWeight").value = String(DEMO.weights.radiation * 100);
  updateWeights();
  chooseEndpoint("start");
  runRoute({ allowPreview: true });
});
mapSvg.addEventListener("click", onMapClick);
for (const id of ["startLat", "startLon", "endLat", "endLon"]) {
  $(id).addEventListener("change", () => { renderMap(currentResponse); setAlert(""); });
}
fillInputs(DEMO.start, DEMO.end);
updateWeights();
renderMap(null);
checkHealth();
