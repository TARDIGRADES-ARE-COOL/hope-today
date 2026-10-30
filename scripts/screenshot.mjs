// Screenshot a page at an exact size with headless Chrome:  node scripts/screenshot.mjs <url> <out.png> <width> <height>
// Used for the link-preview image (harness/og_image.py). Node's built-in WebSocket talks to Chrome.
import { spawn } from "node:child_process";
import { writeFileSync, mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const [url, out, width = "1200", height = "630"] = process.argv.slice(2);
const sleep = ms => new Promise(r => setTimeout(r, ms));
const chrome = spawn("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", ["--headless=new",
  "--remote-debugging-port=9361", "--hide-scrollbars", `--user-data-dir=${mkdtempSync(join(tmpdir(), "shot-"))}`,
  "about:blank"], { stdio: "ignore" });
try {
  await sleep(1500);
  const page = (await (await fetch("http://127.0.0.1:9361/json")).json()).find(t => t.type === "page");
  const ws = new WebSocket(page.webSocketDebuggerUrl);
  await new Promise(r => ws.onopen = r);
  let id = 0; const waiting = {};
  ws.onmessage = e => { const m = JSON.parse(e.data); if (m.id) waiting[m.id]?.(m.result); };
  const send = (method, params = {}) => new Promise(r => { waiting[++id] = r; ws.send(JSON.stringify({ id, method, params })); });
  await send("Emulation.setDeviceMetricsOverride", { width: +width, height: +height, deviceScaleFactor: 1, mobile: false });
  await send("Page.enable");
  await send("Page.navigate", { url });
  await sleep(4000);                              // fonts and the pixel dawn
  writeFileSync(out, Buffer.from((await send("Page.captureScreenshot", { format: "png" })).data, "base64"));
  ws.close();
} finally {
  chrome.kill();
}
