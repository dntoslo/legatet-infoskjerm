# Infoskjerm: hyttene i DNT Oslo og Omegn

Nettside for infoskjerm i tre sider. Side 1 (`betjente.html`) viser om foreningens betjente hytter er betjent, selvbetjent eller stengt i dag, og når det endrer seg. Side 2 (`selvbetjente.html`) viser de selvbetjente hyttene. Side 3 (`oslomarka.html`) viser alle hyttene i Oslomarka og langs Oslofjorden, ubetjente og betjente sammen, med sengetall og nøkkeltype, på et kart zoomet inn på Oslo-området. På side 1 og 2 står et enkelt kart av Sør-Norge i midten med fjellområdene fylt i farge og hyttene som prikker, på side 3 et kart over Oslomarka og indre Oslofjord med delområdene i farge. Områdekortene står i to kolonner rundt med en strek til området sitt. Sidene er laget for en liggende TV (16:9) og viser alt på én skjerm uten scrolling. TV-en bytter mellom sidene med en spilleliste i MagicInfo. Hovedsiden (`index.html`) er bare en enkel navigasjon til de tre sidene, for dem som åpner adressen i en vanlig nettleser.

Adresser:

- Hovedside med lenker til alle: https://dntoslo.github.io/legatet-infoskjerm/
- Side 1, betjente hytter: https://dntoslo.github.io/legatet-infoskjerm/betjente.html
- Side 2, selvbetjente hytter: https://dntoslo.github.io/legatet-infoskjerm/selvbetjente.html
- Side 3, Oslomarka og Oslofjorden: https://dntoslo.github.io/legatet-infoskjerm/oslomarka.html

Spillelista i MagicInfo skal peke rett på de tre hyttesidene, ikke på hovedsiden.

## Slik virker det

- `scripts/hent_data.py` henter alle publiserte hytter til DNT Oslo og Omegn (eier 156 på ut.no) i én spørring, velger de betjente, selvbetjente og ubetjente etter reglene i `hytter.json`, og skriver `data.json` med åpningsperioder, nøkkeltype, koordinater og sengetall.
- GitHub Action (`.github/workflows/oppdater.yml`) kjører scriptet klokka 06:30 og 12:00 norsk tid og publiserer sidene til GitHub Pages. `data.json` committes til repoet bare når selve hyttedataene er endret, men de publiserte sidene får alltid ferskt tidsstempel. Action kjører også ved hver push til `main`.
- De tre hyttesidene bruker samme `assets/app.js` og `assets/style.css`. `data-side` på `<body>` velger konfigurasjonen i `SIDER` i `app.js`, som velger hytter fra `data.json` (side 1 og 2 på `serviceLevel`, side 3 på området), regner ut status for dagens dato i norsk tid, tegner ett kort per område (side 3: per delområde) og kartet i midten. Tidspunktet for siste henting vises nederst til høyre. Er dataene eldre enn 36 timer, blir teksten rød.
- Side 2 viser alle hyttenavn i to spalter per kort med statusprikk, en teller i overskriften («10 hytter · 8 åpne») og en kort dato bak stengte hytter («til 15. feb.», i rødt som «om 3 dager» når det er innen 14 dager). Åpne hytter er grønne på side 2 og 3, siden selvbetjent og ubetjent er den normale tilstanden der. Oransje brukes bare på side 1, om selvbetjeningsperioder ved betjente hytter. Kortvarianten per side står som `kort` i `SIDER`. Nederst på side 2 står en merknad om at selvbetjeningskvarter ved betjente hytter ikke er med.
- Side 3 bruker listevarianten fra side 2 og viser sengetall bak navnet («Fuglemyrhytta · 10 senger»), «Betjent» for de tre betjente hyttene i området (Kobberhaughytta, Sæteren Gård og Breivoll Gård, som også står på side 1) og en hengelås for hytter som ikke åpnes med DNT-nøkkel (lukket for egen nøkkel, åpen for ulåst, fra feltet `key` på perioden på ut.no, se `docs/utno-graphql.md`). Hengelås og ikke nøkkel med hensikt, så det ikke forveksles med DNT-nøkkelen, som ikke har noe ikon. Navnet vises alltid helt, det er tilleggsteksten som må være kort, derfor står de betjente uten sengetall. Nesten alle ubetjente er åpne hele året, bare Langøyene stenger om vinteren. De få ubetjente hyttene på fjellet kommer med i `data.json`, men ingen side viser dem.
- Kartgrunnlagene ligger i `assets/sor-norge.json` (side 1 og 2) og `assets/oslomarka.json` (side 3) og lages av `scripts/lag_kart.py`, se under.
- Sidene laster seg selv på nytt hver 30. minutt, i tillegg til at TV-en refresher.
- Innholdet ligger i en fast 16:9-flate som sentreres i vinduet, så siden ser lik ut på TV, i et smalt vindu og i et stående vindu.
- Hovedsiden `index.html` bruker ikke `app.js` eller `style.css`. Den har egen, enkel stil med samme font og farger, så den også er lesbar på telefon.

