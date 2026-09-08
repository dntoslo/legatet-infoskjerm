/* Kartvisning: Sør-Norge i midten, områdekortene i to kolonner rundt.
   Overtar tegningen fra app.js via window.infoskjermTegn. Statuslogikk og
   kortbygging hentes fra window.infoskjerm, så de to visningene viser det
   samme. Omrisset ligger i assets/sor-norge.json (laget av scripts/lag_kart.py)
   som ringer i lon/lat, og projiseres her sammen med hyttene. */

(function () {
  "use strict";

  const OMRISSFIL = "assets/sor-norge.json";
  const SVG_NS = "http://www.w3.org/2000/svg";

  // Hvilken kolonne hvert område står i. Vest til venstre, øst til høyre,
  // nord øverst. Områder som ikke står her, havner nederst til høyre.
  const KOLONNER = {
    venstre: ["Breheimen", "Jotunheimen", "Hardangervidda og Skarvheimen"],
    hoyre: ["Rondane og Dovrefjell", "Femundsmarka", "Langsua", "Oslomarka og Oslofjorden"],
  };

  // Hytter i samme område som ligger lenger fra hverandre enn dette, får hver
  // sin flekk. Streken fra kortet går til den nærmeste.
  const KLYNGE_KM = 80;
  const FLEKK_BREDDE = 40;      // i viewBox-enheter, 1 enhet er ca. 0,6 km
  const PRIKK_R = 9;

  const COS_LAT = Math.cos(61 * Math.PI / 180);
  const KM_PER_GRAD = 111;

  let omrissLovnad = null;
  function hentOmriss() {
    if (!omrissLovnad) {
      omrissLovnad = fetch(OMRISSFIL).then(r => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      });
    }
    return omrissLovnad;
  }

  // Enkel projeksjon: lengdegrad skalert med cos(61°), nord opp. Godt nok
  // for Sør-Norge, og én funksjon for både omriss og hytter.
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

  function avstandKm(a, b) {
    const dx = (a.lon - b.lon) * COS_LAT * KM_PER_GRAD;
    const dy = (a.lat - b.lat) * KM_PER_GRAD;
    return Math.hypot(dx, dy);
  }

  // Enkel «single linkage»: to hytter hører sammen hvis de, eller noen de
  // allerede hører sammen med, ligger innen KLYNGE_KM.
  function klynger(hytter) {
    const grupper = hytter.map(h => [h]);
    let slaattSammen = true;
    while (slaattSammen) {
      slaattSammen = false;
      ytre:
      for (let i = 0; i < grupper.length; i++) {
        for (let j = i + 1; j < grupper.length; j++) {
          const naer = grupper[i].some(a => grupper[j].some(b => avstandKm(a, b) <= KLYNGE_KM));
          if (naer) {
            grupper[i].push(...grupper.splice(j, 1)[0]);
            slaattSammen = true;
            break ytre;
          }
        }
      }
    }
    return grupper;
  }

  // Konveks innhylling (monotone chain) av projiserte punkter.
  function hull(punkter) {
    const p = [...punkter].sort((a, b) => a[0] - b[0] || a[1] - b[1]);
    if (p.length < 3) return p;
    const kryss = (o, a, b) => (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0]);
    const nedre = [];
    for (const q of p) {
      while (nedre.length >= 2 && kryss(nedre[nedre.length - 2], nedre[nedre.length - 1], q) <= 0) nedre.pop();
      nedre.push(q);
    }
    const ovre = [];
    for (const q of p.reverse()) {
      while (ovre.length >= 2 && kryss(ovre[ovre.length - 2], ovre[ovre.length - 1], q) <= 0) ovre.pop();
      ovre.push(q);
    }
    return nedre.slice(0, -1).concat(ovre.slice(0, -1));
  }

  const tall = n => Math.round(n * 10) / 10;

  function sti(punkter, lukk) {
    return punkter.map((q, i) => `${i ? "L" : "M"}${tall(q[0])} ${tall(q[1])}`).join("") + (lukk ? "Z" : "");
  }

  // En myk flekk rundt en gruppe hytter: innhyllingen tegnet med bred, rund
  // strek. Én hytte gir en sirkel, to gir en kapsel, flere en avrundet form.
  function tegnFlekk(gruppe, proj, klasse) {
    const pkt = gruppe.map(h => proj.p(h.lon, h.lat));
    if (pkt.length === 1) {
      return svgEl("circle", { class: `flekk ${klasse}`, cx: tall(pkt[0][0]), cy: tall(pkt[0][1]), r: FLEKK_BREDDE / 2 });
    }
    return svgEl("path", {
      class: `flekk ${klasse}`,
      d: sti(hull(pkt), pkt.length > 2),
      "stroke-width": FLEKK_BREDDE,
    });
  }

  function tegnKart(omriss, omrader, data, iDag, status) {
    const proj = lagProjeksjon(omriss.bbox);
    const svg = svgEl("svg", {
      viewBox: `0 0 ${proj.W} ${proj.H}`,
      preserveAspectRatio: "xMidYMid meet",
      role: "img",
      "aria-label": "Kart over Sør-Norge med hyttene markert",
    });

    // Land
    const land = svgEl("g", { class: "land" });
    for (const ring of omriss.ringer) {
      land.appendChild(svgEl("path", { d: sti(ring.map(([lon, lat]) => proj.p(lon, lat)), true) }));
    }
    svg.appendChild(land);

    // Flekker per område, deretter prikker over alt
    const flekker = svgEl("g", { class: "flekker" });
    const prikker = svgEl("g", { class: "prikker" });
    omrader.forEach((omrade, i) => {
      const hytter = data.hytter.filter(h => h.omrade === omrade && h.lon != null && h.lat != null);
      for (const gruppe of klynger(hytter)) {
        flekker.appendChild(tegnFlekk(gruppe, proj, `omrade-${i + 1}`));
      }
      for (const h of hytter) {
        const [x, y] = proj.p(h.lon, h.lat);
        const s = status(h, iDag);
        const c = svgEl("circle", { class: `hyttepunkt ${s.klasse}`, cx: tall(x), cy: tall(y), r: PRIKK_R });
        c.appendChild(svgEl("title")).textContent = `${h.navn}: ${s.niva}, ${s.detalj}`;
        prikker.appendChild(c);
      }
    });
    svg.appendChild(flekker);
    svg.appendChild(prikker);
    return svg;
  }

  // Strek fra hvert kort til flekken sin, tegnet i et SVG-lag over hele flaten
  // i skjermpiksler. Må tegnes på nytt når flaten endrer størrelse.
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

      // Nærmeste flekk med samme farge
      let best = null;
      for (const flekk of kartSvg.querySelectorAll(`.flekk.${klasse}`)) {
        const r = flekk.getBoundingClientRect();
        const m = { x: r.left + r.width / 2 - origo.left, y: r.top + r.height / 2 - origo.top, r: Math.min(r.width, r.height) / 2 };
        const d = Math.hypot(m.x - start.x, m.y - start.y);
        if (!best || d < best.d) best = { ...m, d };
      }
      if (!best) continue;

      // Streken stopper ved kanten av flekken, med en liten prikk der.
      const ux = (best.x - start.x) / best.d;
      const uy = (best.y - start.y) / best.d;
      const slutt = { x: best.x - ux * best.r, y: best.y - uy * best.r };
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

    hentOmriss()
      .then(omriss => {
        kart.replaceChildren(tegnKart(omriss, omrader, data, iDag, status));
        // Fontene kan komme etter kartet og flytte overskriftene, så strekene
        // tegnes én gang nå og én gang når fontene er klare.
        tegnStreker(flate);
        if (document.fonts && document.fonts.ready) document.fonts.ready.then(() => tegnStreker(flate));
      })
      .catch(e => kart.replaceChildren(el("p", "feil", `Fikk ikke lastet kartet (${e.message})`)));
  };
})();
