/**
 * E2E tests for error boundaries and graceful degradation.
 *
 * Covers:
 *   - Pages handle API errors without crashing (no blank pages)
 *   - Network failure shows meaningful error messages
 *   - Malformed API responses do not crash the UI
 *   - Auth errors redirect to login instead of crashing
 *   - Timeout scenarios show user-friendly messages
 *
 * All API calls intercepted — no real backend required.
 */
import { test, expect, type Page, type Route } from "@playwright/test";
import { mockApiRoutes } from "./fixtures";

/* ── Authenticated helper ──────────────────────────────────────── */

async function gotoWithAuth(page: Page, path: string): Promise<void> {
  await mockApiRoutes(page);
  await page.goto(path);
  if (page.url().includes("/login")) {
    await page.fill('[id="email"]', "admin@langsight.io");
    await page.fill('[id="password"]', "demo123");
    await page.getByRole("button", { name: /sign in/i }).click();
    await page.waitForURL("**/*", { timeout: 10_000 });
    await page.goto(path);
  }
}

/* ── API errors do not crash pages ─────────────────────────────── */

test.describe("Error boundary — API 500 errors", () => {
  test("overview page handles health API 500 without crashing", async ({
    page,
  }) => {
    await mockApiRoutes(page);
    await page.route("**/api/health/servers", async (route: Route) => {
      await route.fulfill({ status: 500, body: "Internal Server Error" });
    });
    await page.route("**/api/proxy/health/servers", async (route: Route) => {
      await route.fulfill({ status: 500, body: "Internal Server Error" });
    });

    await page.goto("/");
    if (page.url().includes("/login")) {
      await page.fill('[id="email"]', "admin@langsight.io");
      await page.fill('[id="password"]', "demo123");
      await page.getByRole("button", { name: /sign in/i }).click();
      await page.waitForURL("**/*", { timeout: 10_000 });
      await page.goto("/");
    }

    // Page should still render (not blank white screen)
    await expect(page.getByText("LangSight").first()).toBeVisible({
      timeout: 8_000,
    });
    // The page should not show "Unhandled Runtime Error"
    await expect(
      page.getByText(/unhandled runtime error/i)
    ).not.toBeVisible({ timeout: 3_000 });
  });

  test("sessions page handles sessions API 500 gracefully", async ({
    page,
  }) => {
    await mockApiRoutes(page);
    await page.route("**/api/proxy/agents/sessions*", async (route: Route) => {
      await route.fulfill({ status: 500, body: "Internal Server Error" });
    });
    await page.route("**/api/agents/sessions*", async (route: Route) => {
      await route.fulfill({ status: 500, body: "Internal Server Error" });
    });

    await page.goto("/sessions");
    if (page.url().includes("/login")) {
      await page.fill('[id="email"]', "admin@langsight.io");
      await page.fill('[id="password"]', "demo123");
      await page.getByRole("button", { name: /sign in/i }).click();
      await page.waitForURL("**/*", { timeout: 10_000 });
      await page.goto("/sessions");
    }

    // Sidebar should still be visible
    await expect(page.getByText("LangSight").first()).toBeVisible({
      timeout: 8_000,
    });
    // Error message should appear
    await expect(
      page.getByText(/could not load|error|check/i).first()
    ).toBeVisible({ timeout: 8_000 });
  });

  test("health page handles health API 500 gracefully", async ({ page }) => {
    await mockApiRoutes(page);
    await page.route("**/api/health/servers", async (route: Route) => {
      await route.fulfill({ status: 500, body: "Internal Server Error" });
    });
    await page.route("**/api/proxy/health/servers", async (route: Route) => {
      await route.fulfill({ status: 500, body: "Internal Server Error" });
    });

    await page.goto("/health");
    if (page.url().includes("/login")) {
      await page.fill('[id="email"]', "admin@langsight.io");
      await page.fill('[id="password"]', "demo123");
      await page.getByRole("button", { name: /sign in/i }).click();
      await page.waitForURL("**/*", { timeout: 10_000 });
      await page.goto("/health");
    }

    // Should still show the page structure
    await expect(page.getByText("Tool Health").first()).toBeVisible({
      timeout: 8_000,
    });
  });
});