Endrer du `assets/style.css` eller `assets/app.js`, bump versjonsnummeret (`?v=7`) i lenkene i `betjente.html`, `selvbetjente.html` og `oslomarka.html`, slik at TV-en ikke fortsetter med gammel fil fra cache. Tallet skal være likt i alle tre filene.

Statusen regnes ut på TV-en, ikke i scriptet, slik at en hytte som åpner eller stenger ved midnatt vises riktig selv om dataene ble hentet kvelden før. Endringer som er 14 dager eller færre unna vises i rødt som «om N dager», ellers som dato.

## Kartene

Kartene tegnes som SVG i nettleseren fra `assets/sor-norge.json` (side 1 og 2) og `assets/oslomarka.json` (side 3). Begge filene har samme form og inneholder alt i lon/lat: landomriss, DNT-områder per kort, innsjøer, elver og byer.

Sør-Norge:

- Landomrisset, de største innsjøene (Mjøsa, Femunden, Tyrifjorden, Øyeren), Glomma og fem byer med navn, fra Natural Earth 1:10m (public domain).
- Fjellområdene, hentet som DNT-områder fra ut.no og klippet mot landomrisset. Hvilke ut.no-områder som tegnes for hvert kort, står i `polygon` under området i `omrader` i `hytter.json`.

Oslomarka:

- Kyst med øyer, innsjøer over 1 km² og de bredeste elveflatene fra Kartverkets N250 Kartdata (CC BY 4.0), lest som GML per fylke fra Geonorge. Land lages som utsnittet minus sjøflaten, det er det som gir øyene i Oslofjorden. Sjøen fylles i samme blå som innsjøene (`hav` i kartfila) og kystlinja tegnes ikke som strek, fargen skiller land fra vann. På Sør-Norge-kartet er sjøen bakgrunnsfargen, og der tegnes grensa som strek. Natural Earth er for grov så tett inn, og Kartverkets kommunegrenser går ut i sjøen og har ingen kystlinje. Zip-filene, ca. 70 MB til sammen, caches i mappa `legatet-kart` under systemets temp-mappe.
- Byer og tettsteder fra Kartverkets stedsnavn-API.
- Delområdene, hentet som DNT-områder fra ut.no etter `polygon` under `delomrader` i `hytter.json`. ut.no-polygonene deler ikke grense, så naboer nærmere hverandre enn 3 km (`tett_m` i scriptet) vokser inn i glipa til de møtes på midten, og kartet blir et lappeteppe med den tynne hvite streken som skille. Hadeland og Akershus Øst tegnes ikke, de er store og strekker seg langt utenfor utsnittet, så de to Vikkeli-hyttene og Evjenhytta får prikk like utenfor fargeflaten.

Filene lages med

```bash
uv run --with shapely scripts/lag_kart.py sor-norge
uv run --with shapely --with pyproj scripts/lag_kart.py oslomarka
```

og kjøres bare når et kart skal endres, ikke av Action. Utsnitt, forenklingsgrad, hvilke fylker som leses og hvilke innsjøer, elver og byer som er med, står i `KART` øverst i scriptet. Filene hentes uten cache i `app.js`, så et nytt kart når TV-en uten at `?v=` bumpes.

I `assets/app.js` styrer `SIDER` hvilken kolonne hvert område står i på hver side, og `FARGER` fargen per område og delområde. Et område uten farge (Oslomarka og Oslofjorden på side 1, Oslofjorden på side 3) tegnes ikke på kartet, og streken går til hyttene i stedet. Områder uten hytter på en side tegnes ikke på den siden, så side 1 er uten Østerdalsfjella og side 2 uten Oslomarka. På side 3 står Nordmarka over Krokskogen til venstre og Oslofjorden over Østmarka til høyre, ellers krysser strekene hverandre eller går tvers gjennom Østmarka.

## Hvilke hytter som vises

Hyttene hentes fra ut.no, ikke fra en liste i repoet. Scriptet tar med alle publiserte hytter til eier 156 med `serviceLevel` STAFFED (side 1), SELF_SERVICE (side 2) og NO_SERVICE (side 3, sammen med de betjente i området). Nye hytter på ut.no dukker opp av seg selv ved neste kjøring, og Action-loggen sier fra med MERK-linjer når antallet endrer seg, så layouten kan sjekkes.

`hytter.json` inneholder reglene:

