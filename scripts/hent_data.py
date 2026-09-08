#!/usr/bin/env python3
"""Henter åpningsperioder for hyttene i hytter.json fra ut.no og skriver data.json.

Kjøres av GitHub Action to ganger om dagen, eller manuelt:

  python scripts/hent_data.py

Kun standardbiblioteket. Feiler oppslaget for en hytte etter nytt forsøk,
avsluttes scriptet med kode 1 uten å røre data.json, slik at forrige gyldige
fil beholdes og kjøringen blir rød.
"""

import json
import os
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
TIMEOUT_SEK = 15
FORSOEK = 2
PAUSE_SEK = 2


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

Q_HYTTE = """
query($id: Int!) {
  cabin(id: $id) {
    id name serviceLevel status updatedAt
    serviceStatusAll { serviceLevel beds from to openAllYear }
  }
}
"""


class UtNoFeil(Exception):
    pass


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


def hent_hytte(hytte_id):
    siste_feil = None
    for forsoek in range(FORSOEK):
        try:
            data = gql(Q_HYTTE, {"id": hytte_id})
            cabin = data.get("cabin")
            if not cabin:
                raise UtNoFeil("ut.no har ingen hytte med denne ID-en")
            return cabin
        except UtNoFeil as e:
            siste_feil = e
            if forsoek < FORSOEK - 1:
                time.sleep(PAUSE_SEK)
    raise siste_feil


def normaliser(konfig_hytte, cabin):
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
        "navn": konfig_hytte["navn"],
        "navnUtno": cabin.get("name"),
        "omrade": konfig_hytte["omrade"],
        "utnoUrl": f"https://ut.no/hytte/{cabin['id']}",
        "serviceLevel": cabin.get("serviceLevel"),
        "oppdatertUtno": cabin.get("updatedAt"),
        "perioder": perioder,
    }


def main():
    for stroem in (sys.stdout, sys.stderr):
        if hasattr(stroem, "reconfigure"):
            stroem.reconfigure(encoding="utf-8")

    konfig = json.loads(KONFIG.read_text(encoding="utf-8"))
    hytter_ut = []
    feil = []
    for h in konfig["hytter"]:
        try:
            cabin = hent_hytte(h["id"])
        except UtNoFeil as e:
            feil.append(f"{h['navn']} ({h['id']}): {e}")
            print(f"FEIL  {h['navn']}: {e}", file=sys.stderr)
            continue
        hytter_ut.append(normaliser(h, cabin))
        print(f"OK    {h['navn']}: {len(hytter_ut[-1]['perioder'])} perioder")

    if feil:
        print(f"\n{len(feil)} av {len(konfig['hytter'])} hytter feilet. data.json er ikke endret.", file=sys.stderr)
        return 1

    # Har selve hyttedataene endret seg siden sist? Tidsstempelet «hentet»
    # endres alltid, så det holdes utenfor sammenligningen. GitHub Action
    # bruker svaret til å bare committe når noe faktisk er nytt, mens den
    # publiserte siden alltid får ferskt tidsstempel.
    endret = True
    if UTFIL.exists():
        try:
            forrige = json.loads(UTFIL.read_text(encoding="utf-8"))
            endret = forrige.get("hytter") != hytter_ut or forrige.get("omrader") != konfig["omrader"]
        except ValueError:
            endret = True

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
