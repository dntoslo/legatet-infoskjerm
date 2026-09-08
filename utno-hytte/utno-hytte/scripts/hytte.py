#!/usr/bin/env python3
"""Slår opp hyttedata på ut.no via GraphQL-endepunktet bak nettsiden.

Bruk:
  hytte.py 10604                                   ut.no-ID
  hytte.py https://ut.no/hytte/10604/gjendesheim   ut.no-URL
  hytte.py Gjendesheim                             navnesøk
  hytte.py --liste                                 alle hytter til DNT Oslo og Omegn, per servicenivå
  hytte.py --liste selvbetjent                     bare ett nivå (betjent, selvbetjent, ubetjent)
  hytte.py --liste --eier 156                      annen eierforening (ut.no sin gruppe-ID)
  hytte.py ... --json                              rå JSON i stedet for markdown

Avslutningskoder: 0 ok, 1 feil mot ut.no, 2 flere treff eller feil bruk.
Kun standardbiblioteket, ingenting å installere.
"""

import argparse
import html
import json
import re
import sys
import urllib.error
import urllib.request
from datetime import date

ENDPOINT = "https://ut.no/api/graphql"
USER_AGENT = "dntoslo-utno-skill/0.1 (+https://github.com/dntoslo/claude-plugins)"
TIMEOUT_SEK = 10
DNT_OSLO_ID = 156

NIVAA_ARG = {
    "betjent": "STAFFED",
    "selvbetjent": "SELF_SERVICE",
    "ubetjent": "NO_SERVICE",
}
NIVAA_NORSK = {
    "STAFFED": "betjent",
    "SELF_SERVICE": "selvbetjent",
    "NO_SERVICE": "ubetjent",
    "NO_SERVICE_NO_BEDS": "ubetjent uten senger",
    "FOOD_SERVICE": "servering",
    "EMERGENCY_SHELTER": "nødbu",
    "CLOSED": "stengt",
    "RENTAL": "utleie",
    "UNKNOWN": "ukjent",
}
NIVAA_REKKEFOELGE = list(NIVAA_NORSK)
LENKETYPE_NORSK = {
    "price": "Priser",
    "weather": "Været",
    "homepage": "Hjemmeside",
    "booking": "Booking",
    "facebook": "Facebook",
    "instagram": "Instagram",
    "video": "Video",
}
MAKS_SOEKETREFF = 20
MAANEDER = [
    "januar", "februar", "mars", "april", "mai", "juni",
    "juli", "august", "september", "oktober", "november", "desember",
]

HYTTE_FELT = """
  id name status serviceLevel dntCabin geojson elevationCustom yearOfConstruction
  bedsStaffed bedsSelfService bedsNoService bedsWinter bedsExtra
  email phone mobile bookingEnabled bookingOnly bookingUrl
  carAllYear carSummer bicycle publicTransportAvailable boatTransportAvailable
  serviceStatusToday { serviceLevel beds from to openAllYear }
  serviceStatusAll { serviceLevel beds from to openAllYear }
  municipalities { name } counties { name } areas { name } protectedAreas { name }
  facilities { displayName } accessibilities { displayName } suitableFor { displayName }
  ownerGroupConnection { id name } links { type url title }
  summertimeText wintertimeText description updatedAt
"""

Q_HYTTE = "query($id: Int!) { cabin(id: $id) { %s } }" % HYTTE_FELT

Q_SOEK = """
query($navn: String!) {
  cabins(paging: {first: %d}, filter: {name: {iLike: $navn}, status: {eq: PUBLIC}}, sorting: []) {
    edges { node { id name serviceLevel ownerGroupConnection { id name } } }
  }
}
""" % MAKS_SOEKETREFF

Q_LISTE = """
query($eier: Int!) {
  cabins(paging: {first: 500}, filter: {ownerGroupId: {eq: $eier}, status: {eq: PUBLIC}},
         sorting: [{field: name, direction: ASC}]) {
    totalCount
    edges { node {
      id name serviceLevel bedsStaffed bedsSelfService bedsNoService bedsWinter
      municipalities { name } areas { name } ownerGroupConnection { name }
    } }
  }
}
"""


