# ut.no GraphQL: det scriptet bygger på

Kartlagt 7. september 2026 mot `https://ut.no/api/graphql`. Endepunktet er det nettsiden ut.no selv bruker. Det er ikke dokumentert offentlig, krever ingen autentisering for offentlige data, og tar imot vanlig `POST` med `{"query": ..., "variables": ...}` som JSON. Introspeksjon er åpen, så alt under kan verifiseres på nytt med kommandoene nederst.

## Spørringen scriptet bruker

`scripts/hent_data.py` kjører én spørring per henting: alle publiserte hytter til eieren, med perioder og områder i samme svar. Bekreftet 10. september 2026 at `serviceStatusAll` kan hentes inne i lista, så det trengs ikke ett `cabin(id:)`-kall per hytte.

```graphql
query($eier: Int!) {
  cabins(paging: {first: 500}, filter: {ownerGroupId: {eq: $eier}, status: {eq: PUBLIC}},
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
```

`paging`, `filter` og `sorting` er alle påkrevd på `cabins`, men `sorting: []` er lov. `serviceLevel: {eq: SELF_SERVICE}` og `serviceLevel: {in: [STAFFED, SELF_SERVICE]}` fungerer som serverside-filter (62 og 87 treff for eier 156), men scriptet henter alt og deler i Python siden det trenger begge nivåene og vil logge hva som utelates.

## Nyttige oppslag

Én hytte:

```graphql
query($id: Int!) { cabin(id: $id) { ...felt } }
```

Navnesøk (case-insensitivt, `%` er jokertegn):

```graphql
query($navn: String!) {
  cabins(paging: {first: 20}, filter: {name: {iLike: $navn}, status: {eq: PUBLIC}}, sorting: []) {
    edges { node { id name serviceLevel ownerGroupConnection { id name } } }
  }
}
```

## Felt på typen Cabin

Hentet av scriptet:

| Felt | Innhold |
|---|---|
| `id`, `name`, `status` | ID brukes i URL `https://ut.no/hytte/<id>`. Status er `PUBLIC` for publiserte hytter. |
| `serviceLevel` | Hovednivå, se enum under. |
| `serviceStatusToday` | Perioden som gjelder i dag: `serviceLevel`, `beds` (Float), `from`, `to`, `openAllYear`. |
| `serviceStatusAll` | Alle registrerte perioder, samme form. Datoer er UTC midnatt, bruk bare datodelen. Typen `CabinServiceStatus` har også `key` (String: «dnt-key», «special key», «unlocked» eller null), ujevnt utfylt og ikke brukt. |
| `bedsStaffed`, `bedsSelfService`, `bedsNoService`, `bedsWinter`, `bedsExtra` | Sengetall per nivå. |
| `geojson` | GeoJSON Point, `coordinates` er `[lon, lat, høyde]`. |
| `elevationCustom` | Manuelt satt høyde, som regel null. |
| `municipalities`, `counties`, `areas`, `protectedAreas` | Lister med `id` og `name`. Områder er DNT-områder som Jotunheimen og Oslomarka. |
| `email`, `phone`, `mobile` | Kontakt til hytta. |
| `bookingEnabled`, `bookingOnly`, `bookingUrl` | Booking peker til hyttebestilling.dnt.no. |
| `carAllYear`, `carSummer`, `bicycle`, `publicTransportAvailable`, `boatTransportAvailable` | Adkomstflagg. |
| `summertimeText`, `wintertimeText`, `accessibilityDescription`, `description` | HTML-tekst. |
| `facilities`, `accessibilities`, `suitableFor` | Lister med `name` (engelsk nøkkel) og `displayName` (norsk). |
| `ownerGroupConnection` | Eierforening med `id` og `name`. DNT Oslo og Omegn har ID 156. |
| `links` | Eksterne lenker med `type` (price, weather, ...), `url`, `title`. |
| `yearOfConstruction`, `updatedAt` | Byggeår og sist endret på ut.no. |

Finnes, men hentes ikke fordi de er interne eller irrelevante: `internalNote`, `createdBy`, `updatedBy`, `idVisbook`, `idVisbookSecondary`, `myUserData`, `media`, `portfolioMedia`, `videoUri`, `totalCheckinCount`, `listConnection`, `routeIds`, `poiIds`, `tripIds`.

## Enums

`CabinServiceLevelEnum`: `STAFFED`, `SELF_SERVICE`, `NO_SERVICE`, `NO_SERVICE_NO_BEDS`, `FOOD_SERVICE`, `EMERGENCY_SHELTER`, `CLOSED`, `RENTAL`, `UNKNOWN`.

`StringFieldComparison` (for `name`-filter): `eq`, `neq`, `like`, `notLike`, `iLike`, `notILike`, `in`, `notIn` med flere.

## Områder (brukes av lag_kart.py)

Hver hytte har `areas { id name areaType }`. DNT-områdene har `areaType: DNT_AREA`, villreinområder `REINDEER_AREA`. Geometrien til et område hentes med

```graphql
query($id: Int!) { area(id: $id) { name areaType geojson centerPointGeojson } }
```

