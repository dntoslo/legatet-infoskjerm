#!/usr/bin/env python3
"""Lager kartgrunnlagene til infoskjermen: assets/sor-norge.json til side 1 og 2
(betjente.html, selvbetjente.html) og assets/oslomarka.json til side 3
(oslomarka.html).

Engangsscript, ikke del av GitHub Action. Kjøres med kartnavnet som argument:

  uv run --with shapely scripts/lag_kart.py sor-norge
  uv run --with shapely --with pyproj scripts/lag_kart.py oslomarka

Begge filene har samme form: bbox, landringer, DNT-områder per kort, innsjøer,
elver og byer, alt i lon/lat. Projeksjonen gjøres i assets/app.js, slik at alle
lagene og hyttene bruker samme funksjon.

Sør-Norge (KART["sor-norge"]):
- Omriss: Natural Earth 1:10m «Admin 0 – Countries» (public domain), hentet
  som GeoJSON fra github.com/nvkelso/natural-earth-vector.
- Innsjøer, elver og byer: Natural Earth 1:10m lakes, rivers_lake_centerlines
  og populated_places, filtrert på navnene i definisjonen.
- Fjellområdene: DNT-områdene på ut.no (samme GraphQL-endepunkt som
  hent_data.py). Hvilke ut.no-områder som tegnes for hvert kort, står i
  «polygon» under hvert område i «omrader» i hytter.json. Områder med tom
  liste (Oslomarka og Oslofjorden) tegnes ikke.

Oslomarka (KART["oslomarka"]):
- Land, innsjøer og elveflater: Kartverkets N250 Kartdata (CC BY 4.0), GML
  per fylke fra Geonorge, objekttypene Havflate, Innsjø, InnsjøRegulert og
  Elv i Arealdekke. Land lages som utsnittet minus sjøflaten, det gir øyene i
  Oslofjorden. Natural Earth er for grov så tett inn, og Kartverkets
  kommunegrenser går ut i sjøen og har ingen kystlinje. Zip-filene (ca. 70 MB
  til sammen) caches i <temp>/legatet-kart, så en ny kjøring ikke laster ned
  igjen.
- Byer: Kartverkets stedsnavn-API, filtrert på By/Tettsted innenfor utsnittet.
- Delområdene: «polygon» under «delomrader» i området i hytter.json. ut.no-
  polygonene deler ikke grense, så det ligger striper uten område mellom
  naboer (Hakadal mellom Nordmarka og Romeriksåsene). Naboer som ligger
  nærmere hverandre enn 2 × «tett_m» vokser inn i glipa til de møtes på
  midten, så kartet blir et lappeteppe med den tynne hvite streken fra
  style.css som skille. Ytterkanter uten nabo røres ikke.
- «hav»: true i fila, så app.js fyller alt som ikke er land med vannfarge og
  fjorden blir blå. På Sør-Norge-kartet er sjøen bakgrunnsfargen.

Alt klippes til utsnittet, forenkles så det ser tegnet ut, og skrives som
ringer og linjer i lon/lat.
"""

import io
import json
import shutil
import sys
import tempfile
import unicodedata
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from datetime import date
from pathlib import Path

from shapely.geometry import LineString, MultiLineString, MultiPolygon, Polygon, box, shape
from shapely.ops import transform, unary_union

ROT = Path(__file__).resolve().parent.parent
KONFIG = ROT / "hytter.json"
ASSETS = ROT / "assets"

NE = "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/"
GEONORGE_N250 = "https://nedlasting.geonorge.no/geonorge/Basisdata/N250Kartdata/GML/"
STEDSNAVN = "https://api.kartverket.no/stedsnavn/v1/navn"
UTNO = "https://ut.no/api/graphql"
USER_AGENT = "dntoslo-legatet-infoskjerm/1.0 (+https://github.com/dntoslo/legatet-infoskjerm)"
CACHE = Path(tempfile.gettempdir()) / "legatet-kart"

GML = "{http://www.opengis.net/gml/3.2}"
N250_TYPER = ("Havflate", "Innsjø", "InnsjøRegulert", "Elv")