class UtNoFeil(Exception):
    """Noe gikk galt mot ut.no. Meldingen er ment for brukeren."""


def gql(query, variables=None):
    body = json.dumps({"query": query, "variables": variables or {}}).encode("utf-8")
    req = urllib.request.Request(
        ENDPOINT,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SEK) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise UtNoFeil(f"ut.no svarte HTTP {e.code}") from e
    except urllib.error.URLError as e:
        raise UtNoFeil(f"fikk ikke kontakt med ut.no ({e.reason})") from e
    except OSError as e:
        raise UtNoFeil(f"nettverksfeil mot ut.no ({e})") from e
    except ValueError as e:
        raise UtNoFeil("ut.no svarte med noe som ikke er JSON") from e
    if data.get("errors"):
        meldinger = "; ".join(str(err.get("message", "?")) for err in data["errors"])
        raise UtNoFeil(f"GraphQL-feil fra ut.no: {meldinger}")
    return data.get("data") or {}


def hytte_url(hytte_id):
    return f"https://ut.no/hytte/{hytte_id}"


def finn_id(oppslag):
    """Returnerer (id, None) ved entydig treff, eller (None, kandidater) ved flere."""
    s = oppslag.strip()
    if s.isdigit():
        return int(s), None
    m = re.search(r"ut\.no/hytte/(\d+)", s)
    if m:
        return int(m.group(1)), None

    data = gql(Q_SOEK, {"navn": f"%{s}%"})
    treff = [e["node"] for e in data.get("cabins", {}).get("edges", [])]
    if not treff:
        raise UtNoFeil(f"fant ingen publisert hytte på ut.no som matcher «{s}»")
    if len(treff) == 1:
        return treff[0]["id"], None

    eksakt = [t for t in treff if t["name"].casefold() == s.casefold()]
    if len(eksakt) == 1:
        return eksakt[0]["id"], None

    oslo = [t for t in treff if (t.get("ownerGroupConnection") or {}).get("id") == DNT_OSLO_ID]
    if len(oslo) == 1:
        return oslo[0]["id"], None

    return None, treff


def dato(iso):
    if not iso:
        return None
    d = date.fromisoformat(iso[:10])
    return f"{d.day}. {MAANEDER[d.month - 1]} {d.year}"


def strip_html(s):
    if not s:
        return ""
    s = re.sub(r"<br\s*/?>", "\n", s, flags=re.I)
    s = re.sub(r"</(p|h\d|li|div|ul|ol)>", "\n", s, flags=re.I)
    s = re.sub(r"<li[^>]*>", "- ", s, flags=re.I)
    s = re.sub(r"<[^>]+>", "", s)
    s = html.unescape(s)
    s = s.replace("\xa0", " ")
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r" *\n *", "\n", s)
    s = re.sub(r"\n{2,}", "\n\n", s)
    return s.strip()


def navn_liste(elementer, felt="name"):
    return [e[felt] for e in (elementer or []) if e and e.get(felt)]


def periode_gjelder_naa(p, i_dag):
    if p.get("openAllYear"):
        return True
    fra = date.fromisoformat(p["from"][:10]) if p.get("from") else None
    til = date.fromisoformat(p["to"][:10]) if p.get("to") else None
    return (fra is None or fra <= i_dag) and (til is None or i_dag <= til)


def periode_tekst(p):
    nivaa = NIVAA_NORSK.get(p.get("serviceLevel"), p.get("serviceLevel") or "ukjent")
    if p.get("openAllYear"):
        naar = "Hele året"
    elif p.get("from") and p.get("to"):
        naar = f"{dato(p['from'])} til {dato(p['to'])}"
    elif p.get("from"):
        naar = f"Fra {dato(p['from'])}"
    elif p.get("to"):
        naar = f"Til {dato(p['to'])}"
    else:
        naar = "Uten datoer"
    tekst = f"{naar}: {nivaa}"
    senger = p.get("beds")
    if senger and nivaa != "stengt":
        tekst += f", {int(senger)} senger"
    return tekst


