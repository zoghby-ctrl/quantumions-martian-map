# Review and verification record

## Deadline and baseline

At 18:38 Cairo on November 15, 2026, the official 2026 event listing gave November 15 at 23:59 local time. Using the team creator’s Cairo timezone supplied in the project brief left 5 hours 21 minutes. Searches of connected mail found no extension. The private event dashboard was not independently inspected. The team owner retains responsibility for submission. [Official event listing](https://www.spaceappschallenge.org/2026/)

The workspace initially had no commits or project files. The public repository’s only branch, master, pointed at `4e17f70` with team preparation notes. The supplied ZIP contained the working synthetic implementation and a different README. The ZIP remains the recovery copy, SHA-256 `69cba24093eceeaa6f4d567add34ec0c3eadAf446956e0f225868db7ecda1ae7` (case-insensitive). The archive application was imported at `1cfdc24` on the review branch. Both README histories are preserved. The public site is built from explicit files on a separate Pages branch.

Before edits, seven tests passed. The original HTTP default returned an A* score of 38.745754 and a labeled A* fallback. The base interpreter lacked qiskit-algorithms and qiskit-optimization. The original UI was opened at 1440 px and 390 px. That result concerns the original synthetic scenario only.

## Checks performed on the delivered implementation

| Check | Result |
|---|---|
| Clean CPython environment | Installed requirements, optional quantum packages and test requirements into a fresh Python 3.12.10 environment without inherited system packages. `pip check` found no broken requirements. |
| Automated regression suite | **20 passed**. The clean environment emitted one Starlette TestClient / AnyIO deprecation warning. |
| Geometry and validation | Native MOLA cell centers round-trip at corners and in the interior. Tests independently reject jumps, zero moves, corner cuts, blocked cells, mismatched versions, invalid inputs and disconnected Jezero endpoints. |
| Fixed geography | API terrain was identical before and after different inputs and priorities. Public terrain and graph files matched the current Python generator. Elevation and imagery checksums matched the manifest. |
| Search correctness | A* matched independent Dijkstra for four preference settings on the Jezero grid. A tiny exhaustively enumerated QUBO matched exact waypoint Dijkstra. Extra arcs, duplicate arcs, dead ends and cycles were rejected. Invalid solver geometry produced a labeled fallback. |
| Real quantum execution | Verified directly in the isolated Python environment and through a live HTTP job. The default statevector sample matched the waypoint optimum. The clean run took 13.13 s including first imports. A separate bundled recording took 5.92 s total. These are individual observations. |
| Expensive work | A second concurrent job received 429. Classical routing remained available. DELETE canceled the worker. A subsequent job completed, and repeating its exact inputs reused the result. The watchdog test shortened its configured deadline to 0.05 s and verified that the real process exited. The production deadline is 45 s. |
| Browser interaction | Chromium at 1440 × 960, 768 × 844 and 390 × 844. Checked keyboard solve, swap, focus, map pan/zoom, opacity, mobile map placement, layer switching, inputs and downloaded GeoJSON. No horizontal page overflow at the measured sizes. |
| Failure and race handling | A response held across a weight edit could not restore its old route. A delayed health response preserved a newly selected site. A failed route request and a disconnected real traverse left export disabled. Replay required an explicit action and locked its inputs. |
| Public classical parity | In a fresh signed-out Chromium context, validated **27 additional reachable endpoint/weight combinations** against Python’s full-grid optimum and rescored the returned geometry. New destination selection and export also worked through the actual public controls. |
| Public presentation | Public project and PDF returned HTTP 200 without sign-in. Downloaded PDF bytes exactly matched the reviewed file. PowerPoint opened the deck, exported six pages, and each page was rendered and visually checked. The final slide’s link targets the planner. |
| Submission text | Summary is **125 words and 869 characters**. Source and disclosure files accompany the deck. |

### Bundled run on the fixed dataset

Dataset `jezero-mola-ctx-v1-a1e95a4313`. Source waypoints sol 13 and sol 1100. Full-grid status `optimal_on_grid`. QAOA status `optimal_on_waypoint_graph`, backend `statevector`, four qubits, depth one, 1,024 shots and eight COBYLA iterations. Exact waypoint score 21.8369, sampled route score 21.836855, grid optimum 20.179296. Feasible sample probability 0.0485. Grid gap +8.2142%. In the recorded run, graph preparation took 15.301 ms, optimization and sampling 612.984 ms, and postprocessing 0.460 ms. Total including imports and setup was 5,923.868 ms.

## Principal changes

- `tools/prepare_jezero.py`, `jezero.py`, `static/data/` implement the archive extracts, versioned terrain, metric geometry, independent validation and provenance.
- `mars_router.py` retains the teammate’s A*, waypoint graph, Dijkstra, QUBO and simulator. It now supports rectangular metric grids and validates complete moves and samples.
- `main.py` and `quantum_jobs.py` separate fast A* from bounded optional comparisons. Results carry source data, inputs, assumptions and diagnostics.
- `static/index.html`, `styles.css`, `app.js`, `map.js` and `browser-router.js` implement the map, endpoint selection, live briefing, explicit replay and export. The team-provided logo carries a visible AI-generated label.
- `tools/prepare_demo.py` and `tools/build_public.py` generate the browser graph, recorded result and allowlisted public deployment.
- `requirements*.txt`, `tests/` and `README.md` document and verify the supported workflows. `submission/` contains the form copy, resources, disclosure and presentation.

## Remaining scope

The public app runs live classical planning. New QAOA runs require the Python edition with optional dependencies. Human physiology, radiation exposure, weather, sub-cell hazards and field validation remain outside the prototype. Public access was checked at handoff. The submitted form, eligibility confirmations and final source/credit approval remain with the team.