# Én definisjon per kart. bbox er lon_min, lat_min, lon_max, lat_max.
# Toleransene er i grader for Natural Earth og ut.no-polygonene (som kommer i
# lon/lat), og i meter for N250 (som behandles i UTM 33 før det projiseres).
# Høyere toleranse gir grovere og roligere strek.
KART = {
    "sor-norge": {
        "utfil": "sor-norge.json",
        "kilde": "natural-earth",
        # Fra Lindesnes til litt nord for Dovrefjell, og østover forbi Femunden.
        "bbox": (4.6, 57.9, 12.9, 63.6),
        "toleranse_land": 0.03,
        "toleranse_detalj": 0.012,
        "min_areal": 0.01,                  # kvadratgrader, småøyer under dette droppes
        "desimaler": 3,
        "innsjoer": ["Mjøsa", "Femunden", "Tyrifjorden", "Øyeren"],
        "elver": ["Glomma"],
        "byer": ["Oslo", "Bergen", "Stavanger", "Kristiansand", "Lillehammer"],
        "omrade": None,                     # tegn «polygon» fra toppnivået i «omrader»
    },
    "oslomarka": {
        "utfil": "oslomarka.json",
        "kilde": "n250",
        # Dekker alle hyttene i Oslomarka og langs indre Oslofjord (lon 10,32
        # til 11,24, lat 59,74 til 60,30) med marg, Drøbak i sør, Hønefoss i
        # vest og Jessheim i nordøst. Forholdet bredde/høyde er ca. 0,75, så
        # kartet fyller kartkolonnen (60 rem bred, ca. 83 rem høy) i høyden.
        "bbox": (10.15, 59.62, 11.32, 60.40),
        "toleranse_detalj": 0.001,          # grader, ut.no-polygonene
        "toleranse_land_m": 150,            # meter, N250-kysten
        "toleranse_vann_m": 100,            # meter, innsjøer og elveflater
        "min_land_km2": 0.03,               # holmer under dette droppes
        "min_innsjo_km2": 1.0,
        "min_elv_km2": 0.3,
        "desimaler": 4,
        # Fylkene som dekker utsnittet, som i filnavnene på Geonorge.
        "fylker": ["03_Oslo", "32_Akershus", "33_Buskerud", "31_Ostfold", "34_Innlandet", "39_Vestfold"],
        "byer": ["Oslo", "Drammen", "Sandvika", "Asker", "Lillestrøm", "Ski", "Hønefoss", "Jessheim", "Drøbak"],
        "omrade": "Oslomarka og Oslofjorden",   # tegn «polygon» fra «delomrader» under dette området
        "tett_m": 1500,                     # meter, lukk gliper mellom delområder nærmere enn det dobbelte
        "hav": True,                        # fyll alt som ikke er land med vannfarge, så fjorden blir blå
    },
}


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


def rund(x, y, desimaler):
    return [round(x, desimaler), round(y, desimaler)]


def polygoner_i(geom):
    return list(geom.geoms) if isinstance(geom, MultiPolygon) else [geom]


def ringer_av(geom, desimaler, min_areal=0.0):
    """Ytterringene i et (Multi)Polygon som lister av [lon, lat]. Hull droppes."""
    ut = []
    for poly in polygoner_i(geom):
        if not isinstance(poly, Polygon) or poly.is_empty or poly.area < min_areal:
            continue
        ring = [rund(x, y, desimaler) for x, y in poly.exterior.coords]
        if len(ring) >= 4:
            ut.append(ring)
    return ut


def linjer_av(geom, desimaler):
    deler = list(geom.geoms) if isinstance(geom, MultiLineString) else [geom]
    ut = []
    for linje in deler:
        if isinstance(linje, LineString) and not linje.is_empty:
            ut.append([rund(x, y, desimaler) for x, y in linje.coords])
    return ut


def klipp_og_forenkle(geom, klipp, toleranse):
    return geom.intersection(klipp).simplify(toleranse, preserve_topology=True)


# ---------- Natural Earth (Sør-Norge) ----------

def land_ne(kart, klipp):
    """Det forenklede omrisset av Sør-Norge som geometri. Områdene klippes
    mot dette, så ingen av dem stikker utenfor den tegnede grensa."""
    for f in hent_ne("ne_10m_admin_0_countries"):
        p = f["properties"]
        if p.get("ADMIN") == "Norway" or p.get("ISO_A3") == "NOR":
            geom = klipp_og_forenkle(shape(f["geometry"]), klipp, kart["toleranse_land"])
            return MultiPolygon([p for p in polygoner_i(geom) if isinstance(p, Polygon) and p.area >= kart["min_areal"]])
    raise SystemExit("Fant ikke Norge i datasettet")


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


def innsjoer_ne(kart, klipp):
    ut = []
    for navn, fs in navnefilter(hent_ne("ne_10m_lakes"), "name", kart["innsjoer"]).items():
        for f in fs:
            ut.extend(ringer_av(klipp_og_forenkle(shape(f["geometry"]), klipp, kart["toleranse_detalj"]), kart["desimaler"]))
    return ut


