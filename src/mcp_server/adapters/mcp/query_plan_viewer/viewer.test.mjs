import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { parseHTML } from "linkedom";
import { createViewer } from "./viewer.mjs";

const fixture = {
  operation_id: "fixture-operation",
  data: { total_cost_estimate: 42, rows_estimate: 12, estimates_only: true,
    plan: { "Node Type": "Nested Loop", "Total Cost": 42, "Plan Rows": 12,
      Plans: [{ "Node Type": "Seq Scan", "Relation Name": "orders", "Total Cost": 20, "Plan Rows": 100, Filter: "status_id = 1", "Future Property": "preserved" }] } },
};
function setup() {
  const { document, window } = parseHTML(readFileSync("index.html", "utf8"));
  const selected = [];
  const render = createViewer(document, (value) => selected.push(value));
  return { document, window, selected, render };
}

test("tree, estimates, node details and concise model context", () => {
  const { document, window, selected, render } = setup();
  render(fixture);
  assert.match(document.getElementById("summary").textContent, /Estimated cost 42/);
  const nodes = document.querySelectorAll(".node");
  assert.equal(nodes.length, 2);
  assert.equal(selected.length, 0);
  nodes[1].dispatchEvent(new window.Event("click"));
  assert.match(document.getElementById("details").textContent, /Future Propertypreserved/);
  assert.match(document.getElementById("warnings").textContent, /may be appropriate/);
  assert.equal(nodes[1].getAttribute("aria-pressed"), "true");
  assert.equal(selected[0].path, "0.0");
  assert.equal(selected[0].estimates_only, true);
  assert.equal(selected[0].operation_id, fixture.operation_id);
});

test("untrusted plan values and errors render as text", () => {
  const { document, render } = setup();
  const malicious = structuredClone(fixture);
  malicious.data.plan["Node Type"] = '<img src=x onerror="alert(1)">';
  render(malicious);
  assert.equal(document.querySelectorAll("img").length, 0);
  assert.match(document.getElementById("raw").textContent, /onerror/);
  render({ error: { message: "Database unavailable." } });
  assert.equal(document.querySelectorAll(".node").length, 0);
  assert.equal(document.getElementById("raw").textContent, "");
  assert.match(document.getElementById("summary").textContent, /unavailable/);
  render({ data: { ...fixture.data, estimates_only: false } });
  assert.equal(document.querySelectorAll(".node").length, 0);
});

test("arrow and home/end navigation preserves button activation", () => {
  const { document, window, render } = setup();
  render(fixture);
  const buttons = [...document.querySelectorAll(".node")];
  let active = buttons[0];
  Object.defineProperty(document, "activeElement", { get: () => active });
  buttons.forEach(button => { button.focus = () => { active = button; }; });
  for (const [key, expected] of [["ArrowDown", 1], ["Home", 0], ["End", 1], ["ArrowUp", 0]]) {
    const event = new window.Event("keydown", { bubbles: true, cancelable: true });
    event.key = key; active.dispatchEvent(event);
    assert.equal(active, buttons[expected]);
  }
});

test("cyclic and oversized plans bound rendering work", () => {
  const { document, render } = setup();
  const big = structuredClone(fixture);
  big.data.plan.Plans = Array.from({ length: 2001 }, () => ({ "Node Type": "Result" }));
  big.data.plan.Plans.push(big.data.plan);
  render(big);
  assert.equal(document.querySelectorAll(".node").length, 2000);
  assert.match(document.getElementById("summary").textContent, /capped/);
});
