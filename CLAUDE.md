# legatet-infoskjerm

Infoskjerm for hyttene i DNT Oslo og Omegn på GitHub Pages: to statiske sider uten byggesteg, et Python-script som henter data fra ut.no og en Action som kjører scriptet og deployer. Hvordan det henger sammen, og hvordan hytteutvalg og kart styres, står i README.md. Kodefilene har hver sin innledning med det som gjelder der.

## Gotchas

- `data.json` er generert. Kjører du scriptet lokalt, endres bare tidsstempelet `hentet`. Nullstill med `git checkout -- data.json` før commit, Action committer selv når hyttedataene faktisk er endret.
- Action pusher til `main`, så lokal `main` er ofte bak etter deploy. Ta `git pull --rebase` før neste push.
- Endrer du `assets/style.css` eller `assets/app.js`, bump `?v=` i både `betjente.html` og `selvbetjente.html`, samme tall. GitHub Pages cacher, og TV-en viser ellers gammel versjon lenge. `data.json` og `assets/sor-norge.json` hentes uten cache og trenger ikke bump.
- Skjermen kjører Chromium 94 (Samsung QM75C, Tizen 7.0). CSS den ikke kjenner forkastes stille og layouten kollapser, uten at lokal nettleser viser noe. Sjekk caniuse før du tar i bruk nyere CSS eller JS, og legg en enkel fallback foran i kaskaden. rem-konvensjonen står øverst i `style.css`.
- Alt skal få plass på én 16:9-skjerm uten scrolling, og venstre kolonne er nesten full på begge sidene. Etter layoutendringer, sjekk ved 1920 x 1080 at ingen `.kolonne` har `scrollHeight` over `clientHeight`, og at ingen `.streker line` krysser hverandre.
- `assets/sor-norge.json` er generert av `scripts/lag_kart.py`. Rediger ikke fila for hånd, endre scriptet eller `polygon` i `hytter.json` og kjør på nytt.
- Fonten ABC Social ligger i repoet etter beslutning fra foreningen, som eier lisensen. Fjern eller bytt den ikke som opprydding.
- Repoet og siden er offentlige. `data.json` skal bare inneholde det som allerede er offentlig på ut.no.
- Feiler scriptet med GraphQL-feil fra ut.no, se `docs/utno-graphql.md`.