def render_hytte(c, i_dag):
    ut = []
    ut.append(f"# {c['name']}")
    ut.append("")
    nivaa = NIVAA_NORSK.get(c.get("serviceLevel"), c.get("serviceLevel") or "ukjent")
    eier = (c.get("ownerGroupConnection") or {}).get("name")
    fakta = [f"- Type: {nivaa} hytte" + ("" if c.get("dntCabin") else " (ikke DNT-hytte)")]
    if eier:
        fakta.append(f"- Eier: {eier}")
    if c.get("yearOfConstruction"):
        fakta.append(f"- Byggeår: {c['yearOfConstruction']}")
    if c.get("status") and c["status"] != "PUBLIC":
        fakta.append(f"- Status på ut.no: {c['status']}")
    fakta.append(f"- ut.no: {hytte_url(c['id'])}")
    if c.get("updatedAt"):
        fakta.append(f"- Sist oppdatert på ut.no: {dato(c['updatedAt'])}")
    ut.extend(fakta)

    ut.append("")
    ut.append("## Sengeplasser")
    senger = [
        ("Betjent", c.get("bedsStaffed")),
        ("Selvbetjent", c.get("bedsSelfService")),
        ("Ubetjent", c.get("bedsNoService")),
        ("Vinter", c.get("bedsWinter")),
        ("Ekstra (madrasser o.l.)", c.get("bedsExtra")),
    ]
    senger = [(k, v) for k, v in senger if v]
    if senger:
        ut.extend(f"- {k}: {v}" for k, v in senger)
    else:
        ut.append("- Ingen sengetall registrert på ut.no.")

    ut.append("")
    ut.append("## Åpningstider")
    i_dag_status = c.get("serviceStatusToday")
    if i_dag_status and i_dag_status.get("serviceLevel"):
        ut.append(f"- I dag ({i_dag.isoformat()}): {periode_tekst(i_dag_status)}")
    else:
        ut.append(f"- I dag ({i_dag.isoformat()}): ingen status registrert på ut.no")
    perioder = c.get("serviceStatusAll") or []
    if perioder:
        ut.append("- Registrerte perioder:")
        for p in perioder:
            markering = " (nå)" if periode_gjelder_naa(p, i_dag) else ""
            ut.append(f"  - {periode_tekst(p)}{markering}")
    else:
        ut.append("- Ingen perioder registrert på ut.no.")

    ut.append("")
    ut.append("## Sted")
    kommuner = navn_liste(c.get("municipalities"))
    fylker = navn_liste(c.get("counties"))
    omraader = navn_liste(c.get("areas"))
    vern = navn_liste(c.get("protectedAreas"))
    if kommuner:
        ut.append(f"- Kommune: {', '.join(kommuner)}")
    if fylker:
        ut.append(f"- Fylke: {', '.join(fylker)}")
    if omraader:
        ut.append(f"- Område: {', '.join(omraader)}")
    if vern:
        ut.append(f"- Verneområde: {', '.join(vern)}")
    koord = (c.get("geojson") or {}).get("coordinates") or []
    if len(koord) >= 2:
        lon, lat = koord[0], koord[1]
        ut.append(f"- Koordinater: {lat:.5f} N, {lon:.5f} Ø")
    hoyde = c.get("elevationCustom")
    if hoyde is None and len(koord) >= 3 and koord[2]:
        hoyde = koord[2]
    if hoyde is not None:
        ut.append(f"- Høyde: {round(hoyde)} moh.")
    if not any([kommuner, fylker, omraader, koord]):
        ut.append("- Ingen stedsdata registrert på ut.no.")

    ut.append("")
    ut.append("## Adkomst")
    flagg = []
    if c.get("carAllYear"):
        flagg.append("bilvei hele året")
    elif c.get("carSummer"):
        flagg.append("bilvei om sommeren")
    if c.get("publicTransportAvailable"):
        flagg.append("kollektivtransport i nærheten")
    if c.get("boatTransportAvailable"):
        flagg.append("båttransport")
    if c.get("bicycle"):
        flagg.append("kan sykles til")
    if flagg:
        ut.append(f"- Stikkord: {', '.join(flagg)}")
    sommer = strip_html(c.get("summertimeText"))
    vinter = strip_html(c.get("wintertimeText"))
    if sommer:
        ut.append("")
        ut.append("Sommer:")
        ut.append(sommer)
    if vinter:
        ut.append("")
        ut.append("Vinter:")
        ut.append(vinter)
    if not (flagg or sommer or vinter):
        ut.append("- Ingen adkomstinformasjon registrert på ut.no.")

    ut.append("")
    ut.append("## Kontakt og booking")
    if c.get("email"):
        ut.append(f"- E-post: {c['email']}")
    telefon = (c.get("phone") or "").strip()
    mobil = (c.get("mobile") or "").strip()
    if telefon:
        ut.append(f"- Telefon: {telefon}")
    if mobil and mobil != telefon:
        ut.append(f"- Mobil: {mobil}")
    if c.get("bookingUrl"):
        ut.append(f"- Booking: {c['bookingUrl']}")
    if c.get("bookingOnly"):
        ut.append("- Kun forhåndsbestilling.")
    elif c.get("bookingEnabled") is False:
        ut.append("- Booking er ikke aktivert på ut.no.")
    for lenke in c.get("links") or []:
        if lenke.get("url"):
            lenketype = (lenke.get("type") or "").lower()
            tittel = lenke.get("title") or LENKETYPE_NORSK.get(lenketype) or lenketype or "Lenke"
            ut.append(f"- {tittel}: {lenke['url']}")

    fasiliteter = navn_liste(c.get("facilities"), "displayName")
    egnet = navn_liste(c.get("suitableFor"), "displayName")
    tilgj = navn_liste(c.get("accessibilities"), "displayName")
    if fasiliteter or egnet or tilgj:
        ut.append("")
        ut.append("## Fasiliteter")
        if fasiliteter:
            ut.append(f"- Fasiliteter: {', '.join(fasiliteter)}")
        if egnet:
            ut.append(f"- Egnet for: {', '.join(egnet)}")
        if tilgj:
            ut.append(f"- Tilgjengelighet: {', '.join(tilgj)}")

    beskrivelse = strip_html(c.get("description"))
    if beskrivelse:
        ut.append("")
        ut.append("## Beskrivelse fra ut.no")
        ut.append(beskrivelse)

    ut.append("")
    ut.append(f"Kilde: {hytte_url(c['id'])} hentet {i_dag.isoformat()}")
    return "\n".join(ut)


