// Shared helpers, inlined by the generator into each bookmarklet.
const PRICE_RE = /(?:[€£$]|EUR|GBP|USD|CHF|DKK|SEK|NOK|PLN)\s*(\d{1,3}(?:[.,\s]\d{3})*(?:[.,]\d{1,2})?|\d+(?:[.,]\d{1,2})?)|(\d{1,3}(?:[.,\s]\d{3})*(?:[.,]\d{1,2})?|\d+(?:[.,]\d{1,2})?)\s*(?:[€£$]|EUR|GBP|USD|CHF)/i;
const QTY_RE = /(\d+)\s*(?:x\s*)?(?:tickets?|biglietti|biglietto|kaarten|kaart|billets?|entradas?|karten)\b/i;
const SOLD_RE = /\b(sold|venduto|venduti|verkocht|verkauft|vendu|vendido)\b/i;
const CHALLENGE_RE = /captcha|are you human|verify you are|verifying|unable to verify|access denied|too many requests|verifica in corso|impossibile verificare/i;
const LINK_SEL = 'a[href*="/listing/"]';

const parseAmount = (raw) => {
  let s = raw.replace(/[\s\u00a0]/g, "");
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

const textOf = (el) => {
  const out = [], w = el.ownerDocument.createTreeWalker(el, NodeFilter.SHOW_TEXT);
  let n;
  while ((n = w.nextNode())) {
    const t = n.nodeValue.trim();
    if (t) out.push(t);
  }
  return out.join(" ");
};

const isChallenge = (doc, status) => {
  if (status === 403 || status === 429) return "HTTP " + status;
  if (CHALLENGE_RE.test(doc.title || "")) return doc.title;
  const body = doc.body ? textOf(doc.body) : "";
  return body.length < 500 && CHALLENGE_RE.test(body) ? body : null;
};

const fmt = (n) => {
  return n.toLocaleString(document.documentElement.lang || undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
};

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// Loads a fresh copy of an event page in the background.
// Mode "frame": a hidden same-origin iframe, so listings rendered by
// JavaScript are visible. Mode "fetch": plain HTML, used if framing is refused.
const makeLoader = (url) => {
  const self = { mode: null };
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

  const load = async () => {
    if (self.mode === "fetch") return loadFetch();
    try {
      const r = await loadFrame();
      if (!self.mode) {
        self.mode = "frame";
        // The frame may not show listings that plain HTML does: compare once.
        if (!r.doc.querySelectorAll(LINK_SEL).length && !isChallenge(r.doc)) {
          const f = await loadFetch().catch(() => null);
          if (f && f.doc.querySelectorAll(LINK_SEL).length) {
            self.mode = "fetch";
            return f;
          }
        }
      }
      return r;
    } catch (e) {
      if (self.mode === "frame") throw e;
      self.mode = "fetch";
      if (frame) { frame.remove(); frame = null; }
      return loadFetch();
    }
  };

  self.load = load;
  self.dispose = () => { if (frame) { frame.remove(); frame = null; } };
  return self;
};
