import { expect, test, type Page } from "@playwright/test";

function requiredEnvironment(name: string): string {
	const value = process.env[name]?.trim();
	if (!value) throw new Error(`${name} is required`);
	return value;
}

const apiOrigin = requiredEnvironment("DITTO_SYSTEM_API_ORIGIN");
const researchPaths = [
	"/api/v1/research/factors",
	"/api/v1/research/experiments",
	"/api/v1/research/reviews",
] as const;

function captureBrowserErrors(page: Page): string[] {
	const errors: string[] = [];
	page.on("pageerror", (error) => errors.push(error.message));
	page.on("console", (message) => {
		if (message.type() === "error") errors.push(message.text());
	});
	return errors;
}

test.describe("real product flow: research query into portfolio view", () => {
	test("research workspace answers live control-plane queries", async ({ page }) => {
		const errors = captureBrowserErrors(page);
		const statuses = new Map<string, number>();
		page.on("response", (response) => {
			for (const path of researchPaths) {
				if (response.url() === `${apiOrigin}${path}`) {
					statuses.set(path, response.status());
				}
			}
		});

		await page.goto("/research/", { waitUntil: "networkidle" });

		const strip = page.getByLabel("研究证据范围");
		await expect(strip).toBeVisible();
		await expect(strip).toHaveAttribute("data-state", "fresh");
		for (const path of researchPaths) {
			expect(statuses.get(path), `${path} must have been queried`).toBe(200);
		}
		await expect(page.getByRole("alert")).toHaveCount(0);
		expect(errors).toEqual([]);
	});

	test("portfolio view requires an exact identity and never falls back", async ({ page }) => {
		const errors = captureBrowserErrors(page);

		await page.goto("/portfolio/", { waitUntil: "networkidle" });

		await expect(
			page.getByRole("heading", { name: "Portfolio Overview" }),
		).toBeVisible();
		await expect(page.locator("#root")).not.toBeEmpty();
		// The PIT identity gate is fail-closed: without an exact cohort the page
		// refuses to guess instead of rendering latest-or-fabricated data.
		await expect(page.getByRole("alert")).toContainText("缺少精确组合身份");
		expect(errors).toEqual([]);
	});
});
