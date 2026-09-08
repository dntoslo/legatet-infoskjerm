# Infoskjerm: betjente hytter i DNT Oslo og Omegn

Nettside for infoskjerm som viser om foreningens betjente hytter er betjent, selvbetjent eller stengt i dag, og når det endrer seg. Siden er laget for en liggende TV (16:9) og viser alle hyttene på én skjerm uten scrolling.

Adresse: https://dntoslo.github.io/legatet-infoskjerm/

## Slik virker det

- `scripts/hent_data.py` henter åpningsperiodene for hyttene i `hytter.json` fra ut.no og skriver `data.json`.
- GitHub Action (`.github/workflows/oppdater.yml`) kjører scriptet klokka 06:30 og 12:00 norsk tid og publiserer siden til GitHub Pages. `data.json` committes til repoet bare når selve hyttedataene er endret, men den publiserte siden får alltid ferskt tidsstempel. Action kjører også ved hver push til `main`.
- `index.html` med `assets/app.js` leser `data.json`, regner ut status for dagens dato i norsk tid og tegner ett kort per fjellområde. Tidspunktet for siste henting vises nederst til høyre. Er dataene eldre enn 36 timer, blir teksten rød.
- Siden laster seg selv på nytt hver 30. minutt, i tillegg til at TV-en refresher.
- Innholdet ligger i en fast 16:9-flate som sentreres i vinduet, så siden ser lik ut på TV, i et smalt vindu og i et stående vindu.

Endrer du `assets/style.css` eller `assets/app.js`, bump versjonsnummeret (`?v=2`) i lenkene i `index.html`, slik at TV-en ikke fortsetter med gammel fil fra cache.

Statusen regnes ut på TV-en, ikke i scriptet, slik at en hytte som åpner eller stenger ved midnatt vises riktig selv om dataene ble hentet kvelden før.

## Kartvisning (under utprøving)

`kart.html` viser det samme innholdet med et enkelt kart av Sør-Norge i midten og områdekortene i to kolonner rundt. Hvert fjellområde er fylt med en farge som går igjen på kortet, en strek binder kort og område sammen, og hyttene er prikker farget etter dagens status. De største innsjøene, Glomma og noen byer er med for gjenkjenning. Adresse når branchen er publisert: `.../legatet-infoskjerm/kart.html`.

- `assets/kart.js` overtar tegningen fra `app.js` gjennom `window.infoskjermTegn` og gjenbruker statuslogikken og kortene derfra. Hvilken kolonne et område står i, styres av `KOLONNER` øverst i fila.
- Koordinatene til hyttene hentes fra ut.no av `hent_data.py` og ligger som `lon` og `lat` i `data.json`.
- Kartgrunnlaget ligger i `assets/sor-norge.json` og lages av `scripts/lag_kart.py` med `uv run --with shapely scripts/lag_kart.py`. Landomriss, innsjøer, elver og byer kommer fra Natural Earth (public domain). Fjellområdene er DNT-områdene på ut.no. Hvilke ut.no-områder som hører til hvert kort, står i `utnoOmrader` i `hytter.json`, så et nytt område trenger både en linje der og en ny kjøring av scriptet. Utsnitt, forenklingsgrad og hvilke innsjøer, elver og byer som er med, står øverst i scriptet.

## Legge til eller fjerne en hytte

Rediger `hytter.json`. Hver hytte har ut.no-ID, visningsnavn og område:

```json
{ "id": 10604, "navn": "Gjendesheim", "omrade": "Jotunheimen" }
```

ID-en står i adressen på ut.no, for eksempel `https://ut.no/hytte/10604/gjendesheim`. Området må finnes i listen `omrader` øverst i fila, og rekkefølgen der styrer rekkefølgen på skjermen. Layouten er laget for seks områder i et rutenett på 3 x 2.

Push til `main`, så henter Action nye data og publiserer.

## Kjøre lokalt

Scriptet trenger bare Python 3 uten pakker:

```bash
python scripts/hent_data.py
python -m http.server 8765
```

Åpne deretter http://localhost:8765/ i en nettleser. Siden må serveres over http fordi den henter `data.json` med `fetch`.

## Kjøre Action manuelt

```bash
gh workflow run oppdater.yml
```

Eller Actions-fanen på GitHub, «Oppdater åpningstider og publiser», «Run workflow».

## Datakilde

ut.no sitt GraphQL-endepunkt, det samme som nettsiden ut.no bruker. Det er ikke dokumentert offentlig og kan endres uten varsel. Begynner scriptet å feile, se `docs/utno-graphql.md` for feltene og hvordan skjemaet undersøkes på nytt. Åpningsperiodene legges inn av foreningen selv på ut.no, så feil på skjermen rettes der.

## Visuell profil

Farger og logo følger DNTs visuelle identitet. Fonten ABC Social ligger i `assets/fonts/` og er lisensiert til DNT.
