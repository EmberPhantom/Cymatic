import { test, expect } from "@playwright/test"

test.describe("auth flow", () => {
  test("register and login", async ({ page }) => {
    const email = `e2e-${Date.now()}@example.com`
    await page.goto("/register")
    await page.getByLabel(/email/i).fill(email)
    await page.getByLabel(/^name/i).fill("E2E User")
    await page.getByLabel(/^password/i).fill("testpass123")
    await page.getByRole("button", { name: /register|create/i }).click()
    await expect(page).toHaveURL(/login/)
    await page.getByLabel(/email/i).fill(email)
    await page.getByLabel(/password/i).fill("testpass123")
    await page.getByRole("button", { name: /login|sign in/i }).click()
    await expect(page).toHaveURL(/dashboard/)
  })

  test("unauthenticated redirect", async ({ page }) => {
    await page.goto("/dashboard")
    await expect(page).toHaveURL(/login/)
  })
})