- `omrader`: visningsområdene i den rekkefølgen kartet tegner dem. Hvert område har `polygon` (ut.no-område-ID-er som tegnes på kartet) og `grupper` (ut.no-område-ID med navn, alle ut.no-områdene som samles under dette kortet). Hallingdal samles for eksempel under Skarvheimen, og Rondane, Dovrefjell og Lillehammer-Rondane under «Rondane og Dovrefjell». Hver ID kan bare stå ett sted i fila. Alvdal Vestfjell står bare i `grupper` under Østerdalsfjella, ikke i `polygon`, fordi det ligger inni Østerdalsfjella og ville gitt en hvit ring i fyllet.
- `delomrader`: under et område, kortene på side 3. Hvert delområde har `polygon` og `grupper` som et område. En ut.no-ID står enten i `grupper` under området selv (paraplyen Oslomarka, som bare sier at hytta hører til området) eller under ett delområde. Hytter i området får `delomrade` i `data.json`. Ligger en hytte i null eller flere delområder, feiler scriptet på samme måte som for områder (Nydalen-hyttene ligger i både Lillomarka og Nordmarka på ut.no og har `overstyr`). Små delområder er slått sammen til ett kort: Vestmarka og Kjekstadmarka, Romeriksåsene og Hadeland, Østmarka med Akershus Øst.
- `overstyr`: per ut.no-ID, `navn` for et kortere visningsnavn («Aurlandsdalen Turisthytte Østerbø» vises som Aurlandsdalen, «Uglebu - Sæteren Gård» som Uglebu), `omrade` når hytta ligger i flere visningsområder på ut.no (Finsehytta ligger i både Skarvheimen og Hardangervidda og vises under Hardangervidda, Ellefsplass og Narjordet ligger i både Femundsmarka og Østerdalsfjella og vises under Femundsmarka) og `delomrade` tilsvarende for delområder. `navnUtno` ved siden av `navn` sier hva ut.no kalte hytta da overstyringen ble lagt inn. Endrer ut.no navnet, varsler scriptet, så noen kan vurdere om overstyringen fortsatt trengs.
- `utelat`: `navnMonster` og `ider`. Selvbetjeningskvarter ved betjente hytter fører ut.no som egne hytter med «Selvbetjent» i navnet. De utelates fordi hovedhytta på side 1 viser overgangen til selvbetjening selv.

Ligger en hytte i to visningsområder, eller i et ut.no-område som ikke står i `grupper`, feiler scriptet med en melding som sier hvilken hytte og hvilke områder det gjelder, og `data.json` røres ikke. Det er med hensikt: noen må bestemme hvor hytta skal stå, i `overstyr` eller `grupper`. Alle slike feil rapporteres i samme kjøring.

Layouten er laget for åtte områder per side, fire i hver kolonne. Venstre kolonne er nesten full på alle sidene (16 betjente, 30 selvbetjente og 28 av de 53 hyttene på side 3). Kommer det flere hytter, må skriften i kortene ned eller et område flyttes til den andre kolonnen i `SIDER`. Sjekk at ingen `.kolonne` har `scrollHeight` større enn `clientHeight` ved 1920 x 1080, og på side 3 at ingen `.hytte` har `scrollWidth` større enn `clientWidth`, siden navnene der ikke skal kuttes.

### Nytt område

1. Legg området i `omrader` i `hytter.json` med `polygon` og `grupper`, eller et nytt delområde i `delomrader` under Oslomarka og Oslofjorden. ut.no-ID-en for et DNT-område finnes med `cabin(id) { areas { id name areaType } }` på en av hyttene, se `docs/utno-graphql.md`.
2. Gi det en farge i `FARGER` og en plass i `kolonner` under hver side det skal vises på i `SIDER`, i `assets/app.js`. Fargen må skille seg klart fra naboområdene på kartet. Rekkefølgen i kolonnen skal følge nord til sør, ellers krysser strekene fra kortene hverandre. Sjekk ved 1920 x 1080 at ingen `.streker line` krysser en annen.
3. Kjør `scripts/lag_kart.py` på nytt for kartet det gjelder og commit `assets/sor-norge.json` eller `assets/oslomarka.json`.
4. Bump `?v=` i de tre HTML-filene.

## Kjøre lokalt

Scriptet trenger bare Python 3 uten pakker:

```bash
python scripts/hent_data.py
python -m http.server 8765
```

Åpne deretter http://localhost:8765/betjente.html, http://localhost:8765/selvbetjente.html og http://localhost:8765/oslomarka.html i en nettleser, eller http://localhost:8765/ for hovedsiden med lenker til alle. Sidene må serveres over http fordi de henter `data.json` og kartfilene med `fetch`.

## Kjøre Action manuelt

```bash
gh workflow run oppdater.yml
```

Eller Actions-fanen på GitHub, «Oppdater åpningstider og publiser», «Run workflow».

## Datakilde

ut.no sitt GraphQL-endepunkt, det samme som nettsiden ut.no bruker. Det er ikke dokumentert offentlig og kan endres uten varsel. Begynner scriptet å feile, se `docs/utno-graphql.md` for feltene og hvordan skjemaet undersøkes på nytt. Åpningsperiodene legges inn av foreningen selv på ut.no, så feil på skjermen rettes der.

## Visuell profil

Farger og logo følger DNTs visuelle identitet. Fonten ABC Social ligger i `assets/fonts/` og er lisensiert til DNT.
