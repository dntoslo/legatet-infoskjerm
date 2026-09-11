#!/usr/bin/env python3
"""Henter foreningens betjente og selvbetjente hytter fra ut.no og skriver data.json.

Kjøres av GitHub Action to ganger om dagen, eller manuelt:

  python scripts/hent_data.py

Utvalget er dynamisk. Én GraphQL-spørring gir alle publiserte hytter til
eieren i hytter.json (DNT Oslo og Omegn, 156). Scriptet tar med hyttene med
serviceLevel STAFFED og SELF_SERVICE, utelater selvbetjeningskvarter ved
betjente hytter, og plasserer hver hytte i et visningsområde etter reglene i
hytter.json. Visningen (betjente.html og selvbetjente.html med assets/app.js)
filtrerer på serviceLevel per side og regner ut status for i dag selv.

Kun standardbiblioteket. Feiler hentingen eller reglene, avsluttes scriptet
med kode 1 uten å røre data.json, slik at forrige gyldige fil beholdes og
kjøringen blir rød. Regelfeil samles og rapporteres samlet, så én kjøring
viser alle overstyringene som mangler.
"""

import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROT = Path(__file__).resolve().parent.parent
KONFIG = ROT / "hytter.json"
UTFIL = ROT / "data.json"

ENDPOINT = "https://ut.no/api/graphql"
USER_AGENT = "dntoslo-legatet-infoskjerm/1.0 (+https://github.com/dntoslo/legatet-infoskjerm)"
TIMEOUT_SEK = 60            # hele hyttelista er rundt 200 kB
FORSOEK = 3
PAUSE_SEK = 5

# Servicenivåene som vises, i rekkefølgen de skrives til data.json. NO_SERVICE
# (ubetjente hytter i marka og langs fjorden) er et eget tilbud og eventuelt
# en egen side senere. CLOSED er varig stengte hytter, EMERGENCY_SHELTER
# nødbuer og FOOD_SERVICE serveringssteder, ingen av dem har åpningsperioder
# som gir mening på skjermen.
NIVAER = ("STAFFED", "SELF_SERVICE")
SENGEFELT = {"STAFFED": "bedsStaffed", "SELF_SERVICE": "bedsSelfService"}


def naa_oslo():
    """Nå i norsk tid. Bruker zoneinfo der den finnes (Linux, GitHub Actions).
    Windows-Python mangler ofte tzdata, da regnes EU-sommertid ut manuelt:
    UTC+2 fra siste søndag i mars 01:00 UTC til siste søndag i oktober 01:00 UTC."""
    utc = datetime.now(timezone.utc)
    try:
        from zoneinfo import ZoneInfo
        return utc.astimezone(ZoneInfo("Europe/Oslo"))
    except Exception:
        pass

    def siste_soendag(aar, maaned):
        d = datetime(aar, maaned + 1, 1, 1, tzinfo=timezone.utc) - timedelta(days=1)
        return d - timedelta(days=(d.weekday() + 1) % 7)

    sommer_start = siste_soendag(utc.year, 3)
    sommer_slutt = siste_soendag(utc.year, 10)
    offset = 2 if sommer_start <= utc < sommer_slutt else 1
    return utc.astimezone(timezone(timedelta(hours=offset)))


# Alle publiserte hytter til én eier, med perioder og områder i samme svar.
# paging, filter og sorting er påkrevd på cabins. 500 er godt over de 147
# hyttene foreningen har, og scriptet feiler hvis det likevel ikke rekker.
Q_HYTTER = """
query($eier: Int!) {
  cabins(paging: {first: 500},
         filter: {ownerGroupId: {eq: $eier}, status: {eq: PUBLIC}},
         sorting: [{field: name, direction: ASC}]) {
    totalCount
    pageInfo { hasNextPage }
    edges { node {
      id name serviceLevel updatedAt geojson bedsStaffed bedsSelfService
      areas { id name areaType }
      serviceStatusAll { serviceLevel beds from to openAllYear }
    } }
  }
}
"""


class UtNoFeil(Exception):
    """Nettverk, HTTP eller GraphQL feilet, eller svaret var ufullstendig."""


class KonfigFeil(Exception):
    """Reglene i hytter.json er ugyldige eller dekker ikke en hytte."""


def advarsel(melding):
    """Til stderr, og som gul annotasjon i kjøringsoppsummeringen på GitHub."""
    prefiks = "::warning::" if os.environ.get("GITHUB_ACTIONS") else "MERK  "
    print(f"{prefiks}{melding}", file=sys.stderr)


