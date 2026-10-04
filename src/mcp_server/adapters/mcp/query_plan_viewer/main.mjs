import { App } from "@modelcontextprotocol/ext-apps";
import { createViewer } from "./viewer.mjs";

const app = new App({ name: "Shop query plan", version: "1.0.0" }, {});
const status = document.getElementById("status");
const render = createViewer(document, async (selection) => {
  try {
    await app.updateModelContext({ content: [{ type: "text", text: `Selected plan node (estimates only): ${JSON.stringify(selection)}` }] });
    status.textContent = "Selected node shared with the conversation.";
  } catch { status.textContent = "Node selected. This host could not receive the selection."; }
});
app.ontoolresult = (result) => {
  const envelope = result.structuredContent;
  render(envelope);
  status.textContent = "";
};
app.ontoolcancelled = () => { status.textContent = "Explain was cancelled."; };
app.connect().catch(() => { status.textContent = "Open this viewer in a host that supports MCP Apps."; });
