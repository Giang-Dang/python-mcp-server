const number = (value) => typeof value === "number" && Number.isFinite(value)
  ? value.toLocaleString("en-US", { maximumFractionDigits: 2 }) : "Unknown";
const json = (value) => {
  try { return JSON.stringify(value, null, 2); }
  catch { return "Node JSON cannot be displayed. Inspect the original tool result."; }
};

export function warningsFor(node) {
  const warnings = [];
  if (node["Node Type"] === "Seq Scan") warnings.push("Sequential scan: may be appropriate for this table and selectivity. Check evidence before suggesting an index.");
  if ((node["Node Type"] || "").includes("Nested Loop")) warnings.push("Nested loop: verify estimated input rows and repeated work. This is a hypothesis, not a measured bottleneck.");
  if (node["Filter"]) warnings.push("Filter present: rows removed and actual selectivity are unknown without execution evidence.");
  return warnings;
}

export function createViewer(document, onSelect = () => {}) {
  const tree = document.getElementById("tree");
  const summary = document.getElementById("summary");
  const details = document.getElementById("details");
  const warnings = document.getElementById("warnings");
  const raw = document.getElementById("raw");
  let buttons = [];

  function select(node, path, button, operationId, notify) {
    for (const b of buttons) b.setAttribute("aria-pressed", String(b === button));
    document.getElementById("node-title").textContent = node["Node Type"] || "Unknown node";
    details.replaceChildren();
    for (const [key, value] of Object.entries(node)) {
      if (key === "Plans") continue;
      const dt = document.createElement("dt");
      const dd = document.createElement("dd");
      dt.textContent = key;
      dd.textContent = typeof value === "object" ? json(value) : String(value);
      details.append(dt, dd);
    }
    warnings.replaceChildren();
    for (const text of warningsFor(node)) {
      const li = document.createElement("li"); li.textContent = text; warnings.append(li);
    }
    raw.textContent = json(node);
    if (notify) onSelect({ operation_id: operationId, path, node_type: node["Node Type"], total_cost_estimate: node["Total Cost"], rows_estimate: node["Plan Rows"], estimates_only: true });
  }

  tree.addEventListener("keydown", (event) => {
    const index = buttons.indexOf(document.activeElement || event.target);
    const target = event.key === "ArrowDown" ? Math.min(index + 1, buttons.length - 1)
      : event.key === "ArrowUp" ? Math.max(index - 1, 0)
      : event.key === "Home" ? 0 : event.key === "End" ? buttons.length - 1 : null;
    if (target !== null && buttons[target]) { event.preventDefault(); buttons[target].focus(); }
  });

  return function render(envelope) {
    tree.replaceChildren(); details.replaceChildren(); warnings.replaceChildren(); raw.textContent = ""; buttons = [];
    document.getElementById("node-title").textContent = "Node details";
    const data = envelope?.data;
    if (envelope?.error || !data?.plan || data.estimates_only !== true) {
      summary.textContent = envelope?.error?.message || "No valid estimates-only plan is available.";
      return;
    }
    summary.textContent = `Estimated cost ${number(data.total_cost_estimate)} | Estimated rows ${number(data.rows_estimate)} | Operation ${envelope.operation_id || "unknown"}`;
    // Iterative traversal bounds work for unusual/deep plans without recursion overflow.
    const stack = [{ node: data.plan, parent: tree, path: "0" }];
    const seen = new Set();
    while (stack.length && buttons.length < 2000) {
      const { node, parent, path } = stack.pop();
      if (!node || typeof node !== "object" || seen.has(node)) continue;
      seen.add(node);
      const li = document.createElement("li");
      const button = document.createElement("button"); button.type = "button"; button.className = "node"; button.setAttribute("aria-pressed", "false");
      const label = document.createElement("span");
      label.textContent = `${node["Node Type"] || "Unknown node"}${node["Relation Name"] ? ` / ${node["Relation Name"]}` : ""}`;
      const estimates = document.createElement("span"); estimates.className = "estimate";
      estimates.textContent = `Cost ${number(node["Total Cost"])} | Rows ${number(node["Plan Rows"])}`;
      button.append(label, estimates); li.append(button); parent.append(li); buttons.push(button);
      button.addEventListener("click", () => select(node, path, button, envelope.operation_id, true));
      if (buttons.length === 1) select(node, path, button, envelope.operation_id, false);
      if (Array.isArray(node.Plans) && node.Plans.length) {
        const children = document.createElement("ul"); li.append(children);
        for (let i = node.Plans.length - 1; i >= 0; i--) stack.push({ node: node.Plans[i], parent: children, path: `${path}.${i}` });
      }
    }
    if (stack.length) summary.textContent += " | Display capped at 2000 nodes; inspect the original tool JSON for the full plan.";
  };
}
