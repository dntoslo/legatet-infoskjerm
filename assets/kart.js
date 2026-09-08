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
    venstre: ["Breheimen", "Jotunheimen", "Hardangervidda og Skarvheimen"],
    hoyre: ["Rondane og Dovrefjell", "Femundsmarka", "Langsua", "Oslomarka og Oslofjorden"],
  };

  const PRIKK_R = 9;            // hytteprikk, i viewBox-enheter (1 enhet er ca. 0,6 km)
  const BY_R = 5;
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

    // DNT-områdene, i samme rekkefølge og farge som kortene. Punktene tas
    // vare på, så streken fra kortet kan gå til nærmeste punkt på kanten.
    const omradeLag = svgEl("g", { class: "omrader" });
    omrader.forEach((omrade, i) => {
      for (const ring of kart.omrader[omrade] || []) {
        const pkt = projiser(proj, ring);
        const path = svgEl("path", { class: `omrade omrade-${i + 1}`, d: sti(pkt, true) });
        path.__punkter = pkt;
        omradeLag.appendChild(path);
      }
    });
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

    // Hyttene øverst
    const prikker = svgEl("g", { class: "prikker" });
    for (const h of data.hytter) {
      if (h.lon == null || h.lat == null) continue;
      const [x, y] = proj.p(h.lon, h.lat);
      const s = status(h, iDag);
      const c = svgEl("circle", { class: `hyttepunkt ${s.klasse}`, cx: tall(x), cy: tall(y), r: PRIKK_R });
      c.appendChild(svgEl("title")).textContent = `${h.navn}: ${s.niva}, ${s.detalj}`;
      prikker.appendChild(c);
    }
    svg.appendChild(prikker);
    return svg;
  }

  // Strek fra hvert kort til nærmeste punkt på kanten av området sitt,
  // tegnet i et SVG-lag over hele flaten i skjermpiksler. Tegnes på nytt
  // når flaten endrer størrelse.
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
      for (const path of kartSvg.querySelectorAll(`.omrade.${klasse}`)) {
        for (const pkt of path.__punkter || []) {
          const s = tilSkjerm(pkt);
          const d = Math.hypot(s.x - start.x, s.y - start.y);
          if (!slutt || d < slutt.d) slutt = { ...s, d };
        }
      }
      if (!slutt) continue;

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
      const i = omrader.indexOf(navn);
      if (i < 0) return;
      const kort = tegnKort(navn, data.hytter.filter(h => h.omrade === navn), iDag);
      kort.classList.add(`omrade-${i + 1}`);
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