def gql(query, variables):
    body = json.dumps({"query": query, "variables": variables}).encode("utf-8")
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
        raise UtNoFeil(f"HTTP {e.code}") from e
    except (urllib.error.URLError, OSError) as e:
        raise UtNoFeil(f"nettverksfeil ({e})") from e
    except ValueError as e:
        raise UtNoFeil("svaret var ikke JSON") from e
    if data.get("errors"):
        meldinger = "; ".join(str(err.get("message", "?")) for err in data["errors"])
        raise UtNoFeil(f"GraphQL-feil: {meldinger}")
    return data.get("data") or {}


def dato(iso):
    """ut.no gir UTC midnatt, vi bruker bare datodelen."""
    return iso[:10] if iso else None


def heltall(verdi, hva):
    try:
        return int(verdi)
    except (TypeError, ValueError):
        raise KonfigFeil(f"{hva}: «{verdi}» er ikke et heltall") from None


def les_konfig():
    """Leser og validerer reglene i hytter.json.

    Returnerer eier, områdene i kanonisk rekkefølge, en mapping fra ut.no
    område-ID til visningsnavn, ut.no-navnet per område-ID (for å oppdage
    navneendringer), overstyringer per hytte-ID og utelatelsesreglene."""
    try:
        raa = json.loads(KONFIG.read_text(encoding="utf-8"))
    except ValueError as e:
        raise KonfigFeil(f"{KONFIG.name} er ikke gyldig JSON ({e})") from None

    omrader = raa.get("omrader")
    if not isinstance(omrader, dict) or not omrader:
        raise KonfigFeil("«omrader» må være et objekt med minst ett område")

    id_til_omrade = {}
    omradenavn_utno = {}
    for navn, regler in omrader.items():
        grupper = regler.get("grupper") or {}
        if not isinstance(grupper, dict) or not grupper:
            raise KonfigFeil(f"{navn}: «grupper» må ha minst én ut.no-område-ID")
        for streng, utno_navn in grupper.items():
            omrade_id = heltall(streng, f"{navn}.grupper")
            if omrade_id in id_til_omrade:
                raise KonfigFeil(f"ut.no-område {omrade_id} står under både {id_til_omrade[omrade_id]} og {navn}")
            id_til_omrade[omrade_id] = navn
            omradenavn_utno[omrade_id] = utno_navn
        for omrade_id in regler.get("polygon") or []:
            if id_til_omrade.get(heltall(omrade_id, f"{navn}.polygon")) != navn:
                raise KonfigFeil(f"{navn}: polygon {omrade_id} står ikke i «grupper» for samme område")

    overstyr = {}
    for streng, regel in (raa.get("overstyr") or {}).items():
        hytte_id = heltall(streng, "overstyr")
        ukjent = set(regel) - {"navn", "navnUtno", "omrade"}
        if ukjent:
            raise KonfigFeil(f"overstyr {hytte_id}: ukjente felt {sorted(ukjent)}")
        if "omrade" in regel and regel["omrade"] not in omrader:
            raise KonfigFeil(f"overstyr {hytte_id}: området «{regel['omrade']}» finnes ikke i «omrader»")
        overstyr[hytte_id] = regel

    utelat = raa.get("utelat") or {}
    monster = None
    if utelat.get("navnMonster"):
        try:
            monster = re.compile(utelat["navnMonster"], re.IGNORECASE)
        except re.error as e:
            raise KonfigFeil(f"utelat.navnMonster er ikke et gyldig regulært uttrykk ({e})") from None

    return {
        "eier": heltall(raa.get("eier"), "eier"),
        "omrader": list(omrader),
        "id_til_omrade": id_til_omrade,
        "omradenavn_utno": omradenavn_utno,
        "overstyr": overstyr,
        "utelat_monster": monster,
        "utelat_ider": {heltall(i, "utelat.ider") for i in utelat.get("ider") or []},
    }


def hent_alle(eier):
    """Alle publiserte hytter til eieren, som liste av cabin-noder."""
    siste_feil = None
    data = None
    for forsoek in range(FORSOEK):
        try:
            data = gql(Q_HYTTER, {"eier": eier})
            break
        except UtNoFeil as e:
            siste_feil = e
            print(f"FEIL  forsøk {forsoek + 1} av {FORSOEK}: {e}", file=sys.stderr)
            if forsoek < FORSOEK - 1:
                time.sleep(PAUSE_SEK)
    if data is None:
        raise siste_feil

    cabins = data.get("cabins") or {}
    hytter = [e["node"] for e in cabins.get("edges") or [] if e.get("node")]
    total = cabins.get("totalCount")
    if not hytter:
        raise UtNoFeil(f"ut.no ga ingen hytter for eier {eier}")
    if (cabins.get("pageInfo") or {}).get("hasNextPage") or total != len(hytter):
        raise UtNoFeil(f"ut.no har {total} hytter, fikk {len(hytter)}. Øk paging i Q_HYTTER eller legg inn paginering")
    return hytter


