# Sources and attribution

## Mission products used by the planner

Retrieved November 15, 2026. The machine-readable manifest records the crop, transformation and hashes. Products are distributed with source attribution. The science links below provide context for the annotated locations.

| Product | Use and credit | Exact public source |
|---|---|---|
| MEGT44N000HB.IMG v2.0 | NASA GSFC / MGS MOLA Science Team, PDS Geosciences Node. Native 1/128° simple-cylindrical grid, signed big-endian 16-bit meters of topography. Use the PDS interpolated value where there are no observations. | https://pds-geosciences.wustl.edu/mgs/urn-nasa-pds-mgs_mola_topography_derived/meg128/megt44n000hb.img |
| MEGC44N000HB.IMG v2.0 | Same mission, instrument, producer and pixel geometry. Unsigned 8-bit observation count. Zero is meaningful data. | https://pds-geosciences.wustl.edu/mgs/urn-nasa-pds-mgs_mola_topography_derived/meg128/megc44n000hb.img |
| JEZ_ctx_B_soc_008_orthoMosaic_6m_Eqc_latTs0_lon0.tif | NASA MRO / CTX, NASA/JPL-Caltech/MSSS and USGS Astrogeology. Fergason, Galuszka, Hare, Mayer and Redding. USGS marks this product CC0 1.0. The CTX image is cropped, averaged, contrast-stretched and given a warm display tint. No color or terrain interpretation relies on that tint. | https://planetarymaps.usgs.gov/mosaic/mars2020_trn/CTX/JEZ_ctx_B_soc_008_orthoMosaic_6m_Eqc_latTs0_lon0.tif |
| M20_waypoints.json | NASA/JPL-Caltech Mars 2020 team. Selected the final rover position on sols 13, 700 and 1100, RMC 3_0, 33_366 and 51_644. The source is updated by the mission. The app bundles the three positions used. | https://mars.nasa.gov/mmgis-maps/M20/Layers/json/M20_waypoints.json |

Product labels and release records:

- MOLA topography label · https://pds-geosciences.wustl.edu/mgs/urn-nasa-pds-mgs_mola_topography_derived/meg128/megt44n000hb.lbl
- MOLA shot count label · https://pds-geosciences.wustl.edu/mgs/urn-nasa-pds-mgs_mola_topography_derived/meg128/megc44n000hb.lbl
- PDS MEGDR archive and interpolation context · https://pds-geosciences.wustl.edu/missions/mgs/megdr.html
- USGS orthoimage release and rights statement · https://www.usgs.gov/data/mars-2020-terrain-relative-navigation-context-camera-orthorectified-image-mosaic
- USGS orthoimage DOI · https://doi.org/10.5066/P9GV1ND3
- NASA rover location map · https://science.nasa.gov/mission/mars-2020-perseverance/location-map/
- NASA media usage guidance · https://www.nasa.gov/nasa-brand-center/images-and-media/
- JPL image use guidance · https://www.jpl.nasa.gov/jpl-image-use-policy/

**Science annotations.** The landing note draws on the Mastcam-Z team’s field report. The sol 700 and sol 1100 notes place each waypoint in the mission timeline. Coordinates represent the stated rover sol. They do not locate a sample tube or the rock core itself.

- Bell et al., geological imaging by Perseverance at Jezero · https://doi.org/10.1126/sciadv.abo4856
- NASA/JPL-Caltech, Three Forks sample depot map · https://science.nasa.gov/photojournal/perseverances-three-forks-sample-depot-map/
- NASA Mars 2020 sample catalogue, Comet Geyser / Bunsen Peak, sol 1088 · https://science.nasa.gov/mission/mars-2020-perseverance/mars-rock-samples/

## Other resources

| Resource | Author or steward / license | Use |
|---|---|---|
| Python 3.12.10 · https://www.python.org/ | Python Software Foundation, PSF license | Routing service, preparation, verification |
| FastAPI 0.115.6 · https://fastapi.tiangolo.com/ | Sebastián Ramírez and contributors, MIT | HTTP API and same-origin static assets |
| Pydantic 2.10.4 · https://docs.pydantic.dev/ | Pydantic contributors, MIT | Input validation |
| Uvicorn 0.34.0 · https://www.uvicorn.org/ | Encode and contributors, BSD-3-Clause | ASGI server |
| NumPy 2.4.4 · https://numpy.org/ | NumPy developers, BSD-3-Clause with bundled notices | Terrain fields, gradient and graph computations |
| Qiskit 2.5.1, Qiskit Algorithms 0.4.0, Qiskit Optimization 0.7.0 · https://github.com/Qiskit/qiskit · https://github.com/qiskit-community/qiskit-algorithms · https://github.com/qiskit-community/qiskit-optimization | IBM and Qiskit contributors, Apache-2.0 | Statevector sampling, QAOA and binary flow formulation |
| SciPy 1.18.0 · https://scipy.org/ | SciPy developers, BSD-3-Clause with bundled notices | Numerical optimization used by the Qiskit stack |
| Rasterio 1.5.2 · https://rasterio.readthedocs.io/ | Rasterio contributors, BSD-3-Clause | Read and resample CTX during preparation |
| Pillow 12.2.0 · https://python-pillow.org/ | Pillow authors, MIT-CMU | Encode the display raster |
| pytest 8.3.4 and HTTPX 0.28.1 · https://pytest.org/ · https://www.python-httpx.org/ | pytest contributors, MIT. Encode / HTTPX contributors, BSD-3-Clause | Regression and HTTP checks |
| Playwright 1.65.2 · https://playwright.dev/python/ | Microsoft and contributors, Apache-2.0 | Real browser verification and screenshots |
| GitHub Pages · https://pages.github.com/ | GitHub, hosted service | Public map and demonstration hosting |
| OpenAI Codex and ChatGPT Image · https://openai.com/ | OpenAI tools, used by Quantumions | Code assistance, written content and team artwork. See the disclosure below. |

The UI uses the viewer’s system sans-serif, serif and monospace fonts. The deck uses Georgia and Segoe UI installed on the authoring system. The application distributes no font files. Quantumions supplied the team logo for this project. The PNG included in the app preserves the supplied image. Screenshots show actual application output and the source of the orbital imagery is credited above. Microsoft PowerPoint and the Codex presentation runtime were used for the editable deck and its submission export.

## AI and generated-output metadata

The primary astronomical data are mission archive values. The code crops and displays those values, derives grades, and computes modeled exclusions and routes. The team confirmed Codex assistance and ChatGPT Image use. The application labels the AI-generated logo at its point of display. Route exports identify the model, sources and AI assistance. The presentation includes the same disclosure. No audio or video is part of this submission.

Machine-readable disclosure · [disclosure.json](disclosure.json).

