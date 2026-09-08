# Infoskjerm: betjente hytter i DNT Oslo og Omegn

Nettside for infoskjerm som viser om foreningens betjente hytter er betjent, selvbetjent eller stengt i dag, og når det endrer seg. Siden er laget for en liggende TV (16:9) og viser alle hyttene på én skjerm uten scrolling.

Adresse: https://dntoslo.github.io/legatet-infoskjerm/

## Slik virker det

- `scripts/hent_data.py` henter åpningsperiodene for hyttene i `hytter.json` fra ut.no og skriver `data.json`.
- GitHub Action (`.github/workflows/oppdater.yml`) kjører scriptet klokka 06:30 og 12:00 norsk tid og publiserer siden til GitHub Pages. `data.json` committes til repoet bare når selve hyttedataene er endret, men den publiserte siden får alltid ferskt tidsstempel. Action kjører også ved hver push til `main`.
- `index.html` med `assets/app.js` leser `data.json`, regner ut status for dagens dato i norsk tid og tegner ett kort per fjellområde. Tidspunktet for siste henting vises nederst til høyre. Er dataene eldre enn 36 timer, blir teksten rød.
- Siden laster seg selv på nytt hver 30. minutt, i tillegg til at TV-en refresher.

Statusen regnes ut på TV-en, ikke i scriptet, slik at en hytte som åpner eller stenger ved midnatt vises riktig selv om dataene ble hentet kvelden før.

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