def elver_ne(kart, klipp):
    ut = []
    for navn, fs in navnefilter(hent_ne("ne_10m_rivers_lake_centerlines"), "name", kart["elver"]).items():
        for f in fs:
            ut.extend(linjer_av(klipp_og_forenkle(shape(f["geometry"]), klipp, kart["toleranse_detalj"]), kart["desimaler"]))
    return ut


def byer_ne(kart):
    ut = []
    for navn, fs in navnefilter(hent_ne("ne_10m_populated_places"), "NAME", kart["byer"]).items():
        lon, lat = fs[0]["geometry"]["coordinates"][:2]
        ut.append({"navn": navn, "lon": round(lon, kart["desimaler"]), "lat": round(lat, kart["desimaler"])})
    return ut


# ---------- Kartverket N250 (Oslomarka) ----------

def gml_polygoner(feature):
    """Polygonene i et N250-objekt (gml:Surface med PolygonPatch, eller
    gml:Polygon), med hull, i objektets eget koordinatsystem."""
    def ring(el):
        tall = list(map(float, el.find(f".//{GML}posList").text.split()))
        return list(zip(tall[0::2], tall[1::2]))

    ut = []
    for patch in list(feature.iter(f"{GML}PolygonPatch")) + list(feature.iter(f"{GML}Polygon")):
        ytre = patch.find(f"{GML}exterior")
        if ytre is None:
            continue
        indre = [ring(i) for i in patch.findall(f"{GML}interior")]
        ytre = ring(ytre)
        if len(ytre) >= 4:
            ut.append(Polygon(ytre, indre))
    return ut


def n250_arealdekke(fylke):
    """Polygonene av typene i N250_TYPER fra Arealdekke-GML for ett fylke, i
    EPSG:25833. Zip-fila caches. Fila leses strømmende, siden Innlandet er stor."""
    CACHE.mkdir(parents=True, exist_ok=True)
    fil = CACHE / f"Basisdata_{fylke}_25833_N250Kartdata_GML.zip"
    if not fil.exists():
        url = f"{GEONORGE_N250}{fil.name}"
        print(f"Laster ned {url} ...", file=sys.stderr)
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=600) as resp, open(fil, "wb") as f:
            shutil.copyfileobj(resp, f)
    print(f"Leser N250 Arealdekke for {fylke} ...", file=sys.stderr)
    z = zipfile.ZipFile(fil)
    navn = next(n for n in z.namelist() if "Arealdekke" in n and n.lower().endswith(".gml"))
    ut = {t: [] for t in N250_TYPER}
    dybde = 0
    with z.open(navn) as strom:
        for hendelse, el in ET.iterparse(io.BufferedReader(strom), events=("start", "end")):
            if hendelse == "start":
                dybde += 1
                continue
            dybde -= 1
            lokal = el.tag.rsplit("}", 1)[-1]
            if lokal in ut:
                ut[lokal].extend(gml_polygoner(el))
            # Objektene ligger på dybde 1 eller 2 (inni featureMember). Alt
            # der ryddes når det er ferdig, så minnet ikke vokser med fila.
            if dybde <= 2:
                el.clear()
    print("   " + ", ".join(f"{t} {len(v)}" for t, v in ut.items()), file=sys.stderr)
    return ut


