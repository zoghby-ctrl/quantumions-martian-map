"use strict";
const $ = (id) => document.getElementById(id);
let grid = null,
  result = null,
  placing = null,
  generation = 0,
  activeJob = null;
let pending = false,
  quantumPending = false,
  available = false,
  online = false,
  recorded = false;
const onDevice = document.documentElement.dataset.runtime === "browser";
const stopName = {
  13: "Butler landing",
  700: "Sol 700 site",
  1100: "Sol 1100 site",
};
const names = { start: "Start", end: "Destination" };

function statusMessage(text, error = false) {
  $("status").textContent = text;
  $("status").classList.toggle("error", error);
}
async function jsonRequest(url, options = {}) {
  const response = await fetch(url, {
    ...options,
    signal: options.signal || AbortSignal.timeout(12000),
  });
  if (!response.ok) {
    const info = await response.json().catch(() => ({}));
    throw new Error(
      typeof info.detail === "string"
        ? info.detail
        : "Request failed (HTTP " + response.status + ")",
    );
  }
  return response.json();
}
function point(side) {
  return [$(side + "Lat").valueAsNumber, $(side + "Lon").valueAsNumber];
}
function setPoint(side, p, sol = "custom") {
  $(side + "Lat").value = p[0];
  $(side + "Lon").value = p[1];
  $(side + "Site").value = String(sol);
  showCoordinates(side);
}
function showCoordinates(side) {
  const [lat, lon] = point(side);
  $(side + "View").textContent =
    Number.isFinite(lat) && Number.isFinite(lon)
      ? lat.toFixed(5) + "° N   " + lon.toFixed(5) + "° E"
      : "Enter both coordinates";
}
function choosePlacement(side) {
  placing = side;
  for (const s of Object.keys(names)) {
    $(s + "Pick").setAttribute("aria-pressed", String(placing === s));
    $(s + "Pick").textContent = placing === s ? "Tap a cell" : "Place on map";
  }
}
function buildControls() {
  for (const [index, side] of ["start", "end"].entries()) {
    const label = names[side];
    const panel = document.createElement("div");
    panel.className = "endpoint";
    panel.innerHTML = `<div class="endpoint-head"><span class="station"><b class="letter ${side}">${index ? "B" : "A"}</b>${label}</span><button class="pick" id="${side}Pick" aria-label="Place ${label.toLowerCase()} on map" aria-pressed="false">Place on map</button></div>
      <select id="${side}Site" aria-label="${label} site"><option value="custom">Map point</option></select><p class="coord-view" id="${side}View"></p>`;
    $("endpoints").append(panel);
    for (const site of grid.stops)
      $(side + "Site").add(
        new Option(
          stopName[site.sol] +
            (site.sol === 13 ? " · Sol 13" : " · Perseverance"),
          site.sol,
        ),
      );
    const row = document.createElement("div");
    row.className = "coordinate-row";
    for (const [key, unit] of [
      ["Lat", "latitude"],
      ["Lon", "longitude"],
    ]) {
      const el = document.createElement("label");
      el.textContent = label + " " + unit;
      const input = document.createElement("input");
      input.type = "number";
      input.step = "any";
      input.id = side + key;
      input.min = key === "Lat" ? grid.bbox[1] : grid.bbox[0];
      input.max = key === "Lat" ? grid.bbox[3] : grid.bbox[2];
      input.addEventListener("input", () => {
        $(side + "Site").value = "custom";
        showCoordinates(side);
        invalidate();
      });
      el.append(input);
      row.append(el);
    }
    $("coordinateFields").append(row);
    $(side + "Site").onchange = () => {
      const site = grid.stops.find(
        (s) => s.sol === Number($(side + "Site").value),
      );
      if (site) setPoint(side, [...site.lonlat].reverse(), site.sol);
      else {
        document.querySelector(".coords").open = true;
        $(side + "Lat").focus();
      }
      choosePlacement(null);
      invalidate();
    };
    $(side + "Pick").onclick = () => {
      choosePlacement(placing === side ? null : side);
      if (placing) {
        statusMessage(
          "Tap a clear cell to set the " + label.toLowerCase() + ".",
        );
        svg.scrollIntoView({ block: "nearest" });
      }
    };
  }
}
function defaults() {
  for (const [s, sol] of [
    ["start", 13],
    ["end", 1100],
  ])
    setPoint(
      s,
      [...grid.stops.find((p) => p.sol === sol).lonlat].reverse(),
      sol,
    );
  $("slope").value = 35;
  $("gaps").value = 45;
  weights();
  choosePlacement(null);
}
function weights() {
  $("slopeValue").textContent = $("slope").value + "%";
  $("gapValue").textContent = $("gaps").value + "%";
  $("marginValue").textContent =
    100 - Number($("slope").value) - Number($("gaps").value) + "%";
}
function requestData() {
  return {
    dataset_id: grid.dataset_id,
    start: point("start"),
    end: point("end"),
    weights: {
      slope: Number($("slope").value) / 100,
      interpolation: Number($("gaps").value) / 100,
    },
  };
}
function inputError() {
  const cells = [cellAt(...point("start")), cellAt(...point("end"))];
  if (cells.some((c) => !c))
    return "Enter valid coordinates inside the map bounds.";
  if (cells.some(([r, c]) => grid.excluded[r][c]))
    return "An endpoint is inside a modeled exclusion.";
  if (cells[0][0] === cells[1][0] && cells[0][1] === cells[1][1])
    return "Choose two different routing cells.";
  return "";
}
function buttons() {
  $("run").disabled =
    !grid ||
    pending ||
    quantumPending ||
    recorded ||
    !online ||
    Boolean(inputError());
  $("compare").disabled =
    !result || recorded || pending || quantumPending || !available;
  $("cancel").hidden = !quantumPending;
  $("export").disabled = !result;
  $("service").textContent = recorded ? "Recorded traverse" : onDevice ? "On-device planner" : online ? "Planner online" : "API offline";
  for (const el of document.querySelectorAll(
    "#endpoints button,#endpoints select,#coordinateFields input,#slope,#gaps,#swap",
  ))
    el.disabled = recorded;
}
async function terminate(job) {
  if (job)
    await jsonRequest("api/quantum/" + job, { method: "DELETE" }).catch(
      () => {},
    );
}
function invalidate() {
  generation++;
  if (activeJob) void terminate(activeJob);
  activeJob = null;
  pending = false;
  quantumPending = false;
  result = null;
  $("diagnostics").replaceChildren();
  $("labStatus").textContent = available
    ? ""
    : onDevice
      ? "This edition computes A* on your device. Open the recorded traverse to inspect a measured Qiskit run."
      : online
        ? "Simulator packages unavailable on this server."
        : "Live simulation requires the API.";
  $("briefBody").innerHTML =
    '<p class="empty">Plan a traverse to see its distance and elevation profile.</p>';
  const error = inputError();
  statusMessage(
    error ||
      (online
        ? "Ready to plan with these inputs."
        : "API offline. Open the recorded traverse to explore the example."),
    Boolean(error),
  );
  buttons();
  drawRoutes();
}
function matching(data, request) {
  const x = data.meta.input;
  return (
    data.meta.dataset_id === grid.dataset_id &&
    ["start", "end"].every((s) => x[s].every((v, i) => v === request[s][i])) &&
    x.weights.slope === request.weights.slope &&
    x.weights.interpolation === request.weights.interpolation
  );
}
function showResult() {
  const feature = result.features[0],
    m = feature.properties,
    coordinates = feature.geometry.coordinates;
  const profile = coordinates.map((p) => {
    const [r, c] = cellAt(p[1], p[0]);
    return grid.elevation_m[r][c];
  });
  const low = Math.min(...profile),
    high = Math.max(...profile);
  const distances = [0];
  for (let i = 1; i < coordinates.length; i++) {
    const a = cellAt(coordinates[i - 1][1], coordinates[i - 1][0]),
      b = cellAt(coordinates[i][1], coordinates[i][0]);
    distances.push(
      distances[i - 1] +
        Math.hypot((b[0] - a[0]) * grid.dy, (b[1] - a[1]) * grid.dx),
    );
  }
  const trace = profile
    .map(
      (z, i) =>
        (2 + (296 * distances[i]) / distances.at(-1)).toFixed(1) +
        "," +
        (58 - (48 * (z - low)) / Math.max(1, high - low)).toFixed(1),
    )
    .join(" ");
  $("briefBody").innerHTML =
    `<div class="metric-row"><div><b>${(m.distance_m / 1000).toFixed(2)} km</b><span>Map distance</span></div><div><b>${m.ascent_m.toFixed(0)} m</b><span>Total ascent</span></div><div><b>${m.max_step_grade_percent.toFixed(1)}%</b><span>Steepest step</span></div></div>
    <div class="profile"><div><h3>Elevation profile</h3><p>${low.toLocaleString()} to ${high.toLocaleString()} m above the Mars areoid.</p></div>
    <svg viewBox="0 0 300 66" preserveAspectRatio="none" role="img" aria-label="Route elevation against cumulative distance"><polygon points="2,65 ${trace} 298,65" fill="#ecdaca"/><polyline points="${trace}" fill="none" stroke="#9e3f24" stroke-width="2" vector-effect="non-scaling-stroke"/></svg></div>
    <p class="empty">${m.steps} steps · ${m.interpolated_vertices} of ${coordinates.length} vertices use interpolated elevation. Weighted score ${m.total_cost.toFixed(2)}.</p>`;
  buttons();
  drawRoutes();
}
async function runRoute() {
  if (pending || quantumPending || recorded || !online) return;
  invalidate();
  if (inputError()) return;
  const ticket = generation,
    request = requestData();
  pending = true;
  buttons();
  statusMessage("Searching the full terrain grid…");
  try {
    const data = onDevice
      ? await browserRoute(grid, request)
      : await jsonRequest("api/route", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(request),
        });
    if (ticket !== generation) return;
    if (!matching(data, request))
      throw new Error("Route and map versions differ. Reload the page.");
    result = data;
    showResult();
    statusMessage("Classical route ready. Endpoints snap to the MOLA grid.");
  } catch (e) {
    if (ticket === generation) {
      statusMessage(e.message, true);
      $("replay").hidden = false;
    }
  } finally {
    if (ticket === generation) {
      pending = false;
      buttons();
    }
  }
}
function showLab() {
  const q = result.meta.quantum,
    m = result.features[1].properties;
  const fallback = m.status.startsWith("fallback");
  const name = fallback
    ? m.solver === "exact_waypoint_dijkstra"
      ? "Exact waypoint fallback"
      : "A* fallback"
    : m.status === "optimal_on_waypoint_graph"
      ? "QAOA matched the waypoint optimum"
      : "Feasible QAOA route";
  $("labStatus").textContent =
    (recorded ? "Recorded · " : "") + name + ". " + (q.fallback_reason || "");
  const fmt = (v, suffix = "", digits = 2) =>
    v == null ? "—" : Number(v).toFixed(digits) + suffix;
  const values = [
    ["Backend", q.backend ? q.backend + " simulator" : "Unavailable"],
    ["Qubits / depth", q.n_qubits + " / " + q.qaoa_reps],
    ["Shots", q.shots],
    ["Waypoint reference", fmt(q.exact_waypoint_graph_cost)],
    ["Returned score", fmt(m.total_cost)],
    ["Gap vs. full grid", fmt(q.grid_gap_percent, "%")],
    ["Gap vs. waypoints", fmt(q.waypoint_gap_percent, "%")],
    [
      "Valid samples",
      q.valid_path_probability == null
        ? "—"
        : fmt(100 * q.valid_path_probability, "%"),
    ],
    ["Graph preparation", fmt(q.preprocessing_ms, " ms", 1)],
    ["Optimize & sample", fmt(q.optimization_sampling_ms, " ms", 1)],
    ["Postprocessing", fmt(q.postprocessing_ms, " ms", 1)],
    ["Total incl. imports", fmt(q.total_ms / 1000, " s")],
  ];
  if (result.meta.worker_wall_ms != null)
    values.push([
      "Worker wall time",
      fmt(result.meta.worker_wall_ms / 1000, " s"),
    ]);
  const list = document.createElement("dl");
  list.className = "diag-grid";
  for (const [label, value] of values) {
    const div = document.createElement("div"),
      dt = document.createElement("dt"),
      dd = document.createElement("dd");
    dt.textContent = label;
    dd.textContent = value ?? "—";
    div.append(dt, dd);
    list.append(div);
  }
  $("diagnostics").replaceChildren(list);
}
async function compare() {
  if (!result || quantumPending || recorded) return;
  const ticket = ++generation,
    request = requestData();
  quantumPending = true;
  buttons();
  $("labStatus").textContent =
    "Running a bounded simulation. The classical route remains available.";
  let job = null;
  try {
    const started = await jsonRequest("api/quantum", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
    });
    job = started.job_id;
    if (ticket !== generation) {
      await terminate(job);
      return;
    }
    activeJob = job;
    while (ticket === generation) {
      const info = await jsonRequest("api/quantum/" + job);
      if (ticket !== generation) return;
      if (info.status === "running") {
        await new Promise((resolve) => setTimeout(resolve, 350));
        continue;
      }
      if (info.status !== "complete")
        throw new Error(info.detail || "Simulation " + info.status + ".");
      if (!matching(info.result, request))
        throw new Error("Comparison inputs differ from the current traverse.");
      result = info.result;
      result.meta.worker_wall_ms = info.worker_wall_ms;
      result.meta.quantum_cache_hit = started.cached;
      showResult();
      showLab();
      if (started.cached)
        $("labStatus").textContent += " Cached result for these exact inputs.";
      break;
    }
  } catch (e) {
    if (ticket === generation) {
      $("labStatus").textContent = e.message;
      await terminate(job);
    }
  } finally {
    if (ticket === generation) {
      activeJob = null;
      quantumPending = false;
      buttons();
    }
  }
}
function sourcePanel() {
  for (const site of grid.manifest.science_context) {
    const p = document.createElement("p"),
      title = document.createElement("strong"),
      a = document.createElement("a");
    title.textContent = "Sol " + site.sol + " · " + site.title + ". ";
    a.href = site.url;
    a.textContent = "Mission reference ↗";
    a.target = "_blank";
    a.rel = "noopener";
    p.append(title, site.note + " ", a);
    $("scienceNotes").append(p);
  }
  const descriptions = [
    "Elevation in meters above the Mars areoid, gridded at 128 pixels per degree.",
    "Observation counts identify cells whose elevation the mission team interpolated.",
    "The 6 m CTX orthoimage gives a finer view of the ground between grid centers.",
    "Published rover locations anchor the three selectable stops.",
  ];
  for (const [i, source] of grid.manifest.sources.entries()) {
    const card = document.createElement("article"),
      title = document.createElement("h3"),
      p = document.createElement("p"),
      a = document.createElement("a");
    title.textContent = source.name;
    p.textContent = descriptions[i];
    a.href = source.label;
    a.textContent = "Source record ↗";
    a.target = "_blank";
    a.rel = "noopener";
    card.append(title, p, a);
    $("sourceCards").append(card);
  }
  for (const text of [
    ...grid.assumptions,
    `Map bounds: ${grid.bbox[0]}–${grid.bbox[2]}° E and ${grid.bbox[1]}–${grid.bbox[3]}° N. Grid ${grid.rows} × ${grid.cols}. Version ${grid.dataset_id}.`,
  ]) {
    const p = document.createElement("p");
    p.textContent = text;
    $("modelText").append(p);
  }
  const a = document.createElement("a");
  a.href = "data/manifest.json";
  a.textContent = "Full product manifest and checksums ↗";
  $("modelText").append(a);
}
async function replay() {
  if (pending || recorded) return;
  invalidate();
  const ticket = generation;
  pending = true;
  buttons();
  $("replay").disabled = true;
  try {
    const data = await jsonRequest("data/recorded-route.json");
    if (ticket !== generation) return;
    defaults();
    if (!matching(data, requestData()))
      throw new Error("Recorded data do not match this map.");
    recorded = true;
    result = data;
    showResult();
    showLab();
    statusMessage(
      "Recorded traverse · " +
        data.meta.recorded_utc +
        ". Fixed inputs. Reset to leave replay.",
    );
  } catch (e) {
    if (ticket === generation) statusMessage(e.message, true);
  } finally {
    if (ticket === generation) {
      pending = false;
      buttons();
    }
    $("replay").disabled = false;
  }
}
async function init() {
  try {
    grid = await jsonRequest("data/terrain.json");
    buildControls();
    defaults();
    mapInit();
    sourcePanel();
    // Health only updates capability. Late responses cannot replace route geometry.
    const ticket = generation;
    if (onDevice) online = true;
    else
      try {
        const h = await jsonRequest("api/health");
        online = h.dataset_id === grid.dataset_id;
        available = online && h.quantum_packages_present;
      } catch {
        online = false;
      }
    $("service").textContent = onDevice
      ? "On-device planner"
      : online
        ? "Planner online"
        : "API offline";
    $("service").classList.toggle("online", online);
    $("replay").hidden = false;
    if (ticket === generation) {
      invalidate();
      if (online) await runRoute();
    } else if (!result && !pending && !quantumPending) {
      invalidate();
    } else buttons();
  } catch (e) {
    statusMessage("Map unavailable. " + e.message, true);
    $("service").textContent = "Map unavailable";
  }
}
$("swap").onclick = () => {
  if (!grid) return;
  const a = point("start"),
    b = point("end"),
    idA = $("startSite").value,
    idB = $("endSite").value;
  setPoint("start", b, idB);
  setPoint("end", a, idA);
  choosePlacement(null);
  invalidate();
};
$("reset").onclick = () => {
  if (!grid) return;
  recorded = false;
  defaults();
  fitMap();
  invalidate();
  if (online) void runRoute();
};
for (const [id, other] of [
  ["slope", "gaps"],
  ["gaps", "slope"],
])
  $(id).oninput = () => {
    $(other).value = Math.min(
      Number($(other).value),
      100 - Number($(id).value),
    );
    weights();
    invalidate();
  };
$("run").onclick = runRoute;
$("compare").onclick = compare;
$("replay").onclick = replay;
$("cancel").onclick = async () => {
  const id = activeJob,
    ticket = ++generation;
  activeJob = null;
  quantumPending = false;
  buttons();
  $("labStatus").textContent = "Canceling simulation…";
  try {
    const response = id ? await jsonRequest("api/quantum/" + id, { method: "DELETE" }) : null;
    if (ticket === generation)
      $("labStatus").textContent = id
        ? (response.status === "canceled" ? "Simulation canceled." : "Simulation already ended. The comparison was dismissed.")
        : "Request canceled. A worker that starts will receive a stop request.";
  } catch {
    if (ticket === generation)
      $("labStatus").textContent =
        "Stopped waiting. Server cutoff is 45 seconds.";
  }
};
$("export").onclick = () => {
  if (!result) return;
  const blob = new Blob([JSON.stringify(result, null, 2)], {
    type: "application/geo+json",
  });
  const url = URL.createObjectURL(blob),
    link = document.createElement("a");
  link.href = url;
  link.download =
    "marswalk-jezero" + (recorded ? "-recorded" : "") + "-route.geojson";
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
};
window.addEventListener("DOMContentLoaded", init);
