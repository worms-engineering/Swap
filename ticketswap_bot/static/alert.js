// TicketSwap price alert bookmarklet.
// Runs in the user's own tab: re-reads the event page every ~20s and sounds an
// alarm when a listing at or below the trigger price appears. It never clicks
// "buy": the user opens the listing and purchases by hand. If TicketSwap shows
// its verification page the monitor stops instead of retrying.
// __CONFIG__ is replaced by the generator with {maxPrice, interval, quantity}.
(async () => {
  const CFG = __CONFIG__;
  if (window.__tsAlert) {
    window.__tsAlert.panel.style.display = "block";
    return;
  }
  if (!/ticketswap\./.test(location.hostname)) {
    alert("Apri prima la pagina dell'evento su TicketSwap, poi clicca il segnalibro.");
    return;
  }

  const PRICE_RE = /(?:[€£$]|EUR|GBP|USD|CHF|DKK|SEK|NOK|PLN)\s*(\d{1,3}(?:[.,\s]\d{3})*(?:[.,]\d{1,2})?|\d+(?:[.,]\d{1,2})?)|(\d{1,3}(?:[.,\s]\d{3})*(?:[.,]\d{1,2})?|\d+(?:[.,]\d{1,2})?)\s*(?:[€£$]|EUR|GBP|USD|CHF)/i;
  const QTY_RE = /(\d+)\s*(?:x\s*)?(?:tickets?|biglietti|biglietto|kaarten|kaart|billets?|entradas?|karten)\b/i;
  const SOLD_RE = /\b(sold|venduto|venduti|verkocht|verkauft|vendu|vendido)\b/i;
  const CHALLENGE_RE = /captcha|are you human|verify you are|verifying|unable to verify|access denied|too many requests|verifica in corso|impossibile verificare/i;
  const LINK_SEL = 'a[href*="/listing/"]';

  const parseAmount = (raw) => {
    let s = raw.replace(/[\s ]/g, "");
    const c = s.lastIndexOf(","), d = s.lastIndexOf(".");
    if (c >= 0 && d >= 0) {
      s = c > d ? s.replace(/\./g, "").replace(",", ".") : s.replace(/,/g, "");
    } else if (c >= 0 || d >= 0) {
      const i = Math.max(c, d), sep = s[i], tail = s.slice(i + 1);
      const head = s.slice(0, i).split(sep).join("");
      s = tail.length <= 2 ? head + "." + tail : head + tail;
    }
    return parseFloat(s);
  };

  let maxPrice = CFG.maxPrice;
  if (maxPrice == null) {
    const ans = prompt("Prezzo massimo per biglietto (trigger price):", "");
    if (ans === null) return;
    maxPrice = parseAmount(ans.replace(/[^\d.,]/g, ""));
    if (!(maxPrice > 0)) {
      alert("Prezzo non valido.");
      return;
    }
  }
  const quantity = CFG.quantity || 1;
  const interval = Math.max(CFG.interval || 20, CFG._minInterval || 10);
  const url = location.href.split("#")[0];

  // ---------- reading listings ----------
  const textOf = (el) => {
    const out = [], w = el.ownerDocument.createTreeWalker(el, NodeFilter.SHOW_TEXT);
    let n;
    while ((n = w.nextNode())) {
      const t = n.nodeValue.trim();
      if (t) out.push(t);
    }
    return out.join(" ");
  };

  const collect = (doc) => {
    const seen = new Set(), out = [];
    for (const a of doc.querySelectorAll(LINK_SEL)) {
      const href = new URL(a.getAttribute("href"), url).href.split(/[?#]/)[0];
      if (seen.has(href)) continue;
      seen.add(href);
      const text = textOf(a).replace(/ /g, " ");
      const p = PRICE_RE.exec(text), q = QTY_RE.exec(text);
      out.push({
        url: href,
        text,
        price: p ? parseAmount(p[1] || p[2]) : null,
        qty: q ? +q[1] : null,
        sold: SOLD_RE.test(text),
      });
    }
    return out;
  };

  const isChallenge = (doc, status) => {
    if (status === 403 || status === 429) return "HTTP " + status;
    if (CHALLENGE_RE.test(doc.title || "")) return doc.title;
    const body = doc.body ? textOf(doc.body) : "";
    return body.length < 500 && CHALLENGE_RE.test(body) ? body : null;
  };

  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

  // Mode "frame": a hidden same-origin iframe, so listings rendered by
  // JavaScript are visible. Mode "fetch": plain HTML, used if framing is refused.
  let frame = null;
  const loadFrame = () => new Promise((resolve, reject) => {
    if (!frame) {
      frame = document.createElement("iframe");
      frame.setAttribute("sandbox", "allow-scripts allow-same-origin allow-forms");
      frame.setAttribute("aria-hidden", "true");
      frame.style.cssText = "position:fixed;left:-10000px;top:0;width:1200px;height:900px;border:0;";
      document.body.appendChild(frame);
    }
    let done = false;
    const finish = (fn, v) => { if (!done) { done = true; clearTimeout(to); fn(v); } };
    const to = setTimeout(() => finish(reject, new Error("timeout")), 30000);
    frame.onload = async () => {
      let doc = null;
      try { doc = frame.contentDocument; } catch (e) { /* cross-origin error page */ }
      if (!doc || !doc.body || doc.location.href === "about:blank") return finish(reject, new Error("blocked"));
      // Give client-side rendering time to add the listings.
      const start = Date.now();
      let last = -1;
      while (!done && Date.now() - start < 8000) {
        if (isChallenge(doc)) break;
        const n = doc.querySelectorAll(LINK_SEL).length;
        if (n > 0 && n === last && Date.now() - start > 1500) break;
        last = n;
        await sleep(500);
      }
      finish(resolve, { doc, status: 200 });
    };
    try {
      if (frame.contentWindow && frame.contentDocument && frame.contentDocument.location.href !== "about:blank") {
        frame.contentWindow.location.reload();
        return;
      }
    } catch (e) { /* fall through to src */ }
    frame.src = url;
  });

  const loadFetch = async () => {
    const r = await fetch(url, { credentials: "include", cache: "no-store" });
    const doc = new DOMParser().parseFromString(await r.text(), "text/html");
    return { doc, status: r.status };
  };

  // ---------- alarm ----------
  let audio = null;
  try { audio = new (window.AudioContext || window.webkitAudioContext)(); } catch (e) { /* no audio */ }
  const beep = (freq, at, dur) => {
    const o = audio.createOscillator(), g = audio.createGain();
    o.type = "square";
    o.frequency.value = freq;
    g.gain.setValueAtTime(0.25, audio.currentTime + at);
    g.gain.setValueAtTime(0, audio.currentTime + at + dur);
    o.connect(g).connect(audio.destination);
    o.start(audio.currentTime + at);
    o.stop(audio.currentTime + at + dur + 0.05);
  };
  const ring = () => {
    if (!audio) return;
    if (audio.state !== "running") audio.resume();
    beep(880, 0, 0.18); beep(660, 0.22, 0.18); beep(880, 0.44, 0.18);
  };
  if ("Notification" in window && Notification.permission === "default") {
    try { Notification.requestPermission(); } catch (e) { /* ignore */ }
  }

  // ---------- panel ----------
  const panel = document.createElement("div");
  panel.id = "ts-alert-panel";
  panel.style.cssText = "position:fixed;right:16px;bottom:16px;z-index:2147483647;width:320px;max-width:calc(100vw - 32px);" +
    "background:#fff;color:#111;border:2px solid #00b6f0;border-radius:12px;box-shadow:0 8px 24px rgba(0,0,0,.25);" +
    "font:14px/1.4 system-ui,sans-serif;padding:12px;";
  panel.innerHTML =
    '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">' +
    '<strong>🎟️ TicketSwap Alert</strong>' +
    '<button data-a="hide" title="Nascondi" style="border:0;background:none;font-size:18px;cursor:pointer">–</button></div>' +
    '<div data-r="cfg" style="color:#555"></div>' +
    '<div data-r="status" style="margin:6px 0"></div>' +
    '<div data-r="matches"></div>' +
    '<div style="display:flex;gap:6px;flex-wrap:wrap;margin-top:8px">' +
    '<button data-a="silence" style="display:none;background:#e5243b;color:#fff;border:0;border-radius:6px;padding:6px 10px;cursor:pointer">🔕 Ferma allarme</button>' +
    '<button data-a="test" style="border:1px solid #ccc;background:#fff;border-radius:6px;padding:6px 10px;cursor:pointer">🔊 Test suono</button>' +
    '<button data-a="stop" style="border:1px solid #ccc;background:#fff;border-radius:6px;padding:6px 10px;cursor:pointer">Stop</button></div>';
  document.body.appendChild(panel);
  const $ = (k) => panel.querySelector('[data-r="' + k + '"]');
  const btn = (k) => panel.querySelector('[data-a="' + k + '"]');
  $("cfg").textContent = "Trigger: ≤ " + maxPrice + " · " + quantity + " biglietto/i · ogni ~" + interval + "s";

  const state = { running: true, alarming: false, mode: null, alerted: new Set(), matches: [], checks: 0, error: null, panel };
  window.__tsAlert = state;
  const origTitle = document.title;
  let alarmTimer = null;

  const setStatus = (html, color) => {
    $("status").innerHTML = html;
    $("status").style.color = color || "#111";
  };

  const startAlarm = (items) => {
    state.alarming = true;
    btn("silence").style.display = "inline-block";
    panel.style.borderColor = "#e5243b";
    clearInterval(alarmTimer);
    let flip = false;
    ring();
    alarmTimer = setInterval(() => {
      ring();
      flip = !flip;
      document.title = flip ? "🔔 BIGLIETTO TROVATO!" : origTitle;
    }, 1200);
    if ("Notification" in window && Notification.permission === "granted") {
      const best = items[0];
      try {
        const n = new Notification("Biglietto a " + best.price + " su TicketSwap!", {
          body: best.text.slice(0, 120), requireInteraction: true,
        });
        n.onclick = () => { window.focus(); window.open(best.url, "_blank"); };
      } catch (e) { /* ignore */ }
    }
  };
  const silence = () => {
    state.alarming = false;
    clearInterval(alarmTimer);
    document.title = origTitle;
    btn("silence").style.display = "none";
    panel.style.borderColor = "#00b6f0";
  };
  const stop = (msg) => {
    state.running = false;
    clearTimeout(state.timer);
    if (msg) setStatus(msg, "#e5243b");
  };

  btn("hide").onclick = () => { panel.style.display = "none"; };
  btn("silence").onclick = silence;
  btn("test").onclick = ring;
  btn("stop").onclick = () => {
    stop();
    silence();
    if (frame) frame.remove();
    panel.remove();
    delete window.__tsAlert;
  };

  const renderMatches = () => {
    $("matches").innerHTML = "";
    for (const m of state.matches.slice(0, 5)) {
      const a = document.createElement("a");
      a.href = m.url;
      a.target = "_blank";
      a.rel = "noopener";
      a.textContent = "👉 " + m.price + (m.qty ? " · " + m.qty + " biglietto/i" : "") + " – apri e compra";
      a.style.cssText = "display:block;margin:4px 0;padding:6px 8px;background:#e8f8fe;border-radius:6px;color:#0077a8;font-weight:600;text-decoration:none";
      $("matches").appendChild(a);
    }
  };

  const load = async () => {
    if (state.mode === "fetch") return loadFetch();
    try {
      const r = await loadFrame();
      if (!state.mode) {
        state.mode = "frame";
        // The frame may not show listings that plain HTML does: compare once.
        if (!r.doc.querySelectorAll(LINK_SEL).length && !isChallenge(r.doc)) {
          const f = await loadFetch().catch(() => null);
          if (f && f.doc.querySelectorAll(LINK_SEL).length) {
            state.mode = "fetch";
            return f;
          }
        }
      }
      return r;
    } catch (e) {
      if (state.mode === "frame") throw e;
      state.mode = "fetch";
      if (frame) { frame.remove(); frame = null; }
      return loadFetch();
    }
  };

  let failures = 0;
  const tick = async () => {
    if (!state.running) return;
    try {
      const { doc, status } = await load();
      const challenge = isChallenge(doc, status);
      if (challenge) {
        stop("⛔ TicketSwap chiede una verifica. Monitoraggio fermato: ricarica la pagina a mano e, se tutto è ok, riattiva il segnalibro.");
        return;
      }
      failures = 0;
      state.checks++;
      const all = collect(doc);
      const matches = all
        .filter((l) => !l.sold && l.price != null && l.price <= maxPrice && (l.qty == null || l.qty >= quantity))
        .sort((a, b) => a.price - b.price);
      state.matches = matches;
      renderMatches();
      const fresh = matches.filter((m) => !state.alerted.has(m.url));
      fresh.forEach((m) => state.alerted.add(m.url));
      if (fresh.length) startAlarm(fresh);
      const live = document.querySelectorAll(LINK_SEL).length;
      const warn = !all.length && live ? ' <span style="color:#b26a00">(non riesco a leggere gli annunci di questa pagina)</span>' : "";
      setStatus(
        (matches.length ? "🔔 <b>" + matches.length + (matches.length === 1 ? " annuncio" : " annunci") + " al tuo prezzo!</b>" : "👀 In ascolto…") +
        "<br><small>" + all.length + " annunci letti · controllo #" + state.checks + " alle " +
        new Date().toLocaleTimeString() + "</small>" + warn,
      );
    } catch (e) {
      failures++;
      if (failures >= 3) {
        stop("⚠️ Errore di caricamento ripetuto (" + e.message + "). Monitoraggio fermato.");
        return;
      }
      setStatus("⚠️ Errore (" + e.message + "), riprovo…", "#b26a00");
    }
    if (state.running) state.timer = setTimeout(tick, interval * 1000 * (0.8 + Math.random() * 0.4));
  };

  setStatus("Avvio…");
  tick();
})();
