# Infoskjerm: betjente hytter i DNT Oslo og Omegn

Nettside for infoskjerm som viser om foreningens betjente hytter er betjent, selvbetjent eller stengt i dag, og når det endrer seg. Et enkelt kart av Sør-Norge står i midten med fjellområdene fylt i farge og hyttene som prikker, og områdekortene står i to kolonner rundt med en strek til området sitt. Siden er laget for en liggende TV (16:9) og viser alt på én skjerm uten scrolling.

Adresse: https://dntoslo.github.io/legatet-infoskjerm/

## Slik virker det

- `scripts/hent_data.py` henter åpningsperiodene og koordinatene for hyttene i `hytter.json` fra ut.no og skriver `data.json`.
- GitHub Action (`.github/workflows/oppdater.yml`) kjører scriptet klokka 06:30 og 12:00 norsk tid og publiserer siden til GitHub Pages. `data.json` committes til repoet bare når selve hyttedataene er endret, men den publiserte siden får alltid ferskt tidsstempel. Action kjører også ved hver push til `main`.
- `index.html` med `assets/app.js` leser `data.json`, regner ut status for dagens dato i norsk tid, tegner ett kort per fjellområde og kartet i midten. Tidspunktet for siste henting vises nederst til høyre. Er dataene eldre enn 36 timer, blir teksten rød.
- Kartgrunnlaget ligger i `assets/sor-norge.json` og lages av `scripts/lag_kart.py`, se under.
- Siden laster seg selv på nytt hver 30. minutt, i tillegg til at TV-en refresher.
- Innholdet ligger i en fast 16:9-flate som sentreres i vinduet, så siden ser lik ut på TV, i et smalt vindu og i et stående vindu.

Endrer du `assets/style.css` eller `assets/app.js`, bump versjonsnummeret (`?v=5`) i lenkene i `index.html`, slik at TV-en ikke fortsetter med gammel fil fra cache.

Statusen regnes ut på TV-en, ikke i scriptet, slik at en hytte som åpner eller stenger ved midnatt vises riktig selv om dataene ble hentet kvelden før. Endringer som er 14 dager eller færre unna vises i rødt som «om N dager», ellers som dato.

## Kartet

Kartet tegnes som SVG i nettleseren fra `assets/sor-norge.json`, som inneholder alt i lon/lat:

- Landomrisset av Sør-Norge, de største innsjøene (Mjøsa, Femunden, Tyrifjorden, Øyeren), Glomma og fem byer med navn, fra Natural Earth 1:10m (public domain).
- Fjellområdene, hentet som DNT-områder fra ut.no og klippet mot landomrisset. Hvilke ut.no-områder som hører til hvert kort, står i `utnoOmrader` i `hytter.json`.

Fila lages med

```bash
uv run --with shapely scripts/lag_kart.py
```

og kjøres bare når kartet skal endres, ikke av Action. Utsnitt, forenklingsgrad og hvilke innsjøer, elver og byer som er med, står øverst i scriptet.

I `assets/app.js` styrer `KOLONNER` hvilken kolonne hvert område står i, og `FARGER` fargen per område. Et område uten farge (Oslomarka og Oslofjorden) tegnes ikke på kartet, og streken går til hyttene i stedet.

## Legge til eller fjerne en hytte

Rediger `hytter.json`. Hver hytte har ut.no-ID, visningsnavn og område:

```json
{ "id": 10604, "navn": "Gjendesheim", "omrade": "Jotunheimen" }
```

ID-en står i adressen på ut.no, for eksempel `https://ut.no/hytte/10604/gjendesheim`. Området må finnes i listen `omrader` øverst i fila. Push til `main`, så henter Action nye data og publiserer.

Layouten er laget for åtte områder, fire i hver kolonne, og venstre kolonne er nesten full med 16 hytter. Kommer det flere hytter eller områder, må skriften i kortene ned eller et område flyttes til den andre kolonnen i `KOLONNER`. Sjekk at ingen liste klippes ved 1920 x 1080.

### Nytt område

1. Legg navnet i `omrader` i `hytter.json`.
2. Finn ut.no-ID-en for DNT-området med `cabin(id) { areas { id name areaType } }` på en av hyttene, og legg den i `utnoOmrader`.
3. Legg området i `KOLONNER` og gi det en farge i `FARGER` i `assets/app.js`. Fargen må skille seg klart fra naboområdene på kartet.
4. Kjør `scripts/lag_kart.py` på nytt og commit `assets/sor-norge.json`.

## Kjøre lokalt

Scriptet trenger bare Python 3 uten pakker:

```bash
python scripts/hent_data.py
python -m http.server 8765
```

Åpne deretter http://localhost:8765/ i en nettleser. Siden må serveres over http fordi den henter `data.json` og `assets/sor-norge.json` med `fetch`.

## Kjøre Action manuelt

```bash
gh workflow run oppdater.yml
```

Eller Actions-fanen på GitHub, «Oppdater åpningstider og publiser», «Run workflow».

## Datakilde

ut.no sitt GraphQL-endepunkt, det samme som nettsiden ut.no bruker. Det er ikke dokumentert offentlig og kan endres uten varsel. Begynner scriptet å feile, se `docs/utno-graphql.md` for feltene og hvordan skjemaet undersøkes på nytt. Åpningsperiodene legges inn av foreningen selv på ut.no, så feil på skjermen rettes der.

## Visuell profil

Farger og logo følger DNTs visuelle identitet. Fonten ABC Social ligger i `assets/fonts/` og er lisensiert til DNT.
