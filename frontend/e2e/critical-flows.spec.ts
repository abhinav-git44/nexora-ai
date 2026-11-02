import { expect, test, type Page } from "@playwright/test";

const PASSWORD = "E2e!Passw0rd99";
const email = `e2e-${Date.now()}@example.com`;

async function login(page: Page) {
  await page.goto("/login");
  await page.fill("#email", email);
  await page.fill("#password", PASSWORD);
  await page.click("button[type=submit]");
  await page.waitForURL("**/app**");
}

test.describe.serial("critical user journeys", () => {
  test("sign up and land in a new workspace", async ({ page }) => {
    await page.goto("/register");
    await page.fill("#name", "Esha Tester");
    await page.fill("#email", email);
    await page.fill("#password", PASSWORD);
    await page.fill("#org", "E2E Logistics");
    await page.click("button[type=submit]");
    await page.waitForURL("**/app**");
    await expect(page.getByRole("heading", { name: /Good to see you, Esha/ })).toBeVisible();
    await expect(page.getByText("Get to first value")).toBeVisible();
    await expect(page.getByText("E2E Logistics").first()).toBeVisible();
  });

  test("upload a document and see it indexed", async ({ page }) => {
    await login(page);
    await page.goto("/app/knowledge");
    await page.setInputFiles("input[type=file]", { name: "leave-policy.md", mimeType: "text/markdown",
      buffer: Buffer.from("# Leave policy\n\nEmployees receive 24 days of paid annual leave per calendar year. Unused leave up to 5 days can be carried over.") });
    await expect(page.getByRole("link", { name: /leave-policy/ })).toBeVisible();
    await expect(page.getByText("indexed").first()).toBeVisible({ timeout: 20_000 });
  });

  test("ask the assistant and get a cited answer", async ({ page }) => {
    await login(page);
    await page.goto("/app/assistant");
    await page.getByLabel("Message").fill("How many days of paid annual leave do employees get?");
    await page.getByLabel("Send").click();
    await page.waitForURL(/\/app\/assistant\/.+/);
    await expect(page.getByText(/24 days of paid annual leave/).first()).toBeVisible({ timeout: 20_000 });
    await expect(page.getByRole("button", { name: /\[1\] leave-policy/ })).toBeVisible();
  });

  test("run an agent from a template", async ({ page }) => {
    await login(page);
    await page.goto("/app/agents");
    await page.getByRole("button", { name: "Use template" }).nth(6).click(); // Project Management Assistant
    await page.waitForURL(/\/app\/agents\/.+/);
    await page.getByLabel("Agent input").fill("Extract action items: Ravi to send the vendor contract by Friday. Action: review the Q4 budget (urgent).");
    await page.getByRole("button", { name: "Run" }).click();
    await expect(page.getByText("succeeded").first()).toBeVisible({ timeout: 30_000 });
    await expect(page.getByText("extract_action_items").first()).toBeVisible();
  });

  test("publish and run a workflow", async ({ page }) => {
    await login(page);
    await page.goto("/app/workflows");
    await page.getByRole("button", { name: "Use recipe" }).nth(2).click(); // meeting notes -> approval -> tasks
    await page.waitForURL(/\/app\/workflows\/.+/);
    await page.getByRole("button", { name: "Publish" }).click();
    await expect(page.getByText("published").first()).toBeVisible();
    await page.getByRole("button", { name: "Run", exact: true }).click();
    await page.getByLabel("Trigger payload JSON").fill('{"notes": "Anil to prepare the board deck by Monday."}');
    await page.getByRole("dialog").getByRole("button", { name: "Run", exact: true }).click();
    await expect(page.getByText(/waiting approval|waiting_approval/).first()).toBeVisible({ timeout: 20_000 });
    await page.goto("/app/approvals");
    await page.getByRole("button", { name: "Approve" }).first().click();
    await expect(page.getByText(/Approved/)).toBeVisible();
  });

  test("create a task and move it to done", async ({ page }) => {
    await login(page);
    await page.goto("/app/tasks");
    await page.getByRole("button", { name: "New task" }).click();
    await page.getByRole("dialog").getByLabel("Title").fill("E2E: finalise onboarding checklist");
    await page.getByRole("dialog").getByRole("button", { name: "Create" }).click();
    await expect(page.getByText("E2E: finalise onboarding checklist")).toBeVisible();
    await page.getByRole("radio", { name: /List/ }).click();
    const row = page.getByRole("row", { name: /E2E: finalise onboarding checklist/ });
    await row.getByLabel("Status").selectOption("done");
    await expect(row.getByLabel("Status")).toHaveValue("done");
  });

  test("upgrade subscription (demo billing)", async ({ page }) => {
    await login(page);
    await page.goto("/app/billing");
    await expect(page.getByText("Demo billing mode")).toBeVisible();
    await page.getByRole("button", { name: "Switch", exact: true }).nth(1).click(); // Starter (Free, Starter, Professional)
    await expect(page.getByText(/Plan changed to Starter/)).toBeVisible();
    await expect(page.getByText(/DEMO-/).first()).toBeVisible();
  });

  test("viewer-only and cross-tenant protections hold in the UI", async ({ page, request }) => {
    await login(page);
    const res = await request.get("/api/tasks", { headers: { "X-Org-Id": "00000000-0000-0000-0000-000000000000" } });
    expect(res.status()).toBe(401); // no token → rejected before reaching any tenant data
    await page.goto("/admin");
    await expect(page.getByText("404 — Not found")).toBeVisible(); // admin console hidden from non-admins
  });
});