`geojson` er Polygon eller MultiPolygon i lon/lat. Polygonene kan gå utenfor riksgrensa (Femundsmarka og Østerdalsfjella går inn i Sverige), så `lag_kart.py` klipper dem mot landomrisset. ID-ene til områdene på skjermen står i `polygon` (tegnes) og `grupper` (brukes til å plassere hytter) under hvert område i `hytter.json`. Områdene er flate, `subType` er null på alle, så Oslomarka som paraply over Nordmarka og Østmarka må uttrykkes i `grupper`. Andre felt på typen `Area`: `status`, `provider`, `subType`, `description`, `area`, `restrictions`, `links`, `media`.

DNT-områder med hytter fra eier 156 per 10. september 2026, med antall hytter per servicenivå:

| ID | Navn | Hytter |
|---|---|---|
| 1280 | Akershus Øst | NO_SERVICE 1 |
| 123 | Alvdal Vestfjell | SELF_SERVICE 2 |
| 1213 | Blefjell og Vegglifjell | SELF_SERVICE 1 |
| 1227 | Breheimen med Jostedalsbreen | STAFFED 2, SELF_SERVICE 10, NO_SERVICE 1, EMERGENCY_SHELTER 1 |
| 12165 | Bærumsmarka | STAFFED 1, NO_SERVICE 6 |
| 1243 | Dovrefjell | STAFFED 1, SELF_SERVICE 1 |
| 1215 | Femundsmarka | STAFFED 1, SELF_SERVICE 5, NO_SERVICE 1 |
| 1219 | Hadeland | NO_SERVICE 2 |
| 12222 | Hallingdal | STAFFED 2, SELF_SERVICE 1 |
| 1235 | Hardangervidda | STAFFED 4, SELF_SERVICE 12, NO_SERVICE 1, CLOSED 1 |
| 12177 | Hardangervidda Sør | SELF_SERVICE 3 |
| 1231 | Jotunheimen | STAFFED 7, SELF_SERVICE 8, NO_SERVICE 1, EMERGENCY_SHELTER 1 |
| 12163 | Kjekstadmarka | NO_SERVICE 2 |
| 12166 | Krokskogen | NO_SERVICE 7 |
| 1229 | Langsua | STAFFED 1, SELF_SERVICE 8, FOOD_SERVICE 1 |
| 1222 | Lillehammer-Rondane | SELF_SERVICE 3, CLOSED 1 |
| 12168 | Lillomarka og Gjelleråsen | NO_SERVICE 4 |
| 1271 | Nordmarka | STAFFED 1, NO_SERVICE 11 |
| 1279 | Oslofjorden | STAFFED 1, NO_SERVICE 5 |
| 1223 | Oslomarka | STAFFED 2, NO_SERVICE 42 |
| 12167 | Romeriksåsene | NO_SERVICE 4 |
| 1224 | Rondane | STAFFED 3, SELF_SERVICE 4, EMERGENCY_SHELTER 1 |
| 1232 | Skarvheimen | STAFFED 4, SELF_SERVICE 8 |
| 1230 | Tafjordfjella og Reinheimen | SELF_SERVICE 1 |
| 1272 | Vestmarka | NO_SERVICE 5 |
| 12171 | Østerdalsfjella | SELF_SERVICE 6 |
| 1273 | Østmarka | NO_SERVICE 8 |

I tillegg står én nødbu i «Jotunheimen villreinområde» (124470), som er `DNT_AREA` på ut.no selv om navnet sier villrein. Tallene per område overlapper fordi ti selvbetjente og fire betjente hytter ligger i flere områder.

## Andre nyttige innganger

- `search(input: {searchString: "...", fullResult: true})` er ut.no sitt autocomplete-søk på tvers av hytter, ruter og steder.
- `cabinsNear(input: FindNearInput)` finner hytter nær et punkt.
- `list(id: 19344095)` er ut.no-listen «DNT Oslo og omegns betjente hytter», vedlikeholdt av foreningen.
- Hyttesiden `https://ut.no/hytte/<id>/<slug>` bærer samme data som `publicCabinData` i `__NEXT_DATA__`, men uten koordinater, kommune, fylke, område og dagens status.

## Tall per 10. september 2026

Eier 156 (DNT Oslo og Omegn) hadde 147 publiserte hytter: 25 betjente, 62 selvbetjente, 54 ubetjente, 3 nødbuer, 2 stengte og 1 serveringssted. Samme tall som 7. september. Av de 62 selvbetjente er 11 selvbetjeningskvarter ved betjente hytter, egne oppføringer med «Selvbetjent» eller «selvbetjening» i navnet, som scriptet utelater. Perioder for betjente og selvbetjente bruker bare nivåene STAFFED, SELF_SERVICE og CLOSED.

## Undersøke skjemaet på nytt

Begynner scriptet å feile med GraphQL-feil, er skjemaet sannsynligvis endret. Sjekk feltene slik:

```bash
curl -s -X POST -H "Content-Type: application/json" -d '{"query":"{__type(name:\"Cabin\"){fields{name type{name kind ofType{name}}}}}"}' https://ut.no/api/graphql
```

Alle spørringsnavn:

```bash
curl -s -X POST -H "Content-Type: application/json" -d '{"query":"{__schema{queryType{fields{name}}}}"}' https://ut.no/api/graphql
```