def skal_utelates(cabin, konfig):
    """Selvbetjeningskvarter ved betjente hytter fører ut.no som egne hytter
    med «Selvbetjent» eller «selvbetjening» i navnet. Hovedhytta står på
    side 1 og viser overgangen til selvbetjening selv.

    Utelatelsen skjer før områdemappingen med hensikt: Brebua ved Finsehytta
    ligger i to DNT-områder på ut.no og ville ellers krevd en overstyring."""
    if cabin["id"] in konfig["utelat_ider"]:
        return True
    monster = konfig["utelat_monster"]
    return bool(monster and monster.search(cabin.get("name") or ""))


def bestem_omrade(cabin, konfig):
    """Visningsområdet for en hytte: overstyring hvis den finnes, ellers det ene
    området DNT-områdene på ut.no mapper til. Null eller flere treff er en
    regelfeil, scriptet skal ikke gjette."""
    regel = konfig["overstyr"].get(cabin["id"], {})
    if regel.get("omrade"):
        return regel["omrade"]

    dnt = [a for a in cabin.get("areas") or [] if a.get("areaType") == "DNT_AREA"]
    treff = {}
    for a in dnt:
        navn = konfig["id_til_omrade"].get(a.get("id"))
        if not navn:
            continue
        treff.setdefault(navn, []).append(a)
        if konfig["omradenavn_utno"][a["id"]] != a.get("name"):
            advarsel(f"ut.no-område {a['id']} heter nå «{a.get('name')}», hytter.json sier «{konfig['omradenavn_utno'][a['id']]}»")

    hvem = f"{cabin.get('name')} ({cabin['id']})"
    beskriv = ", ".join(f"{a.get('name')} ({a.get('id')})" for a in dnt) or "ingen DNT-områder på ut.no"
    if len(treff) == 1:
        return next(iter(treff))
    if not treff:
        raise KonfigFeil(f"{hvem}: ingen av områdene er kjent ({beskriv}). "
                         f"Legg ID-en i «grupper» under riktig område, eller sett «overstyr» for {cabin['id']} med «omrade»")
    raise KonfigFeil(f"{hvem}: ligger i både {' og '.join(treff)} ({beskriv}). "
                     f"Sett «overstyr» for {cabin['id']} med «omrade»")


def visningsnavn(cabin, konfig):
    """Overstyrt navn eller ut.no-navnet. «navnUtno» i overstyringen sier hva
    ut.no kalte hytta da overstyringen ble lagt inn, og gir varsel hvis ut.no
    har endret navnet siden, så noen kan vurdere om overstyringen fortsatt trengs."""
    regel = konfig["overstyr"].get(cabin["id"], {})
    if regel.get("navnUtno") and regel["navnUtno"] != cabin.get("name"):
        advarsel(f"{cabin.get('name')} ({cabin['id']}) het «{regel['navnUtno']}» da overstyringen ble laget, sjekk om «{regel.get('navn')}» fortsatt er riktig")
    return regel.get("navn") or cabin.get("name")


def koordinater(cabin):
    """(lon, lat) fra geojson-punktet på ut.no, eller (None, None) hvis det mangler.
    Brukes til prikkene på kartet i assets/app.js. Koordinatene er offentlige på ut.no."""
    try:
        lon, lat = cabin["geojson"]["coordinates"][:2]
        return round(float(lon), 4), round(float(lat), 4)
    except (KeyError, TypeError, ValueError):
        print(f"ADVARSEL {cabin.get('name')}: mangler koordinater på ut.no", file=sys.stderr)
        return None, None


def normaliser(cabin, navn, omrade):
    lon, lat = koordinater(cabin)
    niva = cabin.get("serviceLevel")
    perioder = []
    for p in cabin.get("serviceStatusAll") or []:
        perioder.append(
            {
                "niva": p.get("serviceLevel") or "UNKNOWN",
                "senger": int(p["beds"]) if p.get("beds") else 0,
                "fra": dato(p.get("from")),
                "til": dato(p.get("to")),
                "heleAaret": bool(p.get("openAllYear")),
            }
        )
    perioder.sort(key=lambda p: (p["fra"] or "", p["til"] or "", p["niva"]))
    return {
        "id": cabin["id"],
        "navn": navn,
        "navnUtno": cabin.get("name"),
        "omrade": omrade,
        "utnoUrl": f"https://ut.no/hytte/{cabin['id']}",
        "lon": lon,
        "lat": lat,
        "serviceLevel": niva,
        "senger": int(cabin.get(SENGEFELT.get(niva, ""), 0) or 0),
        "oppdatertUtno": cabin.get("updatedAt"),
        "perioder": perioder,
    }


def navnenoekkel(s):
    """Sorteringsnøkkel for norsk alfabet uten locale: æ, ø og å etter z.
    Tegnene { | } ligger rett etter z i Unicode."""
    return (s or "").casefold().translate(str.maketrans("æøå", "{|}"))


