---
name: utno-hytte
description: Henter ferske data om DNT-hytter fra ut.no med et bundlet script: åpningstider og sesong, sengeplasser, servicenivå (betjent, selvbetjent, ubetjent), kommune, fylke, fjellområde, koordinater og høyde, adkomst sommer og vinter, telefon, e-post og bookinglenke. Lister også alle hyttene til DNT Oslo og Omegn per servicenivå. Bruk denne skillen hver gang noen spør om en hytte eller "hytta", når den åpner eller stenger, hvor mange senger den har, hvor den ligger, hvordan man kommer seg dit, telefon eller e-post til hytta, eller lister som "hvilke selvbetjente hytter har vi", "alle hyttene våre i Oslomarka" og "hvor mange betjente hytter har foreningen". Bruk den også når brukeren bare skriver et hyttenavn (Gjendesheim, Fondsbu, Kobberhaughytta, Olavsbu, Fuglemyrhytta, Sæteren Gård) eller limer inn en ut.no-lenke, selv om DNT ikke nevnes. Skal ikke brukes for turforslag, ruter eller vær, og ikke for prisspørsmål, som ligger på dnt.no.
---

# Hytteoppslag på ut.no

Scriptet `scripts/hytte.py` i denne skillens mappe spør ut.no sitt eget GraphQL-endepunkt og skriver ferdig formatert markdown. Det trenger bare Python 3 uten pakker, og nettverkstilgang til `ut.no`. Bruk scriptet i stedet for å lese nettsiden, for siden viser ikke koordinater, kommune eller dagens status, og teksten der er tyngre å tolke riktig.

## Slik gjør du

1. Kjør scriptet med det brukeren oppga, enten ID, ut.no-lenke eller navn:

   ```bash
   python scripts/hytte.py Gjendesheim
   python scripts/hytte.py https://ut.no/hytte/10604/gjendesheim
   python scripts/hytte.py --liste selvbetjent
   ```

   `--liste` uten nivå gir alle hyttene til DNT Oslo og Omegn gruppert per servicenivå. `--json` gir rådata når du trenger å regne på noe eller sammenligne flere hytter.

2. Svar på det brukeren faktisk spurte om. Scriptet skriver alt det vet, men brukeren som lurer på når Glitterheim åpner trenger ikke fasilitetslisten. Ta med sengeplasser og kontaktinfo bare når det er relevant.

3. Avslutt med kilde og dato, som scriptet skriver på siste linje. Åpningstider og sengetall endres, og den som bruker svaret i en e-post eller på nett skal kunne se hvor gammelt det er og sjekke selv.

4. Feiler scriptet, si det rett ut og gi lenken til hytta på ut.no. Ikke gjett på åpningstider fra hukommelsen, og ikke prøv å lese nettsiden i stedet, den gir dårligere data. Feiler det med nettverksfeil i claude.ai, er den vanlige årsaken at `ut.no` mangler i allowlisten for code execution, nevn det.

## Flere treff på navn

Scriptet velger selv når et navn gir ett treff, når ett treff heter nøyaktig det brukeren skrev, eller når bare ett av treffene eies av DNT Oslo og Omegn. Ellers skriver det kandidatene til stderr og avslutter med kode 2. Vis da kandidatene og spør brukeren, i stedet for å velge selv. Navnemønstre på ut.no som ofte gir flere treff:

- Selvbetjeningskvarteret ved en betjent hytte er egen oppføring, for eksempel «Gjendebu Selvbetjent» ved siden av «Gjendebu».
- Sæteren Gård er splittet i «Sæteren Gård - Hovedhus+Sovehus» og småhyttene «Elgstua - Sæteren Gård», «Knoll - Sæteren Gård» og flere.
- Noen navn har tillegg, som «Aurlandsdalen Turisthytte Østerbø» og «Leirvassbu Turisthytte».
- Andre foreninger har hytter med like navn, for eksempel finnes både «Olavsbu» i Jotunheimen og «Olavsbu - Hornelen».

Skillen virker for alle hytter på ut.no, ikke bare foreningens egne.

## Slik leser du dataene

- Servicenivå kommer fra ut.no sin enum: betjent, selvbetjent, ubetjent, ubetjent uten senger, servering, nødbu, stengt, utleie, ukjent. Scriptet oversetter til norsk.
- Åpningstider er perioder foreningen selv legger inn på ut.no, med servicenivå og sengetall per periode. Perioden som gjelder i dag er markert med «(nå)». Hytter som er åpne hele året har ingen datoer. Datoene kan avvike fra det som står på hyttas egen nettside eller i bookingsystemet, så ved tvil om en konkret dato, anbefal å sjekke med hytta.
- Sengetall ligger per servicenivå. Vintersenger er ofte 0 selv om hytta har vinteråpent, fordi feltet brukes lite. Bruk sengetallet i perioden som gjelder når spørsmålet er om et bestemt tidspunkt.
- Koordinater er WGS84 med høyde fra ut.no sin kartdata, ikke nødvendigvis hyttas offisielle høyde.
- Adkomsttekstene er skrevet av foreningen og kan være lange. Kort dem ned til det brukeren trenger.

Scriptet henter bare felt som er offentlige på ut.no. Interne notater og brukerdata finnes i skjemaet, men hentes ikke.

## Kilde

Endepunktet er udokumentert og kan endres uten varsel. Skjemaet ble kartlagt 7. september 2026, se `references/graphql.md` for spørringene, feltene og hvordan man undersøker skjemaet på nytt hvis scriptet begynner å feile. Denne skillen er en midlertidig løsning frem til en MCP-server mot ut.no er på plass.
