#!/usr/bin/env python3
"""Lager assets/sor-norge.json: kartgrunnlaget til kartet i betjente.html og selvbetjente.html.

Engangsscript, ikke del av GitHub Action. Kjøres med:

  uv run --with shapely scripts/lag_kart.py

Innhold og kilder:
- Omriss av Sør-Norge: Natural Earth 1:10m «Admin 0 – Countries» (public
  domain), hentet som GeoJSON fra github.com/nvkelso/natural-earth-vector.
- Fjellområdene: DNT-områdene på ut.no (samme GraphQL-endepunkt som
  hent_data.py). Hvilke ut.no-områder som tegnes for hvert kort, står i
  «polygon» under hvert område i «omrader» i hytter.json. Områder med tom
  liste (Oslomarka og Oslofjorden) tegnes ikke.
- Innsjøer, elver og byer: Natural Earth 1:10m lakes, rivers_lake_centerlines
  og populated_places, filtrert på navnene under.

Alt klippes til en boks rundt Sør-Norge, forenkles så det ser tegnet ut, og
skrives som ringer og linjer i lon/lat. Projeksjonen gjøres i assets/app.js,
slik at alle lagene og hyttene bruker samme funksjon.
"""

import json
import sys
import unicodedata
import urllib.request
from datetime import date
from pathlib import Path

from shapely.geometry import LineString, MultiLineString, MultiPolygon, Polygon, box, shape

ROT = Path(__file__).resolve().parent.parent
KONFIG = ROT / "hytter.json"
UTFIL = ROT / "assets" / "sor-norge.json"

NE = "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/"
UTNO = "https://ut.no/api/graphql"
USER_AGENT = "dntoslo-legatet-infoskjerm/1.0 (+https://github.com/dntoslo/legatet-infoskjerm)"

# Boks rundt Sør-Norge: fra Lindesnes til litt nord for Dovrefjell, og østover
# forbi Femunden. Kartet klippes rett av i nord.
BBOX = (4.6, 57.9, 12.9, 63.6)          # lon_min, lat_min, lon_max, lat_max
TOLERANSE_LAND = 0.03                   # grader, høyere gir grovere og roligere strek
TOLERANSE_DETALJ = 0.012                # områder, innsjøer og elver
MIN_AREAL = 0.01                        # kvadratgrader, småøyer under dette droppes
DESIMALER = 3

INNSJOER = ["Mjøsa", "Femunden", "Tyrifjorden", "Øyeren"]
ELVER = ["Glomma"]
BYER = ["Oslo", "Bergen", "Stavanger", "Kristiansand", "Lillehammer"]

KLIPP = box(*BBOX)


def hent_json(url, data=None):
    req = urllib.request.Request(url, data=data, headers={
        "User-Agent": USER_AGENT, "Accept": "application/json",
        **({"Content-Type": "application/json"} if data else {}),
    })
    with urllib.request.urlopen(req, timeout=180) as resp:
        return json.load(resp)


def hent_ne(navn):
    print(f"Henter Natural Earth {navn} ...", file=sys.stderr)
    return hent_json(f"{NE}{navn}.geojson")["features"]


def gql(query, variables):
    body = json.dumps({"query": query, "variables": variables}).encode("utf-8")
    svar = hent_json(UTNO, body)
    if svar.get("errors"):
        raise SystemExit(f"GraphQL-feil: {svar['errors']}")
    return svar["data"]


def normaliser_navn(s):
    return unicodedata.normalize("NFC", s or "").casefold()


def rund(x, y):
    return [round(x, DESIMALER), round(y, DESIMALER)]


def ringer_av(geom, min_areal=0.0):
    """Ytterringene i et (Multi)Polygon som lister av [lon, lat]. Hull droppes."""
    polygoner = list(geom.geoms) if isinstance(geom, MultiPolygon) else [geom]
    ut = []
    for poly in polygoner:
        if not isinstance(poly, Polygon) or poly.is_empty or poly.area < min_areal:
            continue
        ring = [rund(x, y) for x, y in poly.exterior.coords]
        if len(ring) >= 4:
            ut.append(ring)
    return ut


def linjer_av(geom):
    deler = list(geom.geoms) if isinstance(geom, MultiLineString) else [geom]
    ut = []
    for linje in deler:
        if isinstance(linje, LineString) and not linje.is_empty:
            ut.append([rund(x, y) for x, y in linje.coords])
    return ut


def klipp_og_forenkle(geom, toleranse):
    return geom.intersection(KLIPP).simplify(toleranse, preserve_topology=True)


