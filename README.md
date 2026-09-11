# Infoskjerm: hyttene i DNT Oslo og Omegn

Nettside for infoskjerm i to sider. Side 1 viser om foreningens betjente hytter er betjent, selvbetjent eller stengt i dag, og når det endrer seg. Side 2 viser de selvbetjente hyttene. Et enkelt kart av Sør-Norge står i midten med fjellområdene fylt i farge og hyttene som prikker, og områdekortene står i to kolonner rundt med en strek til området sitt. Sidene er laget for en liggende TV (16:9) og viser alt på én skjerm uten scrolling. TV-en bytter mellom sidene med en spilleliste i MagicInfo.

Adresser:

- Side 1, betjente hytter: https://dntoslo.github.io/legatet-infoskjerm/
- Side 2, selvbetjente hytter: https://dntoslo.github.io/legatet-infoskjerm/selvbetjente.html

## Slik virker det

- `scripts/hent_data.py` henter alle publiserte hytter til DNT Oslo og Omegn (eier 156 på ut.no) i én spørring, velger de betjente og selvbetjente etter reglene i `hytter.json`, og skriver `data.json` med åpningsperioder, koordinater og sengetall.
- GitHub Action (`.github/workflows/oppdater.yml`) kjører scriptet klokka 06:30 og 12:00 norsk tid og publiserer sidene til GitHub Pages. `data.json` committes til repoet bare når selve hyttedataene er endret, men de publiserte sidene får alltid ferskt tidsstempel. Action kjører også ved hver push til `main`.
- `index.html` og `selvbetjente.html` bruker samme `assets/app.js` og `assets/style.css`. `data-side` på `<body>` velger konfigurasjonen i `SIDER` i `app.js`, som filtrerer `data.json` på `serviceLevel`, regner ut status for dagens dato i norsk tid, tegner ett kort per fjellområde og kartet i midten. Tidspunktet for siste henting vises nederst til høyre. Er dataene eldre enn 36 timer, blir teksten rød.
- Side 2 viser alle hyttenavn i to spalter per kort med statusprikk, en teller i overskriften («10 hytter · 8 åpne») og en kort dato bak stengte hytter («til 15. feb.», i rødt som «om 3 dager» når det er innen 14 dager). Åpne hytter er grønne på side 2, siden selvbetjent er den normale tilstanden der. Oransje brukes bare på side 1, om selvbetjeningsperioder ved betjente hytter. Kortvarianten per side står som `kort` i `SIDER`. Nederst på side 2 står en merknad om at selvbetjeningskvarter ved betjente hytter ikke er med.
- Kartgrunnlaget ligger i `assets/sor-norge.json` og lages av `scripts/lag_kart.py`, se under.
- Sidene laster seg selv på nytt hver 30. minutt, i tillegg til at TV-en refresher.
- Innholdet ligger i en fast 16:9-flate som sentreres i vinduet, så siden ser lik ut på TV, i et smalt vindu og i et stående vindu.

Endrer du `assets/style.css` eller `assets/app.js`, bump versjonsnummeret (`?v=6`) i lenkene i både `index.html` og `selvbetjente.html`, slik at TV-en ikke fortsetter med gammel fil fra cache. Tallet skal være likt i begge filene.

Statusen regnes ut på TV-en, ikke i scriptet, slik at en hytte som åpner eller stenger ved midnatt vises riktig selv om dataene ble hentet kvelden før. Endringer som er 14 dager eller færre unna vises i rødt som «om N dager», ellers som dato.

## Kartet

Kartet tegnes som SVG i nettleseren fra `assets/sor-norge.json`, som inneholder alt i lon/lat:

- Landomrisset av Sør-Norge, de største innsjøene (Mjøsa, Femunden, Tyrifjorden, Øyeren), Glomma og fem byer med navn, fra Natural Earth 1:10m (public domain).
- Fjellområdene, hentet som DNT-områder fra ut.no og klippet mot landomrisset. Hvilke ut.no-områder som tegnes for hvert kort, står i `polygon` under området i `omrader` i `hytter.json`.

Fila lages med

```bash
uv run --with shapely scripts/lag_kart.py
```

og kjøres bare når kartet skal endres, ikke av Action. Utsnitt, forenklingsgrad og hvilke innsjøer, elver og byer som er med, står øverst i scriptet. Fila hentes uten cache i `app.js`, så et nytt kart når TV-en uten at `?v=` bumpes.

I `assets/app.js` styrer `SIDER` hvilken kolonne hvert område står i på hver side, og `FARGER` fargen per område. Et område uten farge (Oslomarka og Oslofjorden) tegnes ikke på kartet, og streken går til hyttene i stedet. Områder uten hytter på en side tegnes ikke på den siden, så side 1 er uten Østerdalsfjella og side 2 uten Oslomarka.

