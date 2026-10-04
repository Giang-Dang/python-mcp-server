import { build } from "esbuild";
import { readFile, writeFile } from "node:fs/promises";

const result = await build({
  entryPoints: ["main.mjs"], bundle: true, write: false, format: "iife",
  target: "es2022", minify: true, charset: "ascii", legalComments: "none",
});
const template = await readFile("index.html", "utf8");
// A dependency's string literal must never terminate the enclosing HTML script.
const script = result.outputFiles[0].text.replace(/<\/script/gi, "<\\/script");
await writeFile("viewer.html", template.replace("<!-- APP_SCRIPT -->", `<script>${script}</script>`));
console.log(`Built viewer.html (${Buffer.byteLength(script)} script bytes; no external assets).`);
