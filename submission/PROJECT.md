# Marswalk: A Martian Survival Map by Quantumions

**Challenge** · Interplanetary Survival Guide: Martian Map  
**Project** · https://zoghby-ctrl.github.io/quantumions-martian-map/  
**Demo presentation** · https://zoghby-ctrl.github.io/quantumions-martian-map/Marswalk.pdf  
**Source** · https://github.com/zoghby-ctrl/quantumions-martian-map/tree/codex/jezero-traverse

## Project summary

Marswalk helps an explorer compare possible traverses across the western delta of Jezero crater. The map pairs imagery from the Mars Reconnaissance Orbiter’s Context Camera with elevations and laser shot counts from Mars Global Surveyor. Perseverance waypoints give explorers real locations to visit. Choose a destination and adjust how strongly the route avoids steep ground or cells with interpolated elevations. The planner calculates a path, shows its distance and ascent, and exports the geometry with its sources and assumptions. An optional Qiskit experiment compares sampled waypoint routes with exact classical references. The public map calculates new classical routes and includes a recorded simulator run. Marswalk supports regional exploration and science discussion. Its coarse terrain grid cannot establish whether an astronaut could safely walk a route.

## Project details

### Planning a science traverse

Start at Octavia E. Butler landing, select another Perseverance stop or enter coordinates, and examine the CTX image. The slope layer reveals steep terrain. Turning on interpolated elevation shows where a MOLA cell contains no direct laser observation. Rover-site notes connect positions to the landing, the period following the Three Forks depot campaign, and the Margin Unit investigation. The mission waypoints retain their published coordinates. Route markers snap to the centers of the cells used in the calculation.

The default traverse links the sol 13 landing-area record to the sol 1100 rover position. At the default settings, A* covers **9.55 km** with **234 m** of cumulative ascent. The steepest individual step has **8.3%** grade. Six of the 19 vertices use interpolated elevation. Explorers can swap endpoints, change priorities, inspect the new profile, and download a Mars-coordinate GeoJSON FeatureCollection with both original and snapped positions, weights, model assumptions, metrics and source records.

### How the mission products fit together

The crop spans 77.265625–77.640625° east longitude and 18.3359375–18.5546875° planetocentric north latitude. The CTX planetary equirectangular GeoTIFF is cropped using its native Mars radius, then averaged for display. It provides visual context at much finer resolution than the cost grid. The 48 × 28 terrain grid uses unresampled MOLA topography and co-registered shot counts. MOLA elevations are meters above the GMM3 areoid. Of 1,344 cells, 784 have zero shots and carry the mission product’s interpolated elevation. Three selected rover records retain their sol numbers and rover motion counters. Data product identifiers, URLs, transforms and checksums appear in the resource manifest.

### How a route is scored

Using the MOLA product sphere of radius 3,396 km and the crop’s central latitude, horizontal center spacing is 439.27 m east–west and 463.06 m north–south. Local grade is the magnitude of the two spatial derivatives of elevation. The scenario excludes 94 cells with local grade above 0.18. It also rejects individual edges whose absolute rise/run exceeds 0.18. Diagonal moves cannot pass between blocked corners.

For a legal move with horizontal length *d* in km and elevation change *h* in km, effort is *d* × (1 + 6 × mean local grade) + 10 × max(*h*, 0). The terrain penalty at a cell is a weighted mix of local grade normalized to the 18% limit, a zero-shot indicator, and an exclusion margin that decays exponentially with distance from a blocked cell. The margin’s decay length is twice the east–west cell spacing. The route adds *d* times the mean penalty of the two endpoints. The final dimensionless score is total effort + 4 × integrated terrain penalty. The default penalty shares are 35%, 45% and 20%, respectively. These coefficients are team assumptions. Map distance is horizontal. Ascent accumulates only positive elevation changes.

### Classical and quantum methods

FastAPI and NumPy serve a fixed terrain version. The A* search uses an admissible anisotropic distance heuristic. Tests compare its answer with independent Dijkstra searches. A separate validator checks route endpoints, obstacles, legal adjacency, blocked corners, directional slope and rescored metrics. Editing the inputs clears old geometry and disables export until a current result arrives.

The optional Qiskit statevector experiment builds up to four waypoints with at most six directed arc variables. Each arc is priced by a full-grid A* leg. A binary variable selects each arc. The QUBO minimizes normalized leg costs with quadratic penalties for broken flow conservation. The decoder accepts a complete simple source-to-target path and rejects dangling branches or extraneous cycles. Exact Dijkstra on the same waypoint graph and exhaustive QUBO enumeration provide references. Solver errors, exact classical fallback, A* fallback and fixed replay carry distinct labels.

In the recorded default run, four arc qubits, depth one, 1,024 shots and eight COBYLA iterations produced a sampled route with score **21.8369**, matching the exact waypoint reference. Full-grid A* scored **20.1793**. Restricting the paths to these waypoints raised cost by **8.21%**. Feasible paths carried **4.85%** of the sampled probability. This run used a simulator. It establishes no speedup or hardware advantage.

### Delivery and impact

The public browser edition runs a new A* search for each plan using legal directed moves and cost components exported from the Python engine. The full local edition adds bounded quantum jobs. Only one simulator subprocess runs per server process, with cancellation and a 45-second cutoff. Source assets and the recorded run are bundled so the public map has no live dependency on NASA archive availability.

The map makes a specific science-planning tradeoff visible. A shorter walk can cross more interpolated cells, and an explorer can inspect that uncertainty before choosing a route. The prototype estimates regional terrain effort. Human endurance, oxygen, live weather, radiation dose, small obstacles and certified EVA margins require other measurements or models.

## NASA and other resources

Use the product links, credits and license notes in [RESOURCES.md](RESOURCES.md). The full machine-readable product manifest is also public at https://zoghby-ctrl.github.io/quantumions-martian-map/data/manifest.json.

## SI / AI disclosure for the form

Quantumions used OpenAI Codex to assist with project code. For this edition, Codex helped prepare the data-processing scripts, routing fixes, interface, verification and submission text. The Quantumions team logo was generated with ChatGPT Image and is labeled “AI-generated” wherever it appears in the app and presentation. The orbital image, laser elevations, shot counts and rover coordinates come from the credited mission products. Terrain costs and route geometries are calculated outputs of the disclosed model. The comparison is a recorded Qiskit statevector simulation. The presentation uses captures of the functioning planner. It contains no generated narration or video.

## Team review before submitting

- Review the summary, project details, source credits and disclosure against the team’s complete contribution record.
- Open the project and six-page demo links as a judge would. The public edition computes A* locally in the browser. The simulator run accessible there is recorded.
- Confirm the registered team, selected challenge, eligibility questions and legal attestations in the official form. The team owner completes the final submission.