def senger_for_nivaa(rad):
    nivaa = rad.get("serviceLevel")
    direkte = {
        "STAFFED": rad.get("bedsStaffed"),
        "SELF_SERVICE": rad.get("bedsSelfService"),
        "NO_SERVICE": rad.get("bedsNoService"),
    }.get(nivaa)
    if direkte:
        return direkte
    total = sum(rad.get(f) or 0 for f in ("bedsStaffed", "bedsSelfService", "bedsNoService"))
    return total or ""


def render_liste(rader, total_paa_utno, eier_id, filter_nivaa, i_dag):
    eier_navn = next(
        ((r.get("ownerGroupConnection") or {}).get("name") for r in rader if r.get("ownerGroupConnection")),
        f"eier-ID {eier_id}",
    )
    ut = [f"# Hytter på ut.no eid av {eier_navn}", ""]
    grupper = {}
    for r in rader:
        grupper.setdefault(r.get("serviceLevel") or "UNKNOWN", []).append(r)
    rekkefoelge = [n for n in NIVAA_REKKEFOELGE if n in grupper] + [n for n in grupper if n not in NIVAA_REKKEFOELGE]
    for nivaa in rekkefoelge:
        gruppe = grupper[nivaa]
        ut.append(f"## {NIVAA_NORSK.get(nivaa, nivaa).capitalize()} ({len(gruppe)})")
        ut.append("")
        ut.append("| Hytte | ut.no-ID | Senger | Kommune | Område |")
        ut.append("|---|---|---|---|---|")
        for r in gruppe:
            ut.append(
                "| {navn} | {id} | {senger} | {kommune} | {omraade} |".format(
                    navn=r["name"],
                    id=r["id"],
                    senger=senger_for_nivaa(r),
                    kommune=", ".join(navn_liste(r.get("municipalities"))),
                    omraade=", ".join(navn_liste(r.get("areas"))),
                )
            )
        ut.append("")
    if filter_nivaa:
        ut.append(f"Viser bare {NIVAA_NORSK[filter_nivaa]}e hytter: {len(rader)} av {total_paa_utno} publiserte hytter.")
    else:
        ut.append(f"Totalt {len(rader)} publiserte hytter.")
    if total_paa_utno > 500:
        ut.append("Merk: ut.no melder om flere hytter enn scriptet henter (maks 500). Listen kan være ufullstendig.")
    ut.append(f"Kilde: ut.no (GraphQL, eier-ID {eier_id}) hentet {i_dag.isoformat()}")
    return "\n".join(ut)


