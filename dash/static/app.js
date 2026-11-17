// friday dash: poll /api/state and draw the tab views. All state text goes in through
// textContent; element trees come from render.mjs.
import { TABS, VIEWS, needsYou, allSessions, ago, h } from "./render.mjs";

let state = null;
let tab = "overview";
const expanded = new Set();
let fetchedAt = 0;
const POLL_MS = 15000, STALE_MS = 45000;

// localStorage can throw (private mode, blocked storage); every access is guarded.
function load(key) { try { return window.localStorage.getItem(key); } catch (e) { return null; } }
function save(key, val) { try { window.localStorage.setItem(key, val); } catch (e) { /* ignore */ } }
(function restore() {
  const t = load("friday.tab");
  if (t && TABS.includes(t)) tab = t;
  try { for (const k of JSON.parse(load("friday.expanded") || "[]")) if (typeof k === "string") expanded.add(k); } catch (e) { /* ignore */ }
})();

// "updated Ns ago"; the page greys out its data when the last good fetch is old.
let lastError = "";
function tickUpdated() {
  const failed = lastError;
  const el = document.getElementById("updated");
  if (!fetchedAt) return;
  const age = Date.now() - fetchedAt, stale = age > STALE_MS;
  el.textContent = "updated " + ago(age / 1000) + " ago" + (failed ? " (update failed: " + failed + ")" : "");
  el.classList.toggle("stale", stale || !!failed);
  document.getElementById("main").classList.toggle("stale-data", stale);
}

export function build(node) {
  if (typeof node === "string") return document.createTextNode(node);
  const el = document.createElement(node.tag);
  if (node.cls) el.className = node.cls;
  for (const [k, v] of Object.entries(node.attrs)) el.setAttribute(k, v);
  for (const kid of node.kids) el.appendChild(build(kid));
  return el;
}

function drawTabs() {
  const nav = document.getElementById("tabs");
  const counts = { overview: needsYou(state || {}).length, sessions: allSessions(state || {}).length };
  nav.replaceChildren(...TABS.map((t) => {
    const b = build(h("button", { cls: "tab", role: "tab", "data-tab": t, "aria-selected": String(t === tab) }, t[0].toUpperCase() + t.slice(1),
      counts[t] ? h("span", { cls: "count" + (t === "overview" ? " warn" : "") }, String(counts[t])) : null));
    b.addEventListener("click", () => { tab = t; save("friday.tab", t); draw(); });
    return b;
  }));
}

function draw() {
  drawTabs();
  const main = document.getElementById("main");
  if (!state) { main.replaceChildren(build(h("p", { cls: "empty" }, "Loading..."))); return; }
  const view = build(VIEWS[tab](state, [...expanded]));
  for (const row of view.querySelectorAll("tr.row")) {
    const toggle = () => { const k = row.dataset.key; expanded.has(k) ? expanded.delete(k) : expanded.add(k); save("friday.expanded", JSON.stringify([...expanded])); draw(); };
    row.addEventListener("click", toggle);
    row.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); toggle(); } });
  }
  main.replaceChildren(view);
}

async function poll() {
  try {
    const r = await fetch("/api/state", { cache: "no-store" });
    if (!r.ok) throw new Error("HTTP " + r.status);
    state = await r.json();
  } catch (e) {
    lastError = e.message;
    if (!fetchedAt) document.getElementById("updated").textContent = "update failed: " + e.message;
    else tickUpdated();
    return;
  }
  lastError = "";
  fetchedAt = Date.now();
  tickUpdated();
  draw();
}

draw();
poll();
setInterval(poll, POLL_MS);
setInterval(() => tickUpdated(), 1000);
