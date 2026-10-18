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
