# Marswalk · A Martian Survival Map by Quantumions

[Open the public Jezero planner](https://zoghby-ctrl.github.io/quantumions-martian-map/) · [Six-slide demonstration](https://zoghby-ctrl.github.io/quantumions-martian-map/Marswalk.pdf) · [Submission copy](submission/PROJECT.md)

Explore the western delta of Jezero crater with MRO/CTX imagery, native MGS/MOLA elevation and shot counts, and three Perseverance sites. Choose two sites or place your own endpoints, tune terrain priorities, inspect the route briefing and download the result. The downloadable geometry uses east longitude and planetocentric north latitude on **Mars**. Earth GIS tools may display it on Earth by default.

## For our team

This project builds on work contributed by the Quantumions team. The current implementation and submission materials are on the **codex/jezero-traverse** branch.

- [View this branch on GitHub](https://github.com/zoghby-ctrl/quantumions-martian-map/tree/codex/jezero-traverse)
- [Edit this README on GitHub](https://github.com/zoghby-ctrl/quantumions-martian-map/edit/codex/jezero-traverse/README.md)
- [Review the project and submission text](submission/PROJECT.md)
- [Review the sources and AI disclosure](submission/RESOURCES.md)

To contribute through GitHub, sign in to your own account and open the README edit link. Make your changes, select **Commit changes**, and follow GitHub's prompts to commit to the branch or propose a pull request. A commit made with your GitHub account records your contribution in the project history. If GitHub offers to fork the repository, propose your changes from the fork or ask the repository owner to add you as a collaborator with write access. The repository owner can invite you under **Settings → Collaborators and teams**.

The live site is published from a separate branch, so edits to this README or the source branch do not automatically change the public planner.

## Run the full application

Use CPython 3.12. Create an environment with `python -m venv .venv`. Activate it with `.venv\Scripts\Activate.ps1` on Windows or `source .venv/bin/activate` on macOS/Linux. From the repository root run:

```sh
python -m pip install -r requirements.txt
python main.py
```

Open <http://127.0.0.1:8000/>. For the live statevector experiment, install `requirements-quantum.txt` in the same environment and restart the application. To run tests, install `requirements-test.txt` and use `python -m pytest -q`. The classical planner needs no Qiskit packages.

## Data and model

The [product manifest](static/data/manifest.json) identifies the exact source files, processing and checksums. The 48-column by 28-row grid is a native crop of the 128 pixels/degree MOLA product. Its outer bounds are 77.265625–77.640625° E and 18.3359375–18.5546875° N. Rows run north to south. At the midpoint, a step east spans 439.27 m and a step north spans 463.06 m on the product's 3,396 km Mars sphere. The CTX map has the same bounds. Its finer image detail does not increase the terrain grid resolution.

Eight-neighbor A* minimizes a positive weighted cost. Traverses avoid blocked corners and modeled grades above 18%. The fixed cost of distance, slope and uphill travel combines with a selectable penalty for grade, interpolated elevation and distance to exclusions. The API returns the integrated scores, physical map distance, positive elevation gain and maximum step grade. These scores are uncalibrated. See the [formulas and limitations](submission/PROJECT.md).

The local API serves `GET /api/health`, `GET /api/terrain`, `POST /api/route` and optional jobs at `POST /api/quantum`, `GET /api/quantum/{id}` and `DELETE /api/quantum/{id}`. See `/docs` for schemas. Inputs use latitude, longitude. The two preference keys are `slope` and `interpolation`. Returning classical A* first and removing the synthetic radiation input are changes from the archived API. Explicit replay loads a recorded result with fixed inputs.

Use one Uvicorn process for the in-memory job manager. One simulator subprocess can run at a time, with a 45-second wall-clock limit, cancellation, and bounded result retention. Repeated successful comparisons for identical inputs reuse the completed job. The experiment uses A* to price waypoint legs, samples a flow-constrained QUBO, checks complete bitstrings, and scores the resulting route on the full grid. The exact waypoint and full-grid references are both reported.

## Build and deployment

The shipped dataset runs without contacting NASA services. Rebuilding the source crop requires `rasterio==1.5.2` and `Pillow==12.2.0` alongside NumPy. Run `python tools/prepare_jezero.py PATH_TO_SOURCE_CACHE`, then `python -m tools.prepare_demo` with the optional Qiskit environment. The second command creates the public graph, terrain and a fresh measured recording. Existing installations can serve the committed assets directly.

For a Python service, deploy `main.py`, `jezero.py`, `mars_router.py`, `quantum_jobs.py`, the applicable requirements and `static/`. Set `HOST=0.0.0.0` and the host-provided `PORT`. CORS is same-origin by default. Set `MARSWALK_CORS_ORIGINS` to a comma-separated list only for a separate frontend.

For static hosting, run `python tools/build_public.py DESTINATION` and serve that directory over HTTP. Its browser A* uses directed step costs compiled by the Python terrain engine. It supports live planning and an explicitly recorded Qiskit comparison. The public site uses the separate `codex/jezero-public` Pages branch.

## Teammate baseline

The working archive was imported alongside the original repository's preparation notes. The original engine and UI are recoverable at commit `1cfdc24`. The archived setup guide is retained in `ARCHIVE-README.md`. Its synthetic previews and 60-second AVI are historical artifacts. The standalone synthetic engine remains available via `python mars_router.py --classical-only --pretty`.

## Original team preparation notes

NASA Space Apps Challenge 2026 — Universal Event

Challenge: [Interplanetary Survival Guide: Martian Map](https://www.spaceappschallenge.org/2026/challenges/interplanetary-survival-guide-martian-map/)

## Before the hackathon

Use this repository to coordinate and prepare. Begin developing the competition solution when the event starts on November 14, 2026, at 9:00 a.m. team creator's local time. Verify the rules and deadline with the event organizers.

## Team workflow

- Both teammates clone this repository and open it in VS Code.
- Use the Microsoft Live Share extension when editing together; share the session link privately.
- Commit and push agreed changes so both teammates can access them later.
- Never commit passwords, API keys, or other private information.

## Project direction

Explore a layered map for planning a Marswalk using NASA mission data, with classical route planning and an exploratory Qiskit optimization comparison. Confirm the dataset choices and scope against the challenge statement.
