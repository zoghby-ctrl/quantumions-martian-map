"""Build the small offline Jezero dataset from NASA PDS, USGS and JPL products.

Usage: python tools/prepare_jezero.py SOURCE_CACHE
Build dependencies: numpy, Pillow, rasterio. Runtime uses only the prepared files.
"""

import argparse
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

import numpy as np
from PIL import Image
import rasterio
from rasterio.enums import Resampling
from rasterio.windows import from_bounds

OUT = Path(__file__).resolve().parents[1] / "static" / "data"
PDS = "https://pds-geosciences.wustl.edu/mgs/urn-nasa-pds-mgs_mola_topography_derived/meg128/"
CTX = "https://planetarymaps.usgs.gov/mosaic/mars2020_trn/CTX/JEZ_ctx_B_soc_008_orthoMosaic_6m_Eqc_latTs0_lon0.tif"
WAYPOINTS = "https://mars.nasa.gov/mmgis-maps/M20/Layers/json/M20_waypoints.json"
ROWS, COLS, PPD = 28, 48, 128
WEST, NORTH = 77.265625, 18.5546875
EAST, SOUTH = WEST + COLS / PPD, NORTH - ROWS / PPD


def fetch(url, cache, filename, byte_range=None):
    path = cache / filename
    if not path.exists():
        headers = (
            {"Range": f"bytes={byte_range[0]}-{byte_range[1]}"} if byte_range else {}
        )
        with urlopen(Request(url, headers=headers), timeout=120) as resp:
            raw = resp.read()
            if byte_range and (
                resp.status != 206
                or resp.headers.get("Content-Range", "").split("/")[0]
                != f"bytes {byte_range[0]}-{byte_range[1]}"
            ):
                raise ValueError("Source did not deliver the requested byte range")
        path.write_bytes(raw)
    return path


def mola(cache, stem, dtype):
    # PDS3 labels describe 11520 samples per line, north-down, no raster header.
    row, col = int((44 - NORTH) * PPD), int(WEST * PPD)
    width = 11520
    row_bytes = width * np.dtype(dtype).itemsize
    start = row * row_bytes
    stop = start + ROWS * row_bytes - 1
    path = fetch(
        PDS + stem + ".img", cache, f"{stem}-{start}-{stop}.bin", (start, stop)
    )
    return np.fromfile(path, dtype=dtype).reshape(ROWS, width)[:, col : col + COLS]