def kjoer_liste(args, i_dag):
    filter_nivaa = NIVAA_ARG.get(args.liste) if args.liste != "alle" else None
    data = gql(Q_LISTE, {"eier": args.eier})
    cabins = data.get("cabins") or {}
    rader = [e["node"] for e in cabins.get("edges", [])]
    if filter_nivaa:
        rader = [r for r in rader if r.get("serviceLevel") == filter_nivaa]
    if args.json:
        print(json.dumps({"eier": args.eier, "hentet": i_dag.isoformat(), "hytter": rader}, ensure_ascii=False, indent=1))
    else:
        print(render_liste(rader, cabins.get("totalCount", len(rader)), args.eier, filter_nivaa, i_dag))
    return 0


def kjoer_hytte(args, i_dag):
    hytte_id, kandidater = finn_id(args.hytte)
    if kandidater:
        print(f"Flere hytter på ut.no matcher «{args.hytte}». Spør brukeren hvilken som menes:", file=sys.stderr)
        for k in kandidater:
            nivaa = NIVAA_NORSK.get(k.get("serviceLevel"), k.get("serviceLevel") or "ukjent")
            eier = (k.get("ownerGroupConnection") or {}).get("name") or "ukjent eier"
            print(f"  {k['id']}: {k['name']} ({nivaa}, {eier})", file=sys.stderr)
        if len(kandidater) >= MAKS_SOEKETREFF:
            print(f"Viser bare de første {MAKS_SOEKETREFF}. Be om et mer presist navn.", file=sys.stderr)
        return 2
    data = gql(Q_HYTTE, {"id": hytte_id})
    hytte = data.get("cabin")
    if not hytte:
        raise UtNoFeil(f"ut.no har ingen hytte med ID {hytte_id} ({hytte_url(hytte_id)})")
    if args.json:
        hytte = dict(hytte, kilde=hytte_url(hytte_id), hentet=i_dag.isoformat())
        print(json.dumps(hytte, ensure_ascii=False, indent=1))
    else:
        print(render_hytte(hytte, i_dag))
    return 0


def main(argv=None):
    for strøm in (sys.stdout, sys.stderr):
        if hasattr(strøm, "reconfigure"):
            strøm.reconfigure(encoding="utf-8")

    p = argparse.ArgumentParser(
        description="Henter hyttedata fra ut.no.",
        epilog=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("hytte", nargs="?", help="ut.no-ID, ut.no-URL eller hyttenavn")
    p.add_argument(
        "--liste",
        nargs="?",
        const="alle",
        choices=["alle", "betjent", "selvbetjent", "ubetjent"],
        metavar="NIVÅ",
        help="list eierens hytter, eventuelt bare ett nivå: betjent, selvbetjent eller ubetjent",
    )
    p.add_argument("--eier", type=int, default=DNT_OSLO_ID, help=f"eier-ID på ut.no for --liste (standard {DNT_OSLO_ID}, DNT Oslo og Omegn)")
    p.add_argument("--json", action="store_true", help="skriv rå JSON i stedet for markdown")
    args = p.parse_args(argv)

    if not args.hytte and not args.liste:
        p.print_help()
        return 2

    i_dag = date.today()
    try:
        if args.liste:
            return kjoer_liste(args, i_dag)
        return kjoer_hytte(args, i_dag)
    except UtNoFeil as e:
        print(f"Oppslag mot ut.no feilet: {e}.", file=sys.stderr)
        if args.hytte and args.hytte.strip().isdigit():
            print(f"Se hytta direkte på {hytte_url(args.hytte.strip())}", file=sys.stderr)
        elif args.hytte:
            print("Se hytta direkte på https://ut.no (søk på navnet).", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
