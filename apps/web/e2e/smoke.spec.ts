import { test, expect } from "@playwright/test"

test("public landing page renders", async ({ page }) => {
  await page.goto("/")
  await expect(page).toHaveTitle(/Cymatic/i)
})

test("login page exposes required credentials", async ({ page }) => {
  await page.goto("/login")
  await expect(page.getByLabel(/email/i)).toBeVisible()
  await expect(page.getByLabel(/password/i)).toBeVisible()
})