def main(cache):
    OUT.mkdir(parents=True, exist_ok=True)
    cache.mkdir(parents=True, exist_ok=True)
    z = mola(cache, "megt44n000hb", ">i2")
    hits = mola(cache, "megc44n000hb", "u1")
    if z.min() < -8208 or z.max() > 21249:
        raise ValueError("Elevation outside the PDS label's valid range")
    ctx = fetch(CTX, cache, "ctx.tif")
    with rasterio.open(ctx) as src:
        # Source EQC has standard parallel 0 and sphere of radius 3396190 m.
        factor = math.pi / 180 * 3396190
        window = from_bounds(
            *(v * factor for v in (WEST, SOUTH, EAST, NORTH)), src.transform
        )
        pixels = src.read(
            1,
            window=window,
            out_shape=(784, 1344),
            resampling=Resampling.average,
            masked=True,
        )
        lo, hi = np.percentile(pixels.compressed(), [1, 99])
        gray = np.clip(
            (pixels.filled(lo).astype(float) - lo) * 255 / (hi - lo), 0, 255
        ).astype("uint8")
        picture = Image.fromarray(gray).convert("LA")
        picture.putalpha(
            Image.fromarray((~np.ma.getmaskarray(pixels)).astype("uint8") * 255)
        )
        picture.save(OUT / "jezero-ctx.webp", lossless=True, method=6)
    features = json.loads(fetch(WAYPOINTS, cache, "waypoints.json").read_bytes())[
        "features"
    ]
    stops = [
        {
            "sol": f["properties"]["sol"],
            "rmc": f["properties"]["RMC"],
            "lonlat": f["geometry"]["coordinates"][:2],
        }
        for f in features
        if f["properties"]["sol"] in (13, 700, 1100) and f["properties"]["final"] == "y"
    ]
    assert len(stops) == 3
    dataset = {
        "bbox": [WEST, SOUTH, EAST, NORTH],
        "rows": ROWS,
        "cols": COLS,
        "elevation_m": z.tolist(),
        "shot_count": hits.tolist(),
        "stops": stops,
    }
    body = json.dumps(dataset, separators=(",", ":")).encode()
    (OUT / "jezero.json").write_bytes(body)

    def checksum(p):
        return hashlib.sha256(p.read_bytes()).hexdigest()

    manifest = {
        "dataset_id": "jezero-mola-ctx-v1-" + hashlib.sha256(body).hexdigest()[:10],
        "retrieved_utc": datetime.now(timezone.utc).date().isoformat(),
        "bbox_edges_wsen": dataset["bbox"],
        "grid_shape": [ROWS, COLS],
        "coordinates": "Planetocentric latitude, east-positive longitude in degrees on Mars. Geographic bounds are outer pixel edges. Each route vertex is a MOLA cell center.",
        "geometry": "Local equirectangular distances on a 3396000 m sphere (MOLA label radius), standard parallel at the crop midpoint. Regional approximation.",
        "sources": [
            {
                "name": "MGS / MOLA topography",
                "url": PDS + "megt44n000hb.img",
                "label": PDS + "megt44n000hb.lbl",
                "credit": "NASA GSFC / MGS MOLA Science Team, PDS Geosciences Node",
                "processing": "MEGT44N000HB v2.0. Native 1/128 degree median elevation, integer meters above the GMM3 areoid. Exact grid crop, no resampling. PDS fills unsounded bins by interpolation.",
            },
            {
                "name": "MGS / MOLA shot counts",
                "url": PDS + "megc44n000hb.img",
                "label": PDS + "megc44n000hb.lbl",
                "credit": "NASA GSFC / MGS MOLA Science Team, PDS Geosciences Node",
                "processing": "MEGC44N000HB v2.0. Co-registered native crop. Zero observations indicates a product-interpolated elevation. Counts are neither confidence intervals nor hazard measurements.",
            },
            {
                "name": "MRO / CTX orbital mosaic",
                "url": CTX,
                "label": "https://doi.org/10.5066/P9GV1ND3",
                "credit": "NASA / JPL-Caltech / MSSS / USGS Astrogeology",
                "processing": "Mars 2020 TRN CTX 6 m orthoimage. Cropped in source EQC meters, area-averaged to 1344 by 784, valid pixels stretched at 1st and 99th percentiles. Zero source DN is nodata, masked output is transparent.",
            },
            {
                "name": "Mars 2020 / Perseverance waypoints",
                "url": WAYPOINTS,
                "label": "https://science.nasa.gov/mission/mars-2020-perseverance/location-map/",
                "credit": "NASA / JPL-Caltech, Mars 2020 mission mapping team",
                "processing": "Three end-of-drive point records selected by sol and RMC. Coordinates retained as published. Suggested walk connects snapped grid centers independently of rover history.",
            },
        ],
        "science_context": [
            {
                "sol": 13,
                "title": "Octavia E. Butler landing",
                "note": "The starting location anchors the plan to the crater floor where Perseverance began its investigation of Jezero.",
                "url": "https://doi.org/10.1126/sciadv.abo4856",
            },
            {
                "sol": 700,
                "title": "After the depot campaign",
                "note": "Ten sols before this waypoint, Perseverance completed the Three Forks depot near the base of the ancient delta. The marker identifies the later rover position.",
                "url": "https://science.nasa.gov/photojournal/perseverances-three-forks-sample-depot-map/",
            },
            {
                "sol": 1100,
                "title": "Margin Unit campaign",
                "note": "Twelve sols before this waypoint, Perseverance sealed a silica-cemented carbonate core at Bunsen Peak. The marker gives the rover position on sol 1100.",
                "url": "https://science.nasa.gov/mission/mars-2020-perseverance/mars-rock-samples/",
            },
        ],
        "sha256": {
            p.name: checksum(p) for p in [OUT / "jezero.json", OUT / "jezero-ctx.webp"]
        },
        "upstream_ctx_sha256": checksum(ctx),
    }
    (OUT / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    print(
        manifest["dataset_id"],
        stops,
        "Elevation",
        z.min(),
        z.max(),
        "zero count",
        (hits == 0).sum(),
        "CTX valid",
        pixels.count() / pixels.size,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("cache", type=Path)
    main(parser.parse_args().cache)
