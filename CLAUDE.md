# legatet-infoskjerm

Infoskjerm for DNT Oslo og Omegns betjente hytter, publisert på GitHub Pages fra dette repoet. Statisk side uten byggesteg, et Python-script som henter åpningsperioder fra ut.no, og en GitHub Action som kjører scriptet og deployer. Hvordan det henger sammen står i README.md.

## Ting som ikke er synlige i koden

- `data.json` er generert. Kjører du scriptet lokalt, endres bare tidsstempelet `hentet`, og det skal ikke committes. Nullstill fila med `git checkout -- data.json` før commit. Action committer den selv når hyttedataene faktisk er endret.
- Action pusher til `main`. Etter at du har pushet, er lokal `main` ofte bak. Ta `git pull --rebase` før neste push.
- Status for i dag regnes ut i `assets/app.js`, ikke i scriptet. Det er med hensikt: data hentes to ganger om dagen, men TV-en refresher oftere, og en hytte som åpner ved midnatt skal vises riktig uten ny henting. Flytt ikke logikken til scriptet.
- ut.no lar to perioder dele grensedato (betjent til 4. okt, stengt fra 4. okt). `til` behandles derfor som eksklusiv i statuslogikken.
- Endrer du `assets/style.css` eller `assets/app.js`, bump `?v=` i lenkene i `index.html`. GitHub Pages cacher filene, og TV-en viser ellers gammel versjon lenge etter deploy.
- Layouten er to kolonner med fire områdekort hver og kartet i midten, og alt skal få plass på én 16:9-skjerm uten scrolling. Venstre kolonne er nesten full. Legger du til et område eller flere hytter, må skriften i kortene ned eller `KOLONNER` i `app.js` balanseres om. Sjekk at ingen `.kort ul` har `scrollHeight` større enn `clientHeight` ved 1920 x 1080.
- Kortene har høyde etter innholdet med hensikt, så avstanden mellom radene er lik i alle kort. Ledig plass legges mellom kortene. Ikke la kortene vokse for å fylle kolonnen, det ga ujevne rader.
- Områdefargene i `FARGER` er bundet til navn, ikke rekkefølge, og er valgt for å skille naboområder og for å ikke kollidere med statusfargene grønn, oransje og rød. Oslomarka og Oslofjorden har ingen farge med hensikt, fordi ut.no sitt Oslofjorden-område er en lang stripe langs hele fjorden.
- `assets/sor-norge.json` er generert av `scripts/lag_kart.py` fra Natural Earth og DNT-områdene på ut.no. Rediger ikke fila for hånd, endre parameterne i scriptet eller `utnoOmrader` i `hytter.json` og kjør scriptet på nytt med `uv run --with shapely`. Scriptet er ikke del av Action. Områdene klippes mot landomrisset fordi ut.no-polygonene kan gå inn i Sverige.
- Finsehytta ligger under Hardangervidda etter beslutning fra foreningen. ut.no fører den i både Hardangervidda og Skarvheimen.
- Fire cron-linjer i workflowen er med hensikt. Cron går i UTC og kjenner ikke sommertid, så to linjer per klokkeslett dekker 06:30 og 12:00 norsk tid året rundt.
- Scriptet bruker bare standardbiblioteket, slik at Action ikke trenger installasjon. Windows-Python mangler ofte tzdata, derfor har `naa_oslo()` en manuell fallback for norsk tid. Ikke legg inn avhengigheter for å forenkle dette.
- Fonten ABC Social ligger i repoet etter beslutning fra foreningen, som eier lisensen. Den skal ikke byttes ut eller fjernes som opprydding.
- Repoet og siden er offentlige. `data.json` skal bare inneholde det som allerede er offentlig på ut.no. Koordinatene til hyttene er offentlige der.

## Datakilde

ut.no sitt GraphQL-endepunkt er udokumentert og kan endres uten varsel. Feiler scriptet med GraphQL-feil, se `docs/utno-graphql.md` for feltene og hvordan skjemaet undersøkes på nytt. Der står også hvordan ut.no-ID-en for et DNT-område finnes.
