/* North-up local metric map. Display coordinates share the terrain's pixel edges. */
const svg = document.getElementById("map");
const ns = "http://www.w3.org/2000/svg";
const W = 1000;
let H = 610;
let zoom = 1,
  cx = W / 2,
  cy = H / 2;
let drag = null;

function shape(tag, attrs, parent, text) {
  const el = document.createElementNS(ns, tag);
  for (const [key, value] of Object.entries(attrs)) el.setAttribute(key, value);
  if (text !== undefined) el.textContent = text;
  parent.append(el);
  return el;
}

function cellAt(lat, lon) {
  const [w, s, e, n] = grid.bbox;
  if (
    !Number.isFinite(lat) ||
    !Number.isFinite(lon) ||
    lat < s ||
    lat > n ||
    lon < w ||
    lon > e
  )
    return null;
  return [
    Math.min(grid.rows - 1, Math.floor(((n - lat) / (n - s)) * grid.rows)),
    Math.min(grid.cols - 1, Math.floor(((lon - w) / (e - w)) * grid.cols)),
  ];
}

function centerGeo(r, c) {
  const [w, s, e, n] = grid.bbox;
  return [
    n - ((r + 0.5) * (n - s)) / grid.rows,
    w + ((c + 0.5) * (e - w)) / grid.cols,
  ];
}

function project([lon, lat]) {
  const [w, s, e, n] = grid.bbox;
  return [((lon - w) / (e - w)) * W, ((n - lat) / (n - s)) * H];
}

function mapInit() {
  for (const [id, name, initial] of [["orbit", "CTX imagery", 100], ["slope", "Slope", 45], ["coverage", "Interpolated elevation", 45], ["mask", "Exclusions", 75]]) {
    const input = document.createElement("input"), label = document.createElement("label"), value = document.createElement("output");
    input.type = "range"; input.min = 0; input.max = 100; input.value = initial; input.id = id + "Opacity";
    label.htmlFor = input.id; value.textContent = initial + "%"; label.append(name, value);
    input.oninput = () => { value.textContent = input.value + "%"; drawRaster(); };
    $("opacityControls").append(label, input);
  }
  H = (W * grid.rows * grid.dy) / (grid.cols * grid.dx);
  document.querySelector(".map-frame").style.setProperty("--map-aspect", W / H);
  $("orbit").setAttribute("width", W);
  $("orbit").setAttribute("height", H);
  fitMap();
  drawRaster();
}
function fitMap() {
  zoom = 1;
  cx = W / 2;
  cy = H / 2;
  viewport();
}

function viewport() {
  if (!grid) return;
  const vw = W / zoom,
    vh = H / zoom;
  cx = Math.max(vw / 2, Math.min(W - vw / 2, cx));
  cy = Math.max(vh / 2, Math.min(H - vh / 2, cy));
  svg.setAttribute("viewBox", [cx - vw / 2, cy - vh / 2, vw, vh].join(" "));
  // Meet preserves physical proportions, including letterbox margins on narrow screens.
  const scale = svg.getScreenCTM()?.a || 1;
  const km = zoom > 2 ? 1 : 2;
  $("scaleBar").style.width =
    ((km * 1000) / (grid.cols * grid.dx)) * W * scale + "px";
  $("scaleText").textContent = km + " km";
  drawRoutes();
}

