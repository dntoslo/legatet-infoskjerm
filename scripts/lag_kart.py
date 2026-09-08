#!/usr/bin/env python3
"""Lager assets/sor-norge.json: et forenklet omriss av Sør-Norge til kartvisningen.

Engangsscript, ikke del av GitHub Action. Kjøres med:

  uv run --with shapely scripts/lag_kart.py

Kilde: Natural Earth 1:10m «Admin 0 – Countries» (public domain), hentet som
GeoJSON fra github.com/nvkelso/natural-earth-vector. Norge klippes til en
boks rundt Sør-Norge, forenkles så det ser tegnet ut, og skrives som ringer
i lon/lat. Projeksjonen gjøres i assets/kart.js, slik at omriss og hytter
bruker samme funksjon.
"""

import json
import sys
import urllib.request
from datetime import date
from pathlib import Path

from shapely.geometry import MultiPolygon, Polygon, box, shape

ROT = Path(__file__).resolve().parent.parent
UTFIL = ROT / "assets" / "sor-norge.json"

KILDE = ("https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/"
         "geojson/ne_10m_admin_0_countries.geojson")

# Boks rundt Sør-Norge: fra Lindesnes til litt nord for Dovrefjell, og østover
# forbi Femunden. Kartet klippes rett av i nord.
BBOX = (4.6, 57.9, 12.9, 63.6)          # lon_min, lat_min, lon_max, lat_max
TOLERANSE = 0.03                        # grader, høyere gir grovere og roligere strek
MIN_AREAL = 0.01                        # kvadratgrader, småøyer under dette droppes
DESIMALER = 3


def hent_norge():
    print(f"Henter {KILDE} ...", file=sys.stderr)
    with urllib.request.urlopen(KILDE, timeout=120) as resp:
        data = json.load(resp)
    for f in data["features"]:
        p = f["properties"]
        if p.get("ADMIN") == "Norway" or p.get("ISO_A3") == "NOR" or p.get("NAME") == "Norway":
            return shape(f["geometry"])
    raise SystemExit("Fant ikke Norge i datasettet")


def ringer_av(geom):
    polygoner = list(geom.geoms) if isinstance(geom, MultiPolygon) else [geom]
    ut = []
    for poly in polygoner:
        if not isinstance(poly, Polygon) or poly.is_empty or poly.area < MIN_AREAL:
            continue
        ring = [[round(x, DESIMALER), round(y, DESIMALER)] for x, y in poly.exterior.coords]
        if len(ring) >= 4:
            ut.append(ring)
    return ut


def main():
    norge = hent_norge()
    klippet = norge.intersection(box(*BBOX))
    forenklet = klippet.simplify(TOLERANSE, preserve_topology=True)
    ringer = ringer_av(forenklet)
    punkter = sum(len(r) for r in ringer)

    ut = {
        "kilde": KILDE,
        "lisens": "Natural Earth, public domain",
        "laget": date.today().isoformat(),
        "toleranse": TOLERANSE,
        "bbox": list(BBOX),
        "ringer": ringer,
    }
    UTFIL.write_text(json.dumps(ut, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"Skrev {UTFIL.relative_to(ROT)}: {len(ringer)} ringer, {punkter} punkter, "
          f"{UTFIL.stat().st_size // 1024} kB", file=sys.stderr)


if __name__ == "__main__":
    main()
