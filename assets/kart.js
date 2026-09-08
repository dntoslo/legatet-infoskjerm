/* Kartvisning: Sør-Norge i midten, områdekortene i to kolonner rundt.
   Overtar tegningen fra app.js via window.infoskjermTegn. Statuslogikk og
   kortbygging hentes fra window.infoskjerm, så de to visningene viser det
   samme. Kartgrunnlaget ligger i assets/sor-norge.json (laget av
   scripts/lag_kart.py): landomriss, DNT-områdene fra ut.no, innsjøer, elver
   og byer, alt i lon/lat. Det projiseres her sammen med hyttene. */

(function () {
  "use strict";

  const KARTFIL = "assets/sor-norge.json";
  const SVG_NS = "http://www.w3.org/2000/svg";

  // Hvilken kolonne hvert område står i. Vest til venstre, øst til høyre,
  // nord øverst. Områder som ikke står her, havner nederst til høyre.
  const KOLONNER = {
    venstre: ["Breheimen", "Jotunheimen", "Skarvheimen", "Hardangervidda"],
    hoyre: ["Rondane og Dovrefjell", "Femundsmarka", "Langsua", "Oslomarka og Oslofjorden"],
  };

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
  };

  const PRIKK_R = 9;            // hytteprikk, i viewBox-enheter (1 enhet er ca. 0,6 km)
  const BY_R = 6;

  // CSS-klassenavn for et område, brukt til å koble kort, polygon og prikker.
  const omradeKlasse = omrade => "omrade-" + omrade.toLowerCase().replace(/[^a-z0-9]+/g, "-");
  const COS_LAT = Math.cos(61 * Math.PI / 180);

  let kartLovnad = null;
  function hentKart() {
    if (!kartLovnad) {
      kartLovnad = fetch(KARTFIL).then(r => {
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

  function svgEl(tag, attr) {
    const e = document.createElementNS(SVG_NS, tag);
    for (const [k, v] of Object.entries(attr || {})) e.setAttribute(k, v);
    return e;
  }

  const tall = n => Math.round(n * 10) / 10;

  function sti(punkter, lukk) {
    return punkter.map((q, i) => `${i ? "L" : "M"}${tall(q[0])} ${tall(q[1])}`).join("") + (lukk ? "Z" : "");
  }

  // Punktene i en ring eller linje projisert til viewBox-koordinater.
  const projiser = (proj, punkter) => punkter.map(([lon, lat]) => proj.p(lon, lat));

  function tegnKart(kart, omrader, data, iDag, status) {
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

    // Byer med navn
    const byer = svgEl("g", { class: "byer" });
    for (const by of kart.byer || []) {
      const [x, y] = proj.p(by.lon, by.lat);
      byer.appendChild(svgEl("circle", { cx: tall(x), cy: tall(y), r: BY_R }));
      const t = svgEl("text", { x: tall(x + BY_R * 2), y: tall(y) });
      t.textContent = by.navn;
      byer.appendChild(t);
    }
    svg.appendChild(byer);

    // Grenselinja tegnes én gang til, uten fyll, så den ligger over områdene
    // og vannet der de går helt ut til kysten eller riksgrensa.
    const grense = svgEl("g", { class: "grense" });
    for (const ring of kart.ringer) grense.appendChild(svgEl("path", { d: sti(projiser(proj, ring), true) }));
    svg.appendChild(grense);

    // Hyttene øverst
    const prikker = svgEl("g", { class: "prikker" });
    for (const h of data.hytter) {
      if (h.lon == null || h.lat == null) continue;
      const [x, y] = proj.p(h.lon, h.lat);
      const s = status(h, iDag);
      const c = svgEl("circle", { class: `hyttepunkt ${s.klasse} ${omradeKlasse(h.omrade)}`, cx: tall(x), cy: tall(y), r: PRIKK_R });
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
    const cqh = flate.closest(".skjerm").clientHeight / 100;
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
        x: (venstre ? kortRect.right : kortRect.left) - origo.left + (venstre ? 1 : -1) * 0.6 * cqh,
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
        const prikkR = 0.9 * cqh;
        slutt.x -= (slutt.x - start.x) / slutt.d * prikkR;
        slutt.y -= (slutt.y - start.y) / slutt.d * prikkR;
      }
      lag.appendChild(svgEl("line", {
        class: "strek", x1: tall(start.x), y1: tall(start.y), x2: tall(slutt.x), y2: tall(slutt.y),
      }));
      lag.appendChild(svgEl("circle", { class: "strekende", cx: tall(slutt.x), cy: tall(slutt.y), r: tall(0.45 * cqh) }));
    }
  }

  let strekTimer = null;
  window.addEventListener("resize", () => {
    clearTimeout(strekTimer);
    strekTimer = setTimeout(() => tegnStreker(document.getElementById("rutenett")), 150);
  });

  window.infoskjermTegn = function (data, iDag) {
    const { status, tegnKort, el } = window.infoskjerm;
    const flate = document.getElementById("rutenett");
    flate.replaceChildren();

    const omrader = (data.omrader || [...new Set(data.hytter.map(h => h.omrade))])
      .filter(o => data.hytter.some(h => h.omrade === o));

    const venstre = el("div", "kolonne venstre");
    const hoyre = el("div", "kolonne hoyre");
    const kart = el("div", "kart");
    kart.appendChild(el("p", "laster", "Henter kart …"));

    // Kort i samme rekkefølge som kolonnelisten, ukjente områder til høyre.
    const plasser = (navn, kolonne) => {
      if (!omrader.includes(navn)) return;
      const hytter = data.hytter.filter(h => h.omrade === navn);
      const kort = tegnKort(navn, hytter, iDag);
      kort.classList.add(omradeKlasse(navn));
      if (FARGER[navn]) kort.style.setProperty("--farge", FARGER[navn]);
      else kort.classList.add("uten-farge");
      kolonne.appendChild(kort);
    };
    KOLONNER.venstre.forEach(n => plasser(n, venstre));
    KOLONNER.hoyre.forEach(n => plasser(n, hoyre));
    omrader.filter(o => !KOLONNER.venstre.includes(o) && !KOLONNER.hoyre.includes(o))
      .forEach(n => plasser(n, hoyre));

    flate.append(venstre, kart, hoyre);

    hentKart()
      .then(grunnlag => {
        kart.replaceChildren(tegnKart(grunnlag, omrader, data, iDag, status));
        // Fontene kan komme etter kartet og flytte overskriftene, så strekene
        // tegnes én gang nå og én gang når fontene er klare.
        tegnStreker(flate);
        if (document.fonts && document.fonts.ready) document.fonts.ready.then(() => tegnStreker(flate));
      })
      .catch(e => kart.replaceChildren(el("p", "feil", `Fikk ikke lastet kartet (${e.message})`)));
  };
})();