def n250_land_og_vann(kart, klipp):
    """Landflate (lon/lat), innsjøringer og elveflater fra N250. Geometrien
    behandles i UTM 33 (meter) for å filtrere på areal og forenkle, og
    projiseres til lon/lat til slutt."""
    from pyproj import Transformer
    til_lonlat = Transformer.from_crs("EPSG:25833", "EPSG:4326", always_xy=True).transform
    til_utm = Transformer.from_crs("EPSG:4326", "EPSG:25833", always_xy=True).transform
    # Boksen i UTM med god marg: bredde- og lengdegradslinjene er svakt buede i
    # UTM, og alt klippes uansett til den eksakte boksen i lon/lat etterpå.
    boks_utm = transform(til_utm, box(*kart["bbox"])).buffer(2000)

    hav, innsjoer, elver = [], [], []
    for fylke in kart["fylker"]:
        d = n250_arealdekke(fylke)
        hav.extend(p for p in d["Havflate"] if p.intersects(boks_utm))
        innsjoer.extend(p for p in d["Innsjø"] + d["InnsjøRegulert"] if p.intersects(boks_utm))
        elver.extend(p for p in d["Elv"] if p.intersects(boks_utm))

    def slaa_sammen(polygoner):
        # buffer(0) reparerer, og en liten buffer ut og inn lukker sprekkene
        # der N250 deler flatene med fiktive delelinjer mellom fylkene.
        return unary_union([p.buffer(0) for p in polygoner]).buffer(1).buffer(-1)

    def til_lonlat_klippet(geom, toleranse_m, min_km2):
        deler = [p for p in polygoner_i(geom) if p.area >= min_km2 * 1e6]
        geom = MultiPolygon(deler).simplify(toleranse_m, preserve_topology=True)
        return transform(til_lonlat, geom).buffer(0).intersection(klipp)

    print("Lager land som utsnittet minus sjøflaten ...", file=sys.stderr)
    land = til_lonlat_klippet(boks_utm.difference(slaa_sammen(hav)), kart["toleranse_land_m"], kart["min_land_km2"])
    vann = til_lonlat_klippet(slaa_sammen(innsjoer), kart["toleranse_vann_m"], kart["min_innsjo_km2"])
    elv = til_lonlat_klippet(slaa_sammen(elver), kart["toleranse_vann_m"], kart["min_elv_km2"])
    landflate = MultiPolygon([p for p in polygoner_i(land) if isinstance(p, Polygon) and not p.is_empty])
    return landflate, ringer_av(vann, kart["desimaler"]) + ringer_av(elv, kart["desimaler"])


def byer_kartverket(kart):
    """Byer og tettsteder fra Kartverkets stedsnavn-API, bare treff av typen
    By eller Tettsted innenfor utsnittet (Sandvika finnes også i Lierne)."""
    lon0, lat0, lon1, lat1 = kart["bbox"]
    ut = []
    for navn in kart["byer"]:
        params = urllib.parse.urlencode({"sok": navn, "fuzzy": "false", "utkoordsys": 4258, "treffPerSide": 15, "side": 1})
        treff = [
            n for n in hent_json(f"{STEDSNAVN}?{params}").get("navn") or []
            if n.get("skrivemåte") == navn and n.get("navneobjekttype") in ("By", "Tettsted")
            and n.get("representasjonspunkt")
            and lon0 <= n["representasjonspunkt"]["øst"] <= lon1 and lat0 <= n["representasjonspunkt"]["nord"] <= lat1
        ]
        if not treff:
            print(f"ADVARSEL: fant ikke «{navn}» som by eller tettsted i utsnittet", file=sys.stderr)
            continue
        rp = treff[0]["representasjonspunkt"]
        ut.append({"navn": navn, "lon": round(rp["øst"], kart["desimaler"]), "lat": round(rp["nord"], kart["desimaler"])})
    return ut


# ---------- DNT-områdene fra ut.no (begge kartene) ----------

def tett_gliper(geoms, avstand_m, steg_m=100):
    """Lukker glipene mellom områder som ligger nærmere hverandre enn
    2 × avstand_m. Bare det som ligger innenfor avstand_m fra minst to områder
    regnes som glipe, så ytterkanter uten nabo beholder ut.no-formen. Områdene
    vokser inn i glipa i små steg etter tur, så de møtes omtrent på midten.
    Geometrien må være i meter (UTM)."""
    navn = list(geoms)
    buffere = {n: g.buffer(avstand_m) for n, g in geoms.items()}
    glipe = None
    for i, a in enumerate(navn):
        for b in navn[i + 1:]:
            felles = buffere[a].intersection(buffere[b])
            if not felles.is_empty:
                glipe = felles if glipe is None else glipe.union(felles)
    if glipe is None:
        return geoms
    glipe = glipe.difference(unary_union(list(geoms.values())))
    ut = dict(geoms)
    for _ in range(max(1, round(avstand_m / steg_m))):
        for n in navn:
            andre = unary_union([ut[m] for m in navn if m != n])
            vekst = ut[n].buffer(steg_m).intersection(glipe).difference(andre)
            ut[n] = ut[n].union(vekst).buffer(0)
    return ut