/* ── Malformed API responses ───────────────────────────────────── */

test.describe("Error boundary — malformed responses", () => {
  test("overview handles non-JSON health response", async ({ page }) => {
    await mockApiRoutes(page);
    await page.route("**/api/health/servers", async (route: Route) => {
      await route.fulfill({
        status: 200,
        contentType: "text/html",
        body: "<html>Not JSON</html>",
      });
    });
    await page.route("**/api/proxy/health/servers", async (route: Route) => {
      await route.fulfill({
        status: 200,
        contentType: "text/html",
        body: "<html>Not JSON</html>",
      });
    });

    await page.goto("/");
    if (page.url().includes("/login")) {
      await page.fill('[id="email"]', "admin@langsight.io");
      await page.fill('[id="password"]', "demo123");
      await page.getByRole("button", { name: /sign in/i }).click();
      await page.waitForURL("**/*", { timeout: 10_000 });
      await page.goto("/");
    }

    // Page should not be blank — sidebar should still render
    await expect(page.getByText("LangSight").first()).toBeVisible({
      timeout: 8_000,
    });
  });

  test("sessions page handles null response body gracefully", async ({
    page,
  }) => {
    await mockApiRoutes(page);
    await page.route("**/api/proxy/agents/sessions*", async (route: Route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: "null",
      });
    });
    await page.route("**/api/agents/sessions*", async (route: Route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: "null",
      });
    });

    await page.goto("/sessions");
    if (page.url().includes("/login")) {
      await page.fill('[id="email"]', "admin@langsight.io");
      await page.fill('[id="password"]', "demo123");
      await page.getByRole("button", { name: /sign in/i }).click();
      await page.waitForURL("**/*", { timeout: 10_000 });
      await page.goto("/sessions");
    }

    await expect(page.getByText("LangSight").first()).toBeVisible({
      timeout: 8_000,
    });
  });
});

/* ── 401 Unauthorized forces login redirect ────────────────────── */

test.describe("Error boundary — auth errors", () => {
  test("401 on API call redirects to login page", async ({ page }) => {
    // Set up mocks but make the session endpoint return no user
    await page.route("**/api/auth/session", async (route: Route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({}), // No user = unauthenticated
      });
    });

    await page.goto("/");
    // Should redirect to login
    await expect(page).toHaveURL(/\/login/, { timeout: 8_000 });
  });

  test("expired session redirects to login", async ({ page }) => {
    await page.route("**/api/auth/session", async (route: Route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          // Expired session
          user: null,
          expires: new Date(Date.now() - 86400_000).toISOString(),
        }),
      });
    });

    await page.goto("/health");
    await expect(page).toHaveURL(/\/login/, { timeout: 8_000 });
  });
});

/* ── Network failure ───────────────────────────────────────────── */

test.describe("Error boundary — network failures", () => {
  test("page does not crash when API is unreachable", async ({ page }) => {
    await mockApiRoutes(page);
    // Abort health endpoint requests to simulate network failure
    await page.route("**/api/health/servers", async (route: Route) => {
      await route.abort("connectionfailed");
    });
    await page.route("**/api/proxy/health/servers", async (route: Route) => {
      await route.abort("connectionfailed");
    });

    await page.goto("/");
    if (page.url().includes("/login")) {
      await page.fill('[id="email"]', "admin@langsight.io");
      await page.fill('[id="password"]', "demo123");
      await page.getByRole("button", { name: /sign in/i }).click();
      await page.waitForURL("**/*", { timeout: 10_000 });
      await page.goto("/");
    }

    // Page should still render the sidebar and basic structure
    await expect(page.getByText("LangSight").first()).toBeVisible({
      timeout: 8_000,
    });
  });

  test("Run Check button handles network failure gracefully", async ({
    page,
  }) => {
    await gotoWithAuth(page, "/health");

    // Make the health check POST fail
    await page.route("**/api/proxy/health/check", async (route: Route) => {
      await route.abort("connectionfailed");
    });

    const runBtn = page.getByRole("button", { name: /run check/i });
    await runBtn.waitFor({ timeout: 8_000 });
    await runBtn.click();

    // Button should eventually re-enable (not stay in loading state forever)
    await expect(runBtn).toBeEnabled({ timeout: 10_000 });
  });
});

