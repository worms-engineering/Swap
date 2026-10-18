// TicketSwap original-price bookmarklet.
// On an event page, opens each listing in the background (one at a time, with a
// pause between requests), finds the original ticket price the seller entered
// and shows it under the listing with the difference in %, so good deals stand
// out. Results are cached in the browser so each listing is read only once.
// Stops if TicketSwap shows its verification page.
(async () => {
  /*@common*/
  if (window.__tsPrices) {
    window.__tsPrices.panel.style.display = "block";
    return;
  }
  if (!/ticketswap\./.test(location.hostname)) {
    alert("Apri prima la pagina dell'evento su TicketSwap, poi clicca il segnalibro.");
    return;
  }

  const GAP_MS = window.__tsPricesGapMs != null ? window.__tsPricesGapMs : 1200;
  const CACHE_KEY = "tsOriginalPrices.v1";
  const MISS_TTL = 24 * 3600 * 1000; // re-check listings without an original price after a day
  const LABEL_RE = /prezzo originale|prezzo d'acquisto|prezzo di acquisto|original (?:ticket )?price|face value|originele prijs|prix d'origine|prix initial|originalpreis|precio original/i;
  const JSON_RE = /"(?:originalPrice|original_price|faceValue|face_value)"\s*:\s*(\{[^{}]*\}|"?\d+(?:\.\d+)?"?)/g;

  // ---------- cache (per browser, survives reloads) ----------
  let cache = {};
  try { cache = JSON.parse(localStorage.getItem(CACHE_KEY) || "{}"); } catch (e) { cache = {}; }
  const saveCache = () => {
    try { localStorage.setItem(CACHE_KEY, JSON.stringify(cache)); } catch (e) { /* storage full or blocked */ }
  };
  const cached = (u) => {
    const c = cache[u];
    if (!c) return undefined;
    if (c.orig == null && Date.now() - c.t > MISS_TTL) return undefined;
    return c.orig;
  };

  // ---------- reading the original price from a listing page ----------
  // Money values in page data may be in cents: pick the scale that is plausible
  // next to the resale price.
  const scale = (amount, ref) => {
    const options = Number.isInteger(amount) ? [amount / 100, amount] : [amount];
    if (ref) {
      for (const v of options) if (ref / v >= 0.3 && ref / v <= 3) return v;
      return null;
    }
    return Number.isInteger(amount) && amount >= 1000 ? amount / 100 : amount;
  };

  const extractOriginal = (html, doc, ref) => {
    const body = doc.body ? textOf(doc.body).replace(/ /g, " ") : "";
    const m = LABEL_RE.exec(body);
    if (m) {
      const after = body.slice(m.index + m[0].length, m.index + m[0].length + 60);
      const p = PRICE_RE.exec(after);
      if (p) return parseAmount(p[1] || p[2]);
    }
    for (const j of html.matchAll(JSON_RE)) {
      let raw = j[1];
      if (raw[0] === "{") {
        const a = /"amount"\s*:\s*"?(\d+(?:\.\d+)?)/.exec(raw);
        if (!a) continue;
        raw = a[1];
      }
      const v = scale(parseFloat(raw.replace(/"/g, "")), ref);
      if (v > 0) return v;
    }
    return null;
  };

  // ---------- badges on the event page ----------
  const cards = new Map(); // listing url -> {price, currency, anchors:Set}
  const badgeFor = (a) => {
    let b = a.querySelector(":scope > .ts-orig");
    if (!b) {
      b = document.createElement("span");
      b.className = "ts-orig";
      b.style.cssText = "display:inline-block;margin:6px 0 0;padding:3px 8px;border-radius:999px;font:600 13px/1.4 system-ui,sans-serif;";
      a.appendChild(b);
    }
    return b;
  };
  const paint = (u) => {
    const c = cards.get(u);
    const orig = cached(u);
    for (const a of c.anchors) {
      if (!a.isConnected) { c.anchors.delete(a); continue; }
      const b = badgeFor(a);
      if (orig === undefined) {
        b.textContent = "Prezzo originale: …";
        b.style.background = "#eef1f4"; b.style.color = "#5b6470";
      } else if (orig === null || !c.price) {
        b.textContent = "Prezzo originale: n.d.";
        b.style.background = "#eef1f4"; b.style.color = "#5b6470";
      } else {
        const d = Math.round((c.price / orig - 1) * 100);
        b.textContent = "Originale " + fmt(orig) + " " + c.currency + " · " + (d > 0 ? "+" : "") + d + "%";
        const [bg, fg] = d <= 0 ? ["#dff6e7", "#11703a"] : d <= 10 ? ["#fff3d6", "#8a5a00"] : ["#fde3e3", "#a31b1b"];
        b.style.background = bg; b.style.color = fg;
      }
    }
  };

  const queue = [];
  const scan = () => {
    for (const a of document.querySelectorAll(LINK_SEL)) {
      const u = new URL(a.getAttribute("href"), location.href).href.split(/[?#]/)[0];
      let c = cards.get(u);
      if (!c) {
        const text = textOf(a).replace(/ /g, " ").replace(/Prezzo originale.*$|Originale .*$/, "");
        const p = PRICE_RE.exec(text), cur = /[€£$]/.exec(text);
        c = { price: p ? parseAmount(p[1] || p[2]) : null, currency: cur ? cur[0] : "€", anchors: new Set(), sold: SOLD_RE.test(text) };
        cards.set(u, c);
        if (cached(u) === undefined) queue.push(u);
      }
      c.anchors.add(a);
      paint(u);
    }
    render();
  };

  // ---------- panel ----------
  const panel = document.createElement("div");
  panel.id = "ts-prices-panel";
  panel.style.cssText = "position:fixed;right:16px;top:16px;z-index:2147483646;width:320px;max-width:calc(100vw - 32px);" +
    "background:#fff;color:#111;border:2px solid #00b6f0;border-radius:12px;box-shadow:0 8px 24px rgba(0,0,0,.25);" +
    "font:14px/1.4 system-ui,sans-serif;padding:12px;";
  panel.innerHTML =
    '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">' +
    "<strong>💶 Prezzi originali</strong>" +
    '<button data-a="hide" title="Nascondi" style="border:0;background:none;font-size:18px;cursor:pointer">–</button></div>' +
    '<div data-r="status"></div><div data-r="best" style="margin-top:6px"></div>' +
    '<div style="color:#5b6470;font-size:12px;margin-top:6px">La % confronta il prezzo su TicketSwap (commissioni incluse) con quello originale indicato dal venditore.</div>' +
    '<div style="margin-top:8px"><button data-a="close" style="border:1px solid #ccc;background:#fff;border-radius:6px;padding:6px 10px;cursor:pointer">Chiudi</button></div>';
  document.body.appendChild(panel);
  const $ = (k) => panel.querySelector('[data-r="' + k + '"]');

  const state = { running: true, panel, cards, fetched: 0, stopped: null };
  window.__tsPrices = state;

  const render = () => {
    const urls = [...cards.keys()];
    const known = urls.filter((u) => cached(u) !== undefined);
    const found = known.filter((u) => cached(u) && cards.get(u).price);
    let status = "Letti " + known.length + "/" + urls.length + " annunci" +
      (found.length !== known.length ? " · " + found.length + " con prezzo originale" : "");
    if (state.stopped) status = '<span style="color:#e5243b">' + state.stopped + "</span><br>" + status;
    else if (known.length < urls.length) status = "⏳ " + status;
    $("status").innerHTML = status;
    const best = found
      .filter((u) => !cards.get(u).sold)
      .map((u) => ({ u, c: cards.get(u), d: cards.get(u).price / cached(u) - 1 }))
      .sort((x, y) => x.d - y.d)
      .slice(0, 3);
    $("best").innerHTML = best.length ? "<b>Migliori affari</b>" : "";
    for (const { u, c, d } of best) {
      const a = document.createElement("a");
      a.href = u;
      a.target = "_blank";
      a.rel = "noopener";
      const pct = Math.round(d * 100);
      a.textContent = "👉 " + fmt(c.price) + " " + c.currency + " (originale " + fmt(cached(u)) + " " + c.currency + ", " + (pct > 0 ? "+" : "") + pct + "%)";
      a.style.cssText = "display:block;margin:4px 0;padding:6px 8px;background:#e8f8fe;border-radius:6px;color:#0077a8;font-weight:600;text-decoration:none";
      $("best").appendChild(a);
    }
  };

  const observer = new MutationObserver((muts) => {
    // Ignore changes made by our own badges.
    const ours = (m) => panel.contains(m.target) ||
      [...m.addedNodes].every((n) => n.nodeType !== 1 || n.classList.contains("ts-orig") || n === panel);
    if (muts.every(ours)) return;
    clearTimeout(state.scanTimer);
    state.scanTimer = setTimeout(scan, 300);
  });
  observer.observe(document.body, { childList: true, subtree: true });

  panel.querySelector('[data-a="hide"]').onclick = () => { panel.style.display = "none"; };
  panel.querySelector('[data-a="close"]').onclick = () => {
    state.running = false;
    observer.disconnect();
    document.querySelectorAll(".ts-orig").forEach((b) => b.remove());
    panel.remove();
    delete window.__tsPrices;
  };

  // ---------- worker: one listing at a time ----------
  scan();
  while (state.running) {
    const u = queue.shift();
    if (!u) { await sleep(1000); continue; }
    if (cached(u) !== undefined || !cards.has(u)) continue;
    try {
      const r = await fetch(u, { credentials: "include" });
      const html = await r.text();
      const doc = new DOMParser().parseFromString(html, "text/html");
      const ch = isChallenge(doc, r.status);
      if (ch) {
        state.running = false;
        state.stopped = "⛔ TicketSwap chiede una verifica: lettura fermata. Ricarica la pagina a mano prima di riprovare.";
        render();
        break;
      }
      cache[u] = { orig: r.ok ? extractOriginal(html, doc, cards.get(u).price) : null, t: Date.now() };
      saveCache();
      state.fetched++;
    } catch (e) {
      cache[u] = { orig: null, t: Date.now() };
    }
    paint(u);
    render();
    await sleep(GAP_MS * (0.8 + Math.random() * 0.4));
  }
})();
