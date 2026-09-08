# ut.no GraphQL: det scriptet bygger på

Kartlagt 7. september 2026 mot `https://ut.no/api/graphql`. Endepunktet er det nettsiden ut.no selv bruker. Det er ikke dokumentert offentlig, krever ingen autentisering for offentlige data, og tar imot vanlig `POST` med `{"query": ..., "variables": ...}` som JSON. Introspeksjon er åpen, så alt under kan verifiseres på nytt med kommandoene nederst.

## Spørringer scriptet bruker

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

Alle hytter til en eier:

```graphql
query($eier: Int!) {
  cabins(paging: {first: 500}, filter: {ownerGroupId: {eq: $eier}, status: {eq: PUBLIC}},
         sorting: [{field: name, direction: ASC}]) {
    totalCount
    edges { node { id name serviceLevel bedsStaffed bedsSelfService bedsNoService municipalities { name } areas { name } } }
  }
}
```

`paging`, `filter` og `sorting` er alle påkrevd på `cabins`, men `sorting: []` er lov.

## Felt på typen Cabin

Hentet av scriptet:

| Felt | Innhold |
|---|---|
| `id`, `name`, `status` | ID brukes i URL `https://ut.no/hytte/<id>`. Status er `PUBLIC` for publiserte hytter. |
| `serviceLevel` | Hovednivå, se enum under. |
| `serviceStatusToday` | Perioden som gjelder i dag: `serviceLevel`, `beds` (Float), `from`, `to`, `openAllYear`. |
| `serviceStatusAll` | Alle registrerte perioder, samme form. Datoer er UTC midnatt, bruk bare datodelen. |
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

## Andre nyttige innganger

- `search(input: {searchString: "...", fullResult: true})` er ut.no sitt autocomplete-søk på tvers av hytter, ruter og steder.
- `cabinsNear(input: FindNearInput)` finner hytter nær et punkt.
- `list(id: 19344095)` er ut.no-listen «DNT Oslo og omegns betjente hytter», vedlikeholdt av foreningen.
- Hyttesiden `https://ut.no/hytte/<id>/<slug>` bærer samme data som `publicCabinData` i `__NEXT_DATA__`, men uten koordinater, kommune, fylke, område og dagens status.

## Tall per 7. september 2026

Eier 156 (DNT Oslo og Omegn) hadde 147 publiserte hytter: 25 betjente, 62 selvbetjente, 54 ubetjente, 3 nødbuer, 2 stengte og 1 serveringssted.

## Undersøke skjemaet på nytt

Begynner scriptet å feile med GraphQL-feil, er skjemaet sannsynligvis endret. Sjekk feltene slik:

```bash
curl -s -X POST -H "Content-Type: application/json" -d '{"query":"{__type(name:\"Cabin\"){fields{name type{name kind ofType{name}}}}}"}' https://ut.no/api/graphql
```

Alle spørringsnavn:

```bash
curl -s -X POST -H "Content-Type: application/json" -d '{"query":"{__schema{queryType{fields{name}}}}"}' https://ut.no/api/graphql
```
