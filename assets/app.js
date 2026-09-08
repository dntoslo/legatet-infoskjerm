/* Infoskjerm for betjente hytter i DNT Oslo og Omegn.
   Leser data.json (generert av scripts/hent_data.py), regner ut status for
   dagens dato i norsk tid og tegner ett kort per fjellområde. */

(function () {
  "use strict";

  const DATAFIL = "data.json";
  const RELOAD_MS = 30 * 60 * 1000;       // sikkerhetsnett i tillegg til TV-ens refresh
  const GAMMEL_ETTER_TIMER = 36;          // varsle hvis Action ikke har levert nye data
  const SNART_DAGER = 14;                 // vis «om N dager» innen dette

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

  function el(tag, klasse, tekst) {
    const e = document.createElement(tag);
    if (klasse) e.className = klasse;
    if (tekst != null) e.textContent = tekst;
    return e;
  }

  function tegn(data, iDag) {
    const rutenett = document.getElementById("rutenett");
    rutenett.replaceChildren();

    const omrader = data.omrader || [...new Set(data.hytter.map(h => h.omrade))];
    for (const omrade of omrader) {
      const hytter = data.hytter.filter(h => h.omrade === omrade);
      if (!hytter.length) continue;

      const kort = el("section", "kort");
      kort.appendChild(el("h2", null, omrade));
      const liste = el("ul");
      for (const h of hytter) {
        const s = status(h, iDag);
        const li = el("li", `hytte ${s.klasse}`);
        li.appendChild(el("i", `prikk ${s.klasse}`));
        li.appendChild(el("span", "navn", h.navn));
        const st = el("span", "status");
        st.appendChild(el("span", "niva", s.niva));
        st.appendChild(document.createTextNode(" · "));
        st.appendChild(el("span", s.snart ? "snart" : "detalj", s.detalj));
        li.appendChild(st);
        liste.appendChild(li);
      }
      kort.appendChild(liste);
      rutenett.appendChild(kort);
    }
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
      const rutenett = document.getElementById("rutenett");
      if (!rutenett.querySelector(".kort")) {
        rutenett.replaceChildren(el("p", "feil", `Fikk ikke lastet åpningstider (${e.message}). Prøver igjen.`));
      }
      const boks = document.getElementById("oppdatert");
      boks.textContent = `Klarte ikke å hente nye data (${e.message})`;
      boks.classList.add("gammel");
    }
  }

  last();
  setTimeout(() => location.reload(), RELOAD_MS);

  // Eksponert for testing i konsollen: infoskjerm.status(hytte, "2026-10-04")
  window.infoskjerm = { status, gjeldende, iDagOslo };
})();