## Hvilke hytter som vises

Hyttene hentes fra ut.no, ikke fra en liste i repoet. Scriptet tar med alle publiserte hytter til eier 156 med `serviceLevel` STAFFED (side 1) og SELF_SERVICE (side 2). Nye hytter på ut.no dukker opp av seg selv ved neste kjøring, og Action-loggen sier fra med MERK-linjer når antallet endrer seg, så layouten kan sjekkes.

`hytter.json` inneholder reglene:

- `omrader`: visningsområdene i den rekkefølgen kartet tegner dem. Hvert område har `polygon` (ut.no-område-ID-er som tegnes på kartet) og `grupper` (ut.no-område-ID med navn, alle ut.no-områdene som samles under dette kortet). Hallingdal samles for eksempel under Skarvheimen, og Rondane, Dovrefjell og Lillehammer-Rondane under «Rondane og Dovrefjell». Hver ID kan bare stå under ett område.
- `overstyr`: per ut.no-ID, `navn` for et kortere visningsnavn («Aurlandsdalen Turisthytte Østerbø» vises som Aurlandsdalen) og `omrade` når hytta ligger i flere visningsområder på ut.no (Finsehytta ligger i både Skarvheimen og Hardangervidda og vises under Hardangervidda). `navnUtno` ved siden av `navn` sier hva ut.no kalte hytta da overstyringen ble lagt inn. Endrer ut.no navnet, varsler scriptet, så noen kan vurdere om overstyringen fortsatt trengs.
- `utelat`: `navnMonster` og `ider`. Selvbetjeningskvarter ved betjente hytter fører ut.no som egne hytter med «Selvbetjent» i navnet. De utelates fordi hovedhytta på side 1 viser overgangen til selvbetjening selv.

Ligger en hytte i to visningsområder, eller i et ut.no-område som ikke står i `grupper`, feiler scriptet med en melding som sier hvilken hytte og hvilke områder det gjelder, og `data.json` røres ikke. Det er med hensikt: noen må bestemme hvor hytta skal stå, i `overstyr` eller `grupper`. Alle slike feil rapporteres i samme kjøring.

Layouten er laget for åtte områder per side, fire i hver kolonne. Venstre kolonne er nesten full på begge sidene (16 betjente og 30 selvbetjente hytter). Kommer det flere hytter, må skriften i kortene ned eller et område flyttes til den andre kolonnen i `SIDER`. Sjekk at ingen `.kolonne` har `scrollHeight` større enn `clientHeight` ved 1920 x 1080.

### Nytt område

1. Legg området i `omrader` i `hytter.json` med `polygon` og `grupper`. ut.no-ID-en for et DNT-område finnes med `cabin(id) { areas { id name areaType } }` på en av hyttene, se `docs/utno-graphql.md`.
2. Gi det en farge i `FARGER` og en plass i `kolonner` under hver side det skal vises på i `SIDER`, i `assets/app.js`. Fargen må skille seg klart fra naboområdene på kartet. Rekkefølgen i kolonnen skal følge nord til sør, ellers krysser strekene fra kortene hverandre. Sjekk ved 1920 x 1080 at ingen `.streker line` krysser en annen.
3. Kjør `scripts/lag_kart.py` på nytt og commit `assets/sor-norge.json`.
4. Bump `?v=` i begge HTML-filene.

## Kjøre lokalt

Scriptet trenger bare Python 3 uten pakker:

```bash
python scripts/hent_data.py
python -m http.server 8765
```

Åpne deretter http://localhost:8765/ og http://localhost:8765/selvbetjente.html i en nettleser. Sidene må serveres over http fordi de henter `data.json` og `assets/sor-norge.json` med `fetch`.

## Kjøre Action manuelt

```bash
gh workflow run oppdater.yml
```

Eller Actions-fanen på GitHub, «Oppdater åpningstider og publiser», «Run workflow».

## Datakilde

ut.no sitt GraphQL-endepunkt, det samme som nettsiden ut.no bruker. Det er ikke dokumentert offentlig og kan endres uten varsel. Begynner scriptet å feile, se `docs/utno-graphql.md` for feltene og hvordan skjemaet undersøkes på nytt. Åpningsperiodene legges inn av foreningen selv på ut.no, så feil på skjermen rettes der.

## Visuell profil

Farger og logo følger DNTs visuelle identitet. Fonten ABC Social ligger i `assets/fonts/` og er lisensiert til DNT.
