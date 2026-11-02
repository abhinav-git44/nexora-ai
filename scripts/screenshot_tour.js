// Visits every major screen as the seeded demo owner, captures screenshots and console errors.
// Usage: node scripts/screenshot_tour.js [baseUrl]
const { chromium } = require("playwright");
const path = require("path");
const BASE = process.argv[2] || "http://localhost:3000";
const OUT = path.join(__dirname, "..", "docs", "screenshots");
const PAGES = [
  ["01-landing", "/", false], ["02-pricing", "/pricing", false], ["03-login", "/login", false],
  ["10-home", "/app"], ["11-assistant", "/app/assistant"], ["13-knowledge", "/app/knowledge"], ["15-agents", "/app/agents"],
  ["17-workflows", "/app/workflows"], ["19-data", "/app/data"], ["21-tasks", "/app/tasks"], ["22-analytics", "/app/analytics"],
  ["23-approvals", "/app/approvals"], ["24-integrations", "/app/integrations"], ["25-billing", "/app/billing"], ["26-settings-members", "/app/settings/members"],
  ["27-settings-audit", "/app/settings/audit"], ["28-notifications", "/app/notifications"],
];
(async () => {
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 });
  const page = await ctx.newPage();
  const errors = [];
  page.on("console", (m) => { if (m.type() === "error") errors.push(`${page.url()} :: ${m.text()}`); });
  page.on("pageerror", (e) => errors.push(`${page.url()} :: PAGEERROR ${e.message}`));
  for (const [name, url, auth] of PAGES.slice(0, 3)) { await page.goto(BASE + url, { waitUntil: "networkidle" }); await page.screenshot({ path: `${OUT}/${name}.png`, fullPage: name !== "01-landing" }); }
  await page.fill("#email", "demo.owner@example.com"); await page.fill("#password", "DemoPassw0rd!"); await page.click("button[type=submit]");
  await page.waitForURL("**/app**", { timeout: 15000 });
  for (const [name, url] of PAGES.slice(3)) {
    await page.goto(BASE + url, { waitUntil: "networkidle" }); await page.waitForTimeout(1800);
    await page.screenshot({ path: `${OUT}/${name}.png` });
  }
  // detail screens
  await page.goto(BASE + "/app/assistant", { waitUntil: "networkidle" });
  const first = page.locator("aside a[href^='/app/assistant/']").first();
  if (await first.count()) { await first.click(); await page.waitForLoadState("networkidle"); await page.waitForTimeout(800); await page.screenshot({ path: `${OUT}/12-assistant-conversation.png` }); }
  await page.goto(BASE + "/app/knowledge", { waitUntil: "networkidle" });
  await page.locator("table a[href^='/app/knowledge/']").first().click(); await page.waitForLoadState("networkidle"); await page.waitForTimeout(600);
  await page.screenshot({ path: `${OUT}/14-knowledge-document.png` });
  await page.goto(BASE + "/app/agents", { waitUntil: "networkidle" });
  await page.locator("a[href^='/app/agents/']").first().click(); await page.waitForLoadState("networkidle");
  await page.getByRole("tab", { name: /Runs/ }).click(); await page.waitForTimeout(400);
  const row = page.locator("tbody tr").first(); if (await row.count()) { await row.click(); await page.waitForTimeout(1200); }
  await page.screenshot({ path: `${OUT}/16-agent-run.png`, fullPage: true });
  await page.goto(BASE + "/app/workflows", { waitUntil: "networkidle" });
  await page.locator("table a[href^='/app/workflows/']").first().click(); await page.waitForLoadState("networkidle"); await page.waitForTimeout(1500);
  await page.screenshot({ path: `${OUT}/18-workflow-builder.png` });
  await page.goto(BASE + "/app/data", { waitUntil: "networkidle" });
  await page.locator("table a[href^='/app/data/']").first().click(); await page.waitForLoadState("networkidle");
  await page.getByRole("button", { name: "What is the monthly revenue trend?", exact: true }).click(); await page.waitForTimeout(2000);
  await page.screenshot({ path: `${OUT}/20-data-query.png`, fullPage: true });
  // mobile
  const m = await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2, storageState: await ctx.storageState() });
  const mp = await m.newPage();
  mp.on("pageerror", (e) => errors.push(`mobile ${mp.url()} :: PAGEERROR ${e.message}`));
  for (const [name, url] of [["30-mobile-home", "/app"], ["31-mobile-tasks", "/app/tasks"], ["32-mobile-landing", "/"]]) {
    await mp.goto(BASE + url, { waitUntil: "networkidle" }); await mp.waitForTimeout(800); await mp.screenshot({ path: `${OUT}/${name}.png` });
  }
  // admin
  const a = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const ap = await a.newPage();
  await ap.goto(BASE + "/login"); await ap.fill("#email", "admin@example.com"); await ap.fill("#password", "DemoPassw0rd!"); await ap.click("button[type=submit]");
  await ap.waitForURL("**/app**"); await ap.goto(BASE + "/admin", { waitUntil: "networkidle" }); await ap.waitForTimeout(800); await ap.screenshot({ path: `${OUT}/40-admin-console.png` });
  // dark mode
  const d = await browser.newContext({ viewport: { width: 1440, height: 900 }, colorScheme: "dark", storageState: await ctx.storageState() });
  const dp = await d.newPage(); await dp.goto(BASE + "/app/analytics", { waitUntil: "networkidle" }); await dp.waitForTimeout(1800); await dp.screenshot({ path: `${OUT}/50-dark-analytics.png` });
  await browser.close();
  console.log(JSON.stringify({ screenshots: "ok", console_errors: errors }, null, 2));
})().catch((e) => { console.error(e); process.exit(1); });