def omrader(deler, landflate, kart, klipp):
    """{kortnavn: [ringer]} fra DNT-områdene på ut.no, klippet mot landflaten.
    «deler» er «omrader» fra hytter.json, eller «delomrader» under ett område.
    Kort uten «polygon» hoppes over og får ingen nøkkel. Har kartet «tett_m»,
    lukkes glipene mellom naboområdene først, se tett_gliper."""
    geoms = {}
    for kort, regler in deler.items():
        ider = regler.get("polygon") or []
        if not ider:
            continue
        geoms[kort] = []
        for omrade_id in ider:
            print(f"Henter ut.no-område {omrade_id} ({kort}) ...", file=sys.stderr)
            a = gql("query($id: Int!) { area(id: $id) { name areaType geojson } }", {"id": omrade_id})["area"]
            if not a or not a.get("geojson"):
                print(f"ADVARSEL: ut.no-område {omrade_id} har ingen geometri", file=sys.stderr)
                continue
            if a.get("areaType") != "DNT_AREA":
                print(f"ADVARSEL: {a.get('name')} er {a.get('areaType')}, ikke DNT_AREA", file=sys.stderr)
            geoms[kort].append(klipp_og_forenkle(shape(a["geojson"]).buffer(0), klipp, kart["toleranse_detalj"]))

    if kart.get("tett_m"):
        from pyproj import Transformer
        til_utm = Transformer.from_crs("EPSG:4326", "EPSG:25833", always_xy=True).transform
        til_lonlat = Transformer.from_crs("EPSG:25833", "EPSG:4326", always_xy=True).transform
        print(f"Lukker gliper under {2 * kart['tett_m']} m mellom delområdene ...", file=sys.stderr)
        i_utm = {kort: transform(til_utm, unary_union(biter)) for kort, biter in geoms.items() if biter}
        tette = tett_gliper(i_utm, kart["tett_m"])

        def rens(g):
            # Lett forenkling etterpå, veksten gir mange små hjørner. Under
            # strekbredden i style.css, så naboene fortsatt ser ut som om de
            # deler grense. Fliser under 0,05 km² fra veksten droppes.
            g = g.simplify(40, preserve_topology=True)
            deler = [p for p in polygoner_i(g) if isinstance(p, Polygon) and p.area >= 50_000]
            return transform(til_lonlat, MultiPolygon(deler)).buffer(0)

        geoms = {kort: [rens(g)] for kort, g in tette.items()}

    ut = {}
    for kort, biter in geoms.items():
        ringer = []
        for geom in biter:
            ringer.extend(ringer_av(geom.intersection(landflate), kart["desimaler"]))
        ut[kort] = ringer
    return ut


def main():
    for stroem in (sys.stdout, sys.stderr):
        if hasattr(stroem, "reconfigure"):
            stroem.reconfigure(encoding="utf-8")
    valg = sys.argv[1] if len(sys.argv) > 1 else None
    if valg not in KART:
        print(f"Bruk: {Path(sys.argv[0]).name} <{'|'.join(KART)}>", file=sys.stderr)
        return 2
    kart = KART[valg]
    klipp = box(*kart["bbox"])
    konfig = json.loads(KONFIG.read_text(encoding="utf-8"))

    if kart["omrade"]:
        deler = konfig["omrader"][kart["omrade"]].get("delomrader") or {}
    else:
        deler = konfig["omrader"]

    if kart["kilde"] == "n250":
        landflate, innsjoer = n250_land_og_vann(kart, klipp)
        elver = []
        byer = byer_kartverket(kart)
        kilder = {
            "land, innsjoer": "Kartverket N250 Kartdata, CC BY 4.0, " + GEONORGE_N250,
            "byer": "Kartverket stedsnavn-API, " + STEDSNAVN,
            "omrader": "DNT-områder fra ut.no, " + UTNO,
        }
    else:
        landflate = land_ne(kart, klipp)
        innsjoer = innsjoer_ne(kart, klipp)
        elver = elver_ne(kart, klipp)
        byer = byer_ne(kart)
        kilder = {
            "land, innsjoer, elver, byer": "Natural Earth 1:10m, public domain, " + NE,
            "omrader": "DNT-områder fra ut.no, " + UTNO,
        }

    ut = {
        "kilder": kilder,
        "laget": date.today().isoformat(),
        "bbox": list(kart["bbox"]),
        "hav": bool(kart.get("hav")),
        "ringer": ringer_av(landflate, kart["desimaler"]),
        "omrader": omrader(deler, landflate, kart, klipp),
        "innsjoer": innsjoer,
        "elver": elver,
        "byer": byer,
    }
    utfil = ASSETS / kart["utfil"]
    utfil.write_text(json.dumps(ut, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8", newline="\n")
    print(f"Skrev {utfil.relative_to(ROT)}: {len(ut['ringer'])} landringer, "
          f"{sum(len(r) for r in ut['omrader'].values())} områderinger, "
          f"{len(ut['innsjoer'])} innsjøer, {len(ut['elver'])} elvestrekk, {len(ut['byer'])} byer, "
          f"{utfil.stat().st_size // 1024} kB", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