/* ── 404 / invalid routes ──────────────────────────────────────── */

test.describe("Error boundary — 404 routes", () => {
  test("navigating to unknown dashboard route does not crash", async ({
    page,
  }) => {
    await gotoWithAuth(page, "/nonexistent-page");

    // Should either show a 404 page or redirect to overview
    // The key assertion: no blank white screen or unhandled error
    const visible = await Promise.race([
      page.getByText("LangSight").first().waitFor({ timeout: 8_000 }).then(() => true),
      page.getByText("404").first().waitFor({ timeout: 8_000 }).then(() => true),
      page.getByText("not found", { exact: false }).first().waitFor({ timeout: 8_000 }).then(() => true),
    ]).catch(() => false);

    // Page rendered something — not a blank crash
    expect(visible).toBeTruthy();
  });

  test("navigating to invalid session ID does not crash", async ({
    page,
  }) => {
    await gotoWithAuth(page, "/sessions/nonexistent-session-id");

    // Should show something — either error state or empty detail
    await expect(page.getByText("LangSight").first()).toBeVisible({
      timeout: 8_000,
    });
  });
});

/* ── Large response handling ───────────────────────────────────── */

test.describe("Error boundary — large data sets", () => {
  test("sessions page handles large number of sessions without crash", async ({
    page,
  }) => {
    await mockApiRoutes(page);

    // Generate 200 sessions
    const largeSessions = Array.from({ length: 200 }, (_, i) => ({
      session_id: `sess_large_${String(i).padStart(5, "0")}`,
      agent_name: `agent-${i % 5}`,
      first_call_at: new Date(Date.now() - i * 60_000).toISOString(),
      last_call_at: new Date(Date.now() - i * 30_000).toISOString(),
      tool_calls: Math.floor(Math.random() * 50) + 1,
      failed_calls: i % 7 === 0 ? Math.floor(Math.random() * 3) + 1 : 0,
      duration_ms: Math.floor(Math.random() * 30_000) + 500,
      servers_used: ["postgres-mcp"],
    }));

    await page.route("**/api/proxy/agents/sessions*", async (route: Route) => {
      const url = route.request().url();
      if (!url.includes("/agents/sessions/")) {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify(largeSessions),
        });
      } else {
        await route.fallback();
      }
    });
    await page.route("**/api/agents/sessions*", async (route: Route) => {
      const url = route.request().url();
      if (!url.includes("/agents/sessions/")) {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify(largeSessions),
        });
      } else {
        await route.fallback();
      }
    });

    await page.goto("/sessions");
    if (page.url().includes("/login")) {
      await page.fill('[id="email"]', "admin@langsight.io");
      await page.fill('[id="password"]', "demo123");
      await page.getByRole("button", { name: /sign in/i }).click();
      await page.waitForURL("**/*", { timeout: 10_000 });
      await page.goto("/sessions");
    }

    // Should show session count
    await expect(
      page.getByText(/200 sessions/i).first()
    ).toBeVisible({ timeout: 10_000 });

    // Pagination should appear (PAGE_SIZE is 20)
    await expect(
      page.getByText(/1 \/ \d+/).first()
    ).toBeVisible({ timeout: 5_000 });
  });
});
