/* Infoskjerm for hyttene i DNT Oslo og Omegn. Ett skript for begge sidene:
   index.html (betjente hytter) og selvbetjente.html (selvbetjente hytter).
   Leser data.json (generert av scripts/hent_data.py), plukker hyttene som
   hører til sida, regner ut status for dagens dato i norsk tid og tegner ett
   kort per fjellområde i to kolonner rundt et kart av Sør-Norge.
   Kartgrunnlaget ligger i assets/sor-norge.json (laget av
   scripts/lag_kart.py): landomriss, DNT-områdene fra ut.no, innsjøer, elver
   og byer, alt i lon/lat. Det projiseres her sammen med hyttene.

   Skjermen kjører Tizen 7.0 med Chromium 94. Bruk ikke JS nyere enn det
   (replaceChildren er det nyeste her). */

(function () {
  "use strict";

  const DATAFIL = "data.json";
  const KARTFIL = "assets/sor-norge.json";
  const RELOAD_MS = 30 * 60 * 1000;       // sikkerhetsnett i tillegg til TV-ens refresh
  const GAMMEL_ETTER_TIMER = 36;          // varsle hvis Action ikke har levert nye data
  const SNART_DAGER = 14;                 // vis «om N dager» innen dette

  // Én konfigurasjon per side, valgt med data-side på <body>.
  //   velg: hvilke hytter i data.json som hører til sida.
  //   kort: hvordan kortene tegnes, se tegnKort. «detalj» er én statuslinje
  //     per hytte, «liste» er alle navn i to spalter med prikk.
  //   kolonner: hvilken kolonne hvert område står i. Vest til venstre, øst til
  //     høyre, nord øverst. Områder som ikke står her, havner nederst til høyre.
  //   prikkR: hytteprikk på kartet i viewBox-enheter (1 enhet er ca. 0,6 km).
  // Side 2 har dobbelt så mange hytter, derfor mindre prikker, og Langsua står
  // til høyre fordi venstre kolonne med 30 hytter er nesten full. Rekkefølgen
  // i en kolonne må følge nord til sør, ellers krysser strekene hverandre.
  const SIDER = {
    betjente: {
      velg: h => h.serviceLevel === "STAFFED",
      kort: "detalj",
      kolonner: {
        venstre: ["Breheimen", "Jotunheimen", "Skarvheimen", "Hardangervidda"],
        hoyre: ["Rondane og Dovrefjell", "Femundsmarka", "Langsua", "Oslomarka og Oslofjorden"],
      },
      prikkR: 9,
    },
    selvbetjente: {
      velg: h => h.serviceLevel === "SELF_SERVICE",
      kort: "liste",
      kolonner: {
        venstre: ["Breheimen", "Jotunheimen", "Skarvheimen", "Hardangervidda"],
        hoyre: ["Femundsmarka", "Rondane og Dovrefjell", "Østerdalsfjella", "Langsua"],
      },
      prikkR: 5.5,              // samme tall som r på .hyttepunkt.stengt for side 2 i style.css
    },
  };
  const SIDE = SIDER[document.body.dataset.side] || SIDER.betjente;

  // Farge per område, brukt både på kortet og som fyll på kartet. Dempede
  // DNT-toner, med hensikt ulike statusfargene grønn, oransje og rød, så
  // prikkene leses tydelig oppå. Områder som ikke står her (Oslomarka og
  // Oslofjorden), tegnes ikke på kartet, og streken går til hyttene i stedet.
  // Naboområder må ha farger som skiller seg klart: Breheimen, Jotunheimen,
  // Skarvheimen og Hardangervidda ligger etter hverandre nord til sør.
  const FARGER = {
    "Jotunheimen": "#C5DCEA",            // blå
    "Hardangervidda": "#FFF097",         // gul
    "Skarvheimen": "#FFC8C3",            // lys rød
    "Rondane og Dovrefjell": "#E9F2D9",  // lys grønn
    "Breheimen": "#DDD3EA",              // lilla, dempet
    "Langsua": "#F5DDB0",                // beige, litt dypere enn DNT mørk beige for å synes mot hvitt
    "Femundsmarka": "#C9E9E4",           // lys turkis
    "Østerdalsfjella": "#F2CFDF",        // lys rosa, ulik naboene Femundsmarka og Rondane
  };

  const BY_R = 6;               // byprikk, i viewBox-enheter (1 enhet er ca. 0,6 km)
  const COS_LAT = Math.cos(61 * Math.PI / 180);
  const SVG_NS = "http://www.w3.org/2000/svg";

  const MAANEDER = ["januar", "februar", "mars", "april", "mai", "juni",
    "juli", "august", "september", "oktober", "november", "desember"];
  const MAANEDER_KORT = ["jan.", "feb.", "mars", "april", "mai", "juni",
    "juli", "aug.", "sep.", "okt.", "nov.", "des."];
  const UKEDAGER = ["søndag", "mandag", "tirsdag", "onsdag", "torsdag", "fredag", "lørdag"];

  const NIVAA = {
    STAFFED: { klasse: "betjent", tekst: "Betjent" },
    SELF_SERVICE: { klasse: "selvbetjent", tekst: "Selvbetjent" },
    NO_SERVICE: { klasse: "selvbetjent", tekst: "Ubetjent" },
    FOOD_SERVICE: { klasse: "betjent", tekst: "Servering" },
    CLOSED: { klasse: "stengt", tekst: "Stengt" },
  };

  /* ---------- Dato og status ---------- */

  // Dagens dato som YYYY-MM-DD i norsk tid, uavhengig av TV-ens tidssone.
  function iDagOslo() {
    return new Intl.DateTimeFormat("sv-SE", { timeZone: "Europe/Oslo" }).format(new Date());
  }

  function tilDato(iso) {
    const [y, m, d] = iso.split("-").map(Number);
    return new Date(Date.UTC(y, m - 1, d));
  }

  function dagerMellom(fraIso, tilIso) {
    return Math.round((tilDato(tilIso) - tilDato(fraIso)) / 86400000);
  }

  function formaterDato(iso, iDag) {
    const d = tilDato(iso);
    const dag = d.getUTCDate();
    const mnd = MAANEDER_KORT[d.getUTCMonth()];
    const aar = d.getUTCFullYear();
    return aar === tilDato(iDag).getUTCFullYear() ? `${dag}. ${mnd}` : `${dag}. ${mnd} ${aar}`;
  }

  function relativ(iso, iDag) {
    const n = dagerMellom(iDag, iso);
    if (n === 0) return "i dag";
    if (n === 1) return "i morgen";
    if (n > 1 && n <= SNART_DAGER) return `om ${n} dager`;
    return null;
  }

  // «om 5 dager» når det er nært, ellers datoen. Kort nok til én linje på TV.
  function naar(iso, iDag) {
    return relativ(iso, iDag) || formaterDato(iso, iDag);
  }

  function erAapen(p) {
    return p.niva !== "CLOSED" && p.niva !== "UNKNOWN";
  }

  // Perioden som gjelder i dag. ut.no lar periodene dele grensedato
  // (betjent til 4. okt, stengt fra 4. okt), så «til» behandles som eksklusiv.
  // Ved overlapp vinner en åpen periode.
  function gjeldende(perioder, iDag) {
    const treff = perioder.filter(p =>
      p.heleAaret ||
      ((!p.fra || p.fra <= iDag) && (!p.til || iDag < p.til))
    );
    if (!treff.length) {
      // Fallback: periode der i dag er lik sluttdato og ingenting nytt starter.
      const kant = perioder.filter(p => p.til === iDag);
      if (kant.length) return kant.find(erAapen) || kant[0];
      return null;
    }
    return treff.find(erAapen) || treff[0];
  }

  function neste(perioder, iDag, filter) {
    return perioder
      .filter(p => !p.heleAaret && p.fra && p.fra > iDag && filter(p))
      .sort((a, b) => a.fra.localeCompare(b.fra))[0] || null;
  }

  // Returnerer { klasse, niva, detalj, snart } for én hytte.
  function status(hytte, iDag) {
    const perioder = hytte.perioder || [];
    const naa = gjeldende(perioder, iDag);

    if (naa && naa.heleAaret && erAapen(naa)) {
      const n = NIVAA[naa.niva] || { klasse: "betjent", tekst: "Åpen" };
      return { klasse: n.klasse, niva: n.tekst, detalj: "hele året", snart: false };
    }

    if (naa && erAapen(naa)) {
      const n = NIVAA[naa.niva] || { klasse: "betjent", tekst: "Åpen" };
      // Hva skjer når denne perioden slutter?
      const etter = neste(perioder, iDag, p => p.fra >= naa.til && p.niva !== naa.niva)
        || (naa.til ? perioder.find(p => p.fra === naa.til && p.niva !== naa.niva) : null);
      if (!naa.til) {
        return { klasse: n.klasse, niva: n.tekst, detalj: "ingen sluttdato", snart: false };
      }
      const snart = relativ(naa.til, iDag) !== null;
      if (etter && erAapen(etter)) {
        const e = NIVAA[etter.niva] || { tekst: "åpen" };
        return { klasse: n.klasse, niva: n.tekst,
          detalj: `${e.tekst.toLowerCase()} ${snart ? "" : "fra "}${naar(naa.til, iDag)}`, snart };
      }
      return { klasse: n.klasse, niva: n.tekst, detalj: `stenger ${naar(naa.til, iDag)}`, snart };
    }

    // Stengt i dag, eller ingen periode registrert.
    const aapner = neste(perioder, iDag, erAapen);
    if (aapner) {
      const a = NIVAA[aapner.niva] || { tekst: "Åpner" };
      const snart = relativ(aapner.fra, iDag) !== null;
      const detalj = aapner.niva === "STAFFED"
        ? `åpner ${naar(aapner.fra, iDag)}`
        : `${a.tekst.toLowerCase()} ${snart ? "" : "fra "}${naar(aapner.fra, iDag)}`;
      return { klasse: "stengt", niva: "Stengt", detalj, snart };
    }
    return { klasse: "stengt", niva: "Stengt", detalj: naa ? "ingen åpningsdato satt" : "ingen data på ut.no", snart: false };
  }

  /* ---------- Hjelpere for DOM og SVG ---------- */

  function el(tag, klasse, tekst) {
    const e = document.createElement(tag);
    if (klasse) e.className = klasse;
    if (tekst != null) e.textContent = tekst;
    return e;
  }

  function svgEl(tag, attr) {
    const e = document.createElementNS(SVG_NS, tag);
    for (const [k, v] of Object.entries(attr || {})) e.setAttribute(k, v);
    return e;
  }

  const tall = n => Math.round(n * 10) / 10;

  function sti(punkter, lukk) {
    return punkter.map((q, i) => `${i ? "L" : "M"}${tall(q[0])} ${tall(q[1])}`).join("") + (lukk ? "Z" : "");
  }

  // CSS-klassenavn for et område, brukt til å koble kort, polygon og prikker.
  // æ, ø og å skrives om først, så «Østerdalsfjella» blir omrade-oesterdalsfjella.
  const omradeKlasse = omrade => "omrade-" + omrade.toLowerCase()
    .replace(/æ/g, "ae").replace(/ø/g, "oe").replace(/å/g, "aa")
    .replace(/[^a-z0-9]+/g, "-");

  /* ---------- Kort ---------- */

  // Én rad slik side 1 viser den: prikk, navn og «Betjent · stenger om 3 dager».
  function radDetalj(rad) {
    const { hytte: h, s } = rad;
    const li = el("li", `hytte ${s.klasse}`);
    li.appendChild(el("i", `prikk ${s.klasse}`));
    li.appendChild(el("span", "navn", h.navn));
    const st = el("span", "status");
    st.appendChild(el("span", "niva", s.niva));
    st.appendChild(document.createTextNode(" · "));
    st.appendChild(el("span", s.snart ? "snart" : "detalj", s.detalj));
    li.appendChild(st);
    return li;
  }

  // Kort tidsangivelse til listevarianten: når en stengt hytte åpner («til
  // 15. feb.»), eller når endringen er nær («om 3 dager», i rødt). Bruker
  // samme perioder og regler som status(), men får plass ved siden av navnet.
  function kortNaar(rad, iDag) {
    const { hytte: h, s } = rad;
    const perioder = h.perioder || [];
    if (s.klasse === "stengt") {
      const aapner = neste(perioder, iDag, erAapen);
      if (!aapner) return null;
      return s.snart
        ? { klasse: "snart", tekst: relativ(aapner.fra, iDag) }
        : { klasse: "detalj", tekst: `til ${formaterDato(aapner.fra, iDag)}` };
    }
    const naa = gjeldende(perioder, iDag);
    if (s.snart && naa && naa.til) return { klasse: "snart", tekst: relativ(naa.til, iDag) };
    return null;
  }

  // Én rad i listevarianten: prikk, navn og eventuelt kort tidsangivelse.
  function radListe(rad, iDag) {
    const { hytte: h, s } = rad;
    const li = el("li", `hytte ${s.klasse}`);
    li.appendChild(el("i", `prikk ${s.klasse}`));
    li.appendChild(el("span", "navn", h.navn));
    const n = kortNaar(rad, iDag);
    if (n) li.appendChild(el("span", `naar ${n.klasse}`, n.tekst));
    return li;
  }

  // «10 hytter · 8 åpne» til kortoverskriften i listevarianten.
  function tell(rader) {
    const aapne = rader.filter(r => r.s.klasse !== "stengt").length;
    return `${rader.length} ${rader.length === 1 ? "hytte" : "hytter"} · ${aapne} ${aapne === 1 ? "åpen" : "åpne"}`;
  }

  // Ett områdekort. Rammen er lik på begge sidene, innholdet følger SIDE.kort:
  // «detalj» (side 1) har én statuslinje per hytte, «liste» (side 2) har alle
  // navn i to spalter med prikk, kort tidsangivelse og teller i overskriften.
  function tegnKort(omrade, hytter, iDag) {
    const kort = el("section", `kort ${omradeKlasse(omrade)}`);
    if (FARGER[omrade]) kort.style.setProperty("--farge", FARGER[omrade]);
    else kort.classList.add("uten-farge");
    const h2 = el("h2", null, omrade);
    kort.appendChild(h2);
    const rader = hytter.map(h => ({ hytte: h, s: status(h, iDag) }));
    const liste = el("ul");

    if (SIDE.kort === "liste") {
      kort.classList.add("liste");
      h2.appendChild(el("span", "teller", tell(rader)));
      // To spalter fylt kolonnevis, så radene ligger på linje på tvers.
      const perSpalte = Math.ceil(rader.length / 2);
      liste.style.gridTemplateRows = `repeat(${perSpalte}, auto)`;
      rader.forEach((rad, i) => {
        const li = radListe(rad, iDag);
        if (i % perSpalte === 0) li.classList.add("spaltestart");
        liste.appendChild(li);
      });
    } else {
      for (const rad of rader) liste.appendChild(radDetalj(rad));
    }
    kort.appendChild(liste);
    return kort;
  }

  /* ---------- Kart ---------- */

  // Hentes én gang per sidelasting, uten cache, så et nytt kartgrunnlag når
  // TV-en uten at ?v= må bumpes. Fila er 20 kB, det tåles hver halvtime.
  let kartLovnad = null;
  function hentKart() {
    if (!kartLovnad) {
      kartLovnad = fetch(`${KARTFIL}?v=${Date.now()}`, { cache: "no-store" }).then(r => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      });
    }
    return kartLovnad;
  }

  // Enkel projeksjon: lengdegrad skalert med cos(61°), nord opp. Godt nok
  // for Sør-Norge, og én funksjon for alle lag.
  function lagProjeksjon(bbox) {
    const [lon0, lat0, lon1, lat1] = bbox;
    const bredde = (lon1 - lon0) * COS_LAT;
    const hoyde = lat1 - lat0;
    const H = 1000;
    const W = Math.round(H * bredde / hoyde);
    return {
      W, H,
      p(lon, lat) {
        return [((lon - lon0) * COS_LAT / bredde) * W, ((lat1 - lat) / hoyde) * H];
      },
    };
  }

  // Punktene i en ring eller linje projisert til viewBox-koordinater.
  const projiser = (proj, punkter) => punkter.map(([lon, lat]) => proj.p(lon, lat));

  function tegnKart(kart, omrader, data, iDag) {
    const proj = lagProjeksjon(kart.bbox);
    const svg = svgEl("svg", {
      viewBox: `0 0 ${proj.W} ${proj.H}`,
      preserveAspectRatio: "xMidYMid meet",
      role: "img",
      "aria-label": "Kart over Sør-Norge med fjellområdene og hyttene markert",
    });

    // Land
    const land = svgEl("g", { class: "land" });
    for (const ring of kart.ringer) land.appendChild(svgEl("path", { d: sti(projiser(proj, ring), true) }));
    svg.appendChild(land);

    // DNT-områdene, fylt i samme farge som kortet. Punktene tas vare på, så
    // streken fra kortet kan gå til nærmeste punkt på kanten.
    const omradeLag = svgEl("g", { class: "omrader" });
    for (const omrade of omrader) {
      if (!FARGER[omrade]) continue;
      for (const ring of kart.omrader[omrade] || []) {
        const pkt = projiser(proj, ring);
        const path = svgEl("path", { class: `omrade ${omradeKlasse(omrade)}`, d: sti(pkt, true) });
        path.style.setProperty("--farge", FARGER[omrade]);
        path.__punkter = pkt;
        omradeLag.appendChild(path);
      }
    }
    svg.appendChild(omradeLag);

    // Vann: innsjøer og elver
    const vann = svgEl("g", { class: "vann" });
    for (const ring of kart.innsjoer || []) vann.appendChild(svgEl("path", { class: "innsjo", d: sti(projiser(proj, ring), true) }));
    for (const linje of kart.elver || []) vann.appendChild(svgEl("path", { class: "elv", d: sti(projiser(proj, linje), false) }));
    svg.appendChild(vann);

    // Grenselinja tegnes én gang til, uten fyll, så den ligger over områdene
    // og vannet der de går helt ut til kysten eller riksgrensa.
    const grense = svgEl("g", { class: "grense" });
    for (const ring of kart.ringer) grense.appendChild(svgEl("path", { d: sti(projiser(proj, ring), true) }));
    svg.appendChild(grense);

    // Byer med navn, over grensa så den hvite kanten rundt bokstavene
    // dekker kystlinja der byen ligger ved sjøen.
    const byer = svgEl("g", { class: "byer" });
    for (const by of kart.byer || []) {
      const [x, y] = proj.p(by.lon, by.lat);
      byer.appendChild(svgEl("circle", { cx: tall(x), cy: tall(y), r: BY_R }));
      const t = svgEl("text", { x: tall(x + BY_R * 2), y: tall(y) });
      t.textContent = by.navn;
      byer.appendChild(t);
    }
    svg.appendChild(byer);

    // Hyttene øverst
    const prikker = svgEl("g", { class: "prikker" });
    for (const h of data.hytter) {
      if (h.lon == null || h.lat == null) continue;
      const [x, y] = proj.p(h.lon, h.lat);
      const s = status(h, iDag);
      const c = svgEl("circle", { class: `hyttepunkt ${s.klasse} ${omradeKlasse(h.omrade)}`, cx: tall(x), cy: tall(y), r: SIDE.prikkR });
      c.__punkter = [[x, y]];
      c.appendChild(svgEl("title")).textContent = `${h.navn}: ${s.niva}, ${s.detalj}`;
      prikker.appendChild(c);
    }
    svg.appendChild(prikker);
    return svg;
  }

  // Strek fra hvert kort til nærmeste punkt på kanten av området sitt, eller
  // til nærmeste hytte når området ikke er tegnet. Tegnes i et SVG-lag over
  // hele flaten i skjermpiksler, og på nytt når flaten endrer størrelse.
  function tegnStreker(flate) {
    let lag = flate.querySelector(".streker");
    if (!lag) {
      lag = svgEl("svg", { class: "streker", "aria-hidden": "true" });
      flate.appendChild(lag);
    }
    lag.replaceChildren();
    const kartSvg = flate.querySelector(".kart svg");
    if (!kartSvg) return;

    const origo = flate.getBoundingClientRect();
    const enhet = flate.closest(".skjerm").clientHeight / 100;   // 1 % av flatens høyde, som 1rem i CSS
    lag.setAttribute("viewBox", `0 0 ${origo.width} ${origo.height}`);
    const ctm = kartSvg.getScreenCTM();
    const tilSkjerm = ([x, y]) => {
      const p = new DOMPoint(x, y).matrixTransform(ctm);
      return { x: p.x - origo.left, y: p.y - origo.top };
    };

    for (const kort of flate.querySelectorAll(".kort")) {
      const klasse = [...kort.classList].find(k => k.startsWith("omrade-"));
      if (!klasse) continue;
      const venstre = kort.closest(".kolonne").classList.contains("venstre");
      const kortRect = kort.getBoundingClientRect();
      const h2Rect = kort.querySelector("h2").getBoundingClientRect();
      const start = {
        x: (venstre ? kortRect.right : kortRect.left) - origo.left + (venstre ? 1 : -1) * 0.6 * enhet,
        y: h2Rect.top + h2Rect.height / 2 - origo.top,
      };

      let slutt = null;
      const maal = kartSvg.querySelectorAll(`.omrade.${klasse}`);
      for (const element of maal.length ? maal : kartSvg.querySelectorAll(`.hyttepunkt.${klasse}`)) {
        for (const pkt of element.__punkter || []) {
          const s = tilSkjerm(pkt);
          const d = Math.hypot(s.x - start.x, s.y - start.y);
          if (!slutt || d < slutt.d) slutt = { ...s, d };
        }
      }
      if (!slutt) continue;

      // Går streken til en hytteprikk, stopper den like utenfor prikken.
      if (!maal.length) {
        const prikkR = 0.9 * enhet;
        slutt.x -= (slutt.x - start.x) / slutt.d * prikkR;
        slutt.y -= (slutt.y - start.y) / slutt.d * prikkR;
      }
      lag.appendChild(svgEl("line", {
        class: "strek", x1: tall(start.x), y1: tall(start.y), x2: tall(slutt.x), y2: tall(slutt.y),
      }));
      lag.appendChild(svgEl("circle", { class: "strekende", cx: tall(slutt.x), cy: tall(slutt.y), r: tall(0.45 * enhet) }));
    }
  }

  let strekTimer = null;
  window.addEventListener("resize", () => {
    clearTimeout(strekTimer);
    strekTimer = setTimeout(() => tegnStreker(document.getElementById("kartflate")), 150);
  });

  /* ---------- Hele flaten ---------- */

  function tegn(data, iDag) {
    const flate = document.getElementById("kartflate");
    flate.replaceChildren();

    // Bare hyttene som hører til denne sida. data.json har begge gruppene.
    const hytter = (data.hytter || []).filter(SIDE.velg);
    if (!hytter.length) {
      flate.replaceChildren(el("p", "feil", "Fant ingen hytter for denne sida i data.json."));
      return;
    }
    const visning = { ...data, hytter };

    // Områdene i kanonisk rekkefølge fra data.omrader, med påfyll av områder
    // som bare finnes på hyttene, og bare de som har hytter på denne sida.
    const omrader = [...new Set([...(data.omrader || []), ...hytter.map(h => h.omrade)])]
      .filter(o => hytter.some(h => h.omrade === o));

    const venstre = el("div", "kolonne venstre");
    const hoyre = el("div", "kolonne hoyre");
    const kart = el("div", "kart");
    kart.appendChild(el("p", "laster", "Henter kart …"));

    // Kort i samme rekkefølge som kolonnelisten, ukjente områder til høyre.
    const kolonner = SIDE.kolonner;
    const plasser = (navn, kolonne) => {
      if (!omrader.includes(navn)) return;
      kolonne.appendChild(tegnKort(navn, hytter.filter(h => h.omrade === navn), iDag));
    };
    kolonner.venstre.forEach(n => plasser(n, venstre));
    kolonner.hoyre.forEach(n => plasser(n, hoyre));
    omrader.filter(o => !kolonner.venstre.includes(o) && !kolonner.hoyre.includes(o))
      .forEach(n => plasser(n, hoyre));

    flate.append(venstre, kart, hoyre);

    hentKart()
      .then(grunnlag => {
        kart.replaceChildren(tegnKart(grunnlag, omrader, visning, iDag));
        // Fontene kan komme etter kartet og flytte overskriftene, så strekene
        // tegnes én gang nå og én gang når fontene er klare.
        tegnStreker(flate);
        if (document.fonts && document.fonts.ready) document.fonts.ready.then(() => tegnStreker(flate));
      })
      .catch(e => kart.replaceChildren(el("p", "feil", `Fikk ikke lastet kartet (${e.message})`)));
  }

  function visIDag(iDag) {
    const d = tilDato(iDag);
    const boks = document.getElementById("idag");
    boks.replaceChildren();
    const ukedag = UKEDAGER[d.getUTCDay()];
    boks.appendChild(el("strong", null, ukedag.charAt(0).toUpperCase() + ukedag.slice(1)));
    boks.appendChild(document.createTextNode(`${d.getUTCDate()}. ${MAANEDER[d.getUTCMonth()]} ${d.getUTCFullYear()}`));
  }

  function visOppdatert(hentetIso) {
    const boks = document.getElementById("oppdatert");
    boks.classList.remove("gammel");
    if (!hentetIso) { boks.textContent = ""; return; }
    const hentet = new Date(hentetIso);
    if (isNaN(hentet)) { boks.textContent = `Sist oppdatert fra ut.no: ${hentetIso}`; return; }
    const fmt = new Intl.DateTimeFormat("nb-NO", {
      timeZone: "Europe/Oslo", day: "numeric", month: "long", year: "numeric",
      hour: "2-digit", minute: "2-digit",
    });
    boks.textContent = `Sist oppdatert fra ut.no: ${fmt.format(hentet).replace(",", " kl.")}`;
    const timer = (Date.now() - hentet.getTime()) / 3600000;
    if (timer > GAMMEL_ETTER_TIMER) boks.classList.add("gammel");
  }

  async function last() {
    const iDag = iDagOslo();
    visIDag(iDag);
    try {
      const svar = await fetch(`${DATAFIL}?v=${Date.now()}`, { cache: "no-store" });
      if (!svar.ok) throw new Error(`HTTP ${svar.status}`);
      const data = await svar.json();
      tegn(data, iDag);
      visOppdatert(data.hentet);
    } catch (e) {
      const flate = document.getElementById("kartflate");
      if (!flate.querySelector(".kort")) {
        flate.replaceChildren(el("p", "feil", `Fikk ikke lastet åpningstider (${e.message}). Prøver igjen.`));
      }
      const boks = document.getElementById("oppdatert");
      boks.textContent = `Klarte ikke å hente nye data (${e.message})`;
      boks.classList.add("gammel");
    }
  }

  last();
  setTimeout(() => location.reload(), RELOAD_MS);

  // Eksponert for testing i konsollen: infoskjerm.status(hytte, "2026-10-04")
  window.infoskjerm = { status, gjeldende, iDagOslo, SIDE };
})();
