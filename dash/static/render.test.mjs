// node --test dash/static/render.test.mjs : render functions on tests/fixtures/dash_state.json
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import * as r from "./render.mjs";

const state = JSON.parse(readFileSync(new URL("../../tests/fixtures/dash_state.json", import.meta.url), "utf8"));

function text(node) {
  if (typeof node === "string") return node;
  return node.kids.map(text).join(" ");
}
function find(node, pred, out = []) {
  if (typeof node === "string") return out;
  if (pred(node)) out.push(node);
  for (const k of node.kids) find(k, pred, out);
  return out;
}

test("needs-you lists the waiting session, the stale machine and the open PR", () => {
  const kinds = r.needsYou(state).map((i) => i.kind).sort();
  assert.deepEqual(kinds, ["PR", "stale", "waiting"]);
  const t = text(r.renderNeeds(state));
  assert.match(t, /Proceed\? \(y\/n\)/);
  assert.match(t, /alfred/);
});

test("overview has two machine cards, the stale one greyed, and two projects", () => {
  const v = r.renderOverview(state);
  const machines = find(v, (n) => n.cls.startsWith("card machine"));
  assert.equal(machines.length, 2);
  assert.equal(machines.filter((m) => m.cls.includes("stale")).length, 1);
  assert.equal(find(v, (n) => n.cls.startsWith("card project")).length, 2);
});

test("project alpha links the open PR and is needs-you", () => {
  const alpha = r.projects(state).find((p) => p.name === "alpha");
  assert.equal(r.prsFor(state, alpha).length, 1);
  assert.equal(r.projectState(alpha, state), "needs");
});

test("sessions view shows the snippet only when expanded, as plain text", () => {
  const closed = r.renderSessions(state, []);
  assert.equal(find(closed, (n) => n.cls === "snippet").length, 0);
  const open = r.renderSessions(state, ["laptop/s1"]);
  const pre = find(open, (n) => n.cls === "snippet");
  assert.equal(pre.length, 1);
  assert.equal(pre[0].kids[0], "line one\n<b>not html</b>");
});

test("empty state renders without throwing", () => {
  for (const f of Object.values(r.VIEWS)) assert.ok(f({}, []));
});

test("a missing machine card tells how to register; a stale one shows its age", () => {
  const base = { role: "node", rep: {} };
  const miss = text(r.machineCard({ ...base, name: "pi", status: "missing", age_s: null }));
  assert.match(miss, /never reported: run `friday nodes --setup pi` on the master/);
  const stale = text(r.machineCard({ ...base, name: "alfred", status: "stale", age_s: 7200 }));
  assert.match(stale, /stale, seen .* ago/);
});