function drawRaster() {
  if (!grid) return;
  const layer = $("raster");
  layer.replaceChildren();
  const width = W / grid.cols,
    height = H / grid.rows;
  const slopeOpacity = Number($("slopeOpacity").value) / 100;
  const coverageOpacity = Number($("coverageOpacity").value) / 100;
  const maskOpacity = Number($("maskOpacity").value) / 100;
  $("orbit").style.display = $("imagery").checked ? "" : "none";
  $("orbit").style.opacity = Number($("orbitOpacity").value) / 100;
  for (let r = 0; r < grid.rows; r++)
    for (let c = 0; c < grid.cols; c++) {
      const pos = {
        x: c * width,
        y: r * height,
        width: width + 0.015,
        height: height + 0.015,
      };
      if ($("slopeLayer").checked) {
        const pct = grid.slope_percent[r][c];
        shape(
          "rect",
          {
            ...pos,
            fill: pct < 5 ? "#ffe3a2" : pct < 12 ? "#d76e2f" : "#8e2929",
            opacity: slopeOpacity,
          },
          layer,
        );
      }
      if ($("coverageLayer").checked && grid.shot_count[r][c] === 0)
        shape("rect", { ...pos, fill: "#84b9e6", opacity: coverageOpacity }, layer);
      if ($("maskLayer").checked && grid.excluded[r][c])
        shape(
          "rect",
          { ...pos, fill: "url(#hatch)", opacity: maskOpacity },
          layer,
        );
    }
  const key = [];
  if ($("slopeLayer").checked)
    key.push("Slope · cream <5%, orange 5–12%, red ≥12%.");
  if ($("coverageLayer").checked)
    key.push(
      "Blue · MOLA elevation interpolated from neighboring observations.",
    );
  $("overlayKey").hidden = !key.length;
  $("overlayKey").textContent = key.join(" ");
  drawRoutes();
}
function drawRoutes() {
  if (!grid) return;
  const lines = $("tracks"),
    marks = $("markers");
  lines.replaceChildren();
  marks.replaceChildren();
  const unit = 1 / (svg.getScreenCTM()?.a || 1);
  const alt = result?.features[1];
  $("labLegend").hidden = !alt;
  if (alt)
    $("labLegend").lastElementChild.textContent =
      alt.properties.status.startsWith("fallback")
        ? "Classical fallback"
        : "QAOA waypoint";
  for (const [i, f] of (result?.features || []).entries()) {
    const points = f.geometry.coordinates
      .map((p) => project(p).join(","))
      .join(" ");
    const base = {
      points,
      fill: "none",
      "stroke-linejoin": "round",
      "stroke-linecap": "round",
      "vector-effect": "non-scaling-stroke",
    };
    if (!i)
      shape(
        "polyline",
        { ...base, stroke: "#122c36", "stroke-width": 6.5 },
        lines,
      );
    shape(
      "polyline",
      {
        ...base,
        stroke: i ? "#ffac5f" : "#8fe1ff",
        "stroke-width": i ? 3 : 3.5,
        "stroke-dasharray": i ? "6 6" : "none",
      },
      lines,
    );
  }
  if ($("sitesLayer").checked)
    for (const site of grid.stops) {
      const [x, y] = project(site.lonlat);
      shape(
        "path",
        {
          d: `M ${x} ${y - 4 * unit} l ${4 * unit} ${4 * unit} l ${-4 * unit} ${4 * unit} l ${-4 * unit} ${-4 * unit} Z`,
          fill: "#fff2c9",
          stroke: "#222",
          "stroke-width": unit,
        },
        marks,
      );
    }
  for (const [i, side] of ["start", "end"].entries()) {
    const cell = cellAt(...point(side));
    if (!cell) continue;
    const [x, y] = project(centerGeo(...cell).reverse());
    shape(
      "circle",
      {
        cx: x,
        cy: y,
        r: 10 * unit,
        fill: i ? "#943c24" : "#204653",
        stroke: "white",
        "stroke-width": 2 * unit,
      },
      marks,
    );
    shape(
      "text",
      {
        x,
        y: y + 4 * unit,
        fill: "white",
        "font-size": 12 * unit,
        "font-family": "system-ui",
        "font-weight": 700,
        "text-anchor": "middle",
      },
      marks,
      i ? "B" : "A",
    );
    if (svg.clientWidth > 480) {
      const label =
        $(side + "Site").selectedOptions[0]?.textContent?.split(" · ")[0] ||
        "Map point";
      const left = x > W * 0.72,
        dy = i ? -15 : 24;
      shape(
        "text",
        {
          x: x + (left ? -12 : 12) * unit,
          y: y + dy * unit,
          "text-anchor": left ? "end" : "start",
          fill: "white",
          stroke: "#20231f",
          "stroke-width": 3.5 * unit,
          "paint-order": "stroke",
          "font-size": 13 * unit,
          "font-weight": 650,
          "font-family": "system-ui",
        },
        marks,
        label,
      );
    }
  }
}
function localPoint(event) {
  return new DOMPoint(event.clientX, event.clientY).matrixTransform(
    svg.getScreenCTM().inverse(),
  );
}
function zoomBy(factor) {
  zoom = Math.min(5, Math.max(1, zoom * factor));
  viewport();
}
$("zoomIn").onclick = () => zoomBy(1.5);
$("zoomOut").onclick = () => zoomBy(1 / 1.5);
$("fit").onclick = fitMap;
svg.addEventListener("keydown", (event) => {
  const offset = {
    ArrowLeft: [-1, 0],
    ArrowRight: [1, 0],
    ArrowUp: [0, -1],
    ArrowDown: [0, 1],
  }[event.key];
  if (offset) {
    event.preventDefault();
    cx += (offset[0] * W) / zoom / 7;
    cy += (offset[1] * H) / zoom / 7;
    viewport();
  }
});
svg.addEventListener("pointerdown", (event) => {
  if (!grid || !event.isPrimary) return;
  drag = {
    id: event.pointerId,
    x: event.clientX,
    y: event.clientY,
    cx,
    cy,
    moved: false,
  };
  svg.setPointerCapture(event.pointerId);
});
svg.addEventListener("pointermove", (event) => {
  if (!grid) return;
  const p = localPoint(event),
    r = Math.floor((p.y / H) * grid.rows),
    c = Math.floor((p.x / W) * grid.cols);
  if (r >= 0 && c >= 0 && r < grid.rows && c < grid.cols)
    $("cellReadout").textContent =
      `${grid.elevation_m[r][c]} m · ${grid.slope_percent[r][c]}% grade · ${grid.shot_count[r][c]} MOLA shots`;
  if (!drag || event.pointerId !== drag.id) return;
  const dx = event.clientX - drag.x,
    dy = event.clientY - drag.y;
  if (Math.hypot(dx, dy) > 4) drag.moved = true;
  if (drag.moved) {
    const k = svg.getScreenCTM().a;
    cx = drag.cx - dx / k;
    cy = drag.cy - dy / k;
    viewport();
  }
});
svg.addEventListener("pointerup", (event) => {
  if (!drag || event.pointerId !== drag.id) return;
  const click = !drag.moved;
  drag = null;
  if (!click || !grid || recorded) return;
  const p = localPoint(event),
    r = Math.floor((p.y / H) * grid.rows),
    c = Math.floor((p.x / W) * grid.cols);
  if (r < 0 || c < 0 || r >= grid.rows || c >= grid.cols) return;
  if (grid.excluded[r][c]) {
    statusMessage(
      "That cell exceeds the modeled grade limit. Choose another cell.",
      true,
    );
    return;
  }
  if (!placing) {
    statusMessage(
      "Choose “Place on map” for the start or destination, then tap a cell.",
    );
    return;
  }
  setPoint(placing, centerGeo(r, c));
  choosePlacement(null);
  invalidate();
});
svg.addEventListener("pointercancel", () => {
  drag = null;
});
for (const id of [
  "imagery",
  "slopeLayer",
  "coverageLayer",
  "maskLayer",
  "sitesLayer",
])
  $(id).addEventListener("input", drawRaster);
new ResizeObserver(viewport).observe(svg);
