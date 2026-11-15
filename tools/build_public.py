"""Stage the GitHub Pages edition from explicit assets only. Supply an output directory."""

import argparse
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "static"


def build(dest):
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "data").mkdir(exist_ok=True)
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    (dest / "index.html").write_text(
        html.replace('<html lang="en">', '<html lang="en" data-runtime="browser">'),
        encoding="utf-8",
    )
    for name in [
        "styles.css",
        "app.js",
        "map.js",
        "browser-router.js",
        "quantumions.png",
        "data/terrain.json",
        "data/manifest.json",
        "data/recorded-route.json",
        "data/graph.json",
        "data/jezero-ctx.webp",
        "data/jezero.json",
    ]:
        shutil.copyfile(STATIC / name, dest / name)
    (dest / ".nojekyll").touch()
    deck = ROOT / "submission" / "Marswalk.pdf"
    if deck.is_file():
        shutil.copyfile(deck, dest / deck.name)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("destination", type=Path)
    build(parser.parse_args().destination.resolve())