def land():
    """Det forenklede omrisset av Sør-Norge som geometri. Områdene klippes
    mot dette, så ingen av dem stikker utenfor den tegnede grensa."""
    for f in hent_ne("ne_10m_admin_0_countries"):
        p = f["properties"]
        if p.get("ADMIN") == "Norway" or p.get("ISO_A3") == "NOR":
            geom = klipp_og_forenkle(shape(f["geometry"]), TOLERANSE_LAND)
            polygoner = list(geom.geoms) if isinstance(geom, MultiPolygon) else [geom]
            return MultiPolygon([p for p in polygoner if isinstance(p, Polygon) and p.area >= MIN_AREAL])
    raise SystemExit("Fant ikke Norge i datasettet")


def omrader(konfig, landflate):
    """{kortnavn: [ringer]} fra DNT-områdene på ut.no, klippet mot landflaten.
    Områder uten «polygon» hoppes over og får ingen nøkkel."""
    ut = {}
    for kort, regler in konfig.get("omrader", {}).items():
        ider = regler.get("polygon") or []
        if not ider:
            continue
        ringer = []
        for omrade_id in ider:
            print(f"Henter ut.no-område {omrade_id} ({kort}) ...", file=sys.stderr)
            a = gql("query($id: Int!) { area(id: $id) { name areaType geojson } }", {"id": omrade_id})["area"]
            if not a or not a.get("geojson"):
                print(f"ADVARSEL: ut.no-område {omrade_id} har ingen geometri", file=sys.stderr)
                continue
            if a.get("areaType") != "DNT_AREA":
                print(f"ADVARSEL: {a.get('name')} er {a.get('areaType')}, ikke DNT_AREA", file=sys.stderr)
            geom = klipp_og_forenkle(shape(a["geojson"]).buffer(0), TOLERANSE_DETALJ)
            ringer.extend(ringer_av(geom.intersection(landflate)))
        ut[kort] = ringer
    return ut


def navnefilter(features, navn_felt, oensket):
    oensket_norm = {normaliser_navn(n): n for n in oensket}
    treff = {}
    for f in features:
        n = normaliser_navn(f["properties"].get(navn_felt))
        if n in oensket_norm:
            treff.setdefault(oensket_norm[n], []).append(f)
    for n in oensket:
        if n not in treff:
            print(f"ADVARSEL: fant ikke «{n}» i Natural Earth", file=sys.stderr)
    return treff


def innsjoer():
    ut = []
    for navn, fs in navnefilter(hent_ne("ne_10m_lakes"), "name", INNSJOER).items():
        for f in fs:
            ut.extend(ringer_av(klipp_og_forenkle(shape(f["geometry"]), TOLERANSE_DETALJ)))
    return ut


def elver():
    ut = []
    for navn, fs in navnefilter(hent_ne("ne_10m_rivers_lake_centerlines"), "name", ELVER).items():
        for f in fs:
            ut.extend(linjer_av(klipp_og_forenkle(shape(f["geometry"]), TOLERANSE_DETALJ)))
    return ut


def byer():
    ut = []
    for navn, fs in navnefilter(hent_ne("ne_10m_populated_places"), "NAME", BYER).items():
        lon, lat = fs[0]["geometry"]["coordinates"][:2]
        ut.append({"navn": navn, "lon": round(lon, DESIMALER), "lat": round(lat, DESIMALER)})
    return ut


def main():
    konfig = json.loads(KONFIG.read_text(encoding="utf-8"))
    landflate = land()
    ut = {
        "kilder": {
            "land, innsjoer, elver, byer": "Natural Earth 1:10m, public domain, " + NE,
            "omrader": "DNT-områder fra ut.no, " + UTNO,
        },
        "laget": date.today().isoformat(),
        "bbox": list(BBOX),
        "ringer": ringer_av(landflate),
        "omrader": omrader(konfig, landflate),
        "innsjoer": innsjoer(),
        "elver": elver(),
        "byer": byer(),
    }
    UTFIL.write_text(json.dumps(ut, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"Skrev {UTFIL.relative_to(ROT)}: {len(ut['ringer'])} landringer, "
          f"{sum(len(r) for r in ut['omrader'].values())} områderinger, "
          f"{len(ut['innsjoer'])} innsjøer, {len(ut['elver'])} elvestrekk, {len(ut['byer'])} byer, "
          f"{UTFIL.stat().st_size // 1024} kB", file=sys.stderr)


if __name__ == "__main__":
    main()