def varsle_endringer(forrige, nye):
    """Sier fra i loggen når antall hytter endrer seg, så layoutbrudd på
    skjermen oppdages uten å åpne siden."""
    for niva in NIVAER:
        n0 = sum(1 for h in forrige if h.get("serviceLevel") == niva)
        n1 = sum(1 for h in nye if h.get("serviceLevel") == niva)
        if n0 != n1:
            advarsel(f"antall {niva} endret {n0} → {n1}, sjekk at alt får plass på skjermen")
    gamle = {h["id"]: h for h in forrige}
    ferske = {h["id"]: h for h in nye}
    for hytte_id in sorted(set(ferske) - set(gamle)):
        h = ferske[hytte_id]
        advarsel(f"NY {h['navn']} ({hytte_id}) i {h['omrade']}, {h['serviceLevel']}")
    for hytte_id in sorted(set(gamle) - set(ferske)):
        h = gamle[hytte_id]
        advarsel(f"FJERNET {h['navn']} ({hytte_id}) fra {h.get('omrade')}")


def main():
    for stroem in (sys.stdout, sys.stderr):
        if hasattr(stroem, "reconfigure"):
            stroem.reconfigure(encoding="utf-8")

    try:
        konfig = les_konfig()
    except KonfigFeil as e:
        print(f"FEIL  {KONFIG.name}: {e}", file=sys.stderr)
        return 1

    try:
        alle = hent_alle(konfig["eier"])
    except UtNoFeil as e:
        print(f"FEIL  ut.no: {e}. data.json er ikke endret.", file=sys.stderr)
        return 1
    print(f"ut.no har {len(alle)} publiserte hytter for eier {konfig['eier']}")

    hytter_ut = []
    feil = []
    sett = set()
    for cabin in alle:
        sett.add(cabin["id"])
        if cabin.get("serviceLevel") not in NIVAER:
            continue
        if skal_utelates(cabin, konfig):
            print(f"UTELATT {cabin.get('name')} ({cabin['id']})", file=sys.stderr)
            continue
        try:
            omrade = bestem_omrade(cabin, konfig)
        except KonfigFeil as e:
            feil.append(str(e))
            print(f"FEIL  {e}", file=sys.stderr)
            continue
        hytter_ut.append(normaliser(cabin, visningsnavn(cabin, konfig), omrade))

    for hytte_id in sorted(set(konfig["overstyr"]) - sett):
        advarsel(f"overstyr {hytte_id} gjelder en hytte ut.no ikke lenger fører på eieren")
    for niva in NIVAER:
        if not any(h["serviceLevel"] == niva for h in hytter_ut):
            feil.append(f"ingen hytter med serviceLevel {niva} etter reglene")

    if feil:
        print(f"\n{len(feil)} feil i reglene. data.json er ikke endret.", file=sys.stderr)
        return 1

    hytter_ut.sort(key=lambda h: (NIVAER.index(h["serviceLevel"]), konfig["omrader"].index(h["omrade"]), navnenoekkel(h["navn"])))
    for niva in NIVAER:
        gruppe = [h for h in hytter_ut if h["serviceLevel"] == niva]
        per_omrade = ", ".join(f"{o} {sum(1 for h in gruppe if h['omrade'] == o)}"
                               for o in konfig["omrader"] if any(h["omrade"] == o for h in gruppe))
        print(f"{niva}: {len(gruppe)} hytter ({per_omrade})")
        for h in gruppe:
            print(f"OK    {h['navn']}: {len(h['perioder'])} perioder")

    # Har selve hyttedataene endret seg siden sist? Tidsstempelet «hentet»
    # endres alltid, så det holdes utenfor sammenligningen. GitHub Action
    # bruker svaret til å bare committe når noe faktisk er nytt, mens den
    # publiserte siden alltid får ferskt tidsstempel.
    endret = True
    forrige_hytter = []
    if UTFIL.exists():
        try:
            forrige = json.loads(UTFIL.read_text(encoding="utf-8"))
            forrige_hytter = forrige.get("hytter") or []
            endret = forrige_hytter != hytter_ut or forrige.get("omrader") != konfig["omrader"]
        except ValueError:
            endret = True
    varsle_endringer(forrige_hytter, hytter_ut)

    naa = naa_oslo().replace(microsecond=0)
    ut = {
        "hentet": naa.isoformat(),
        "kilde": "https://ut.no",
        "omrader": konfig["omrader"],
        "hytter": hytter_ut,
    }
    UTFIL.write_text(json.dumps(ut, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"\nSkrev {UTFIL.name} med {len(hytter_ut)} hytter, hentet {naa.isoformat()}")
    print("Hyttedata endret siden sist" if endret else "Hyttedata uendret siden sist")

    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a", encoding="utf-8") as f:
            f.write(f"endret={'true' if endret else 'false'}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
