import { readFileSync } from "node:fs";
import AxeBuilder from "@axe-core/playwright";
import { expect, type Page, test } from "@playwright/test";

function requiredEnvironment(name: string): string {
	const value = process.env[name]?.trim();
	if (!value) throw new Error(`${name} is required`);
	return value;
}

const webOrigin = requiredEnvironment("DITTO_SYSTEM_WEB_ORIGIN");

function captureBrowserErrors(page: Page): string[] {
	const errors: string[] = [];
	page.on("pageerror", (error) => errors.push(error.message));
	page.on("console", (message) => {
		if (message.type() === "error") errors.push(message.text());
	});
	return errors;
}

async function expectNoSeriousAccessibilityViolations(page: Page): Promise<void> {
	const accessibility = await new AxeBuilder({ page }).analyze();
	const serious = accessibility.violations.filter((violation) =>
		["critical", "serious"].includes(violation.impact ?? ""),
	);
	expect(serious).toEqual([]);
}

test.describe
	.serial("chart cockpit showcase journey over the production web build", () => {
		test("renders the interactive cockpit, answers keyboard and exports traced assets", async ({
			page,
		}) => {
			const browserErrors = captureBrowserErrors(page);
			await page.goto(`${webOrigin}/showcase`);

			const daily = page.locator('[data-chart-interaction-contract="showcase-daily-close"]');
			await expect(daily).toBeVisible();
			await expect(daily).toHaveAttribute("data-chart-affordances", /zoom-pan/u);
			await expect(daily).toHaveAttribute("data-chart-as-of", /\d+/u);
			// lightweight-charts mounts real canvases on the chart host.
			await expect(daily.locator("canvas").first()).toBeVisible();

			// Keyboard zoom changes the exposed visible logical range.
			await daily.focus();
			const beforeRange = (await daily.getAttribute("data-chart-visible-range")) ?? "";
			await page.keyboard.press("+");
			await expect
				.poll(async () => (await daily.getAttribute("data-chart-visible-range")) ?? "")
				.not.toBe(beforeRange);

			// Freshness-fade demo cockpit renders on the same page.
			await expect(page.locator('[data-chart-interaction-contract="showcase-freshness"]')).toBeVisible();

			// PNG export downloads a traced screenshot.
			const pngDownload = page.waitForEvent("download");
			await page.getByTestId("chart-export-png-showcase-daily-close").click();
			expect((await pngDownload).suggestedFilename()).toBe("showcase-daily-close.png");

			// CSV export carries the full PIT identity columns (snapshot id untruncated).
			const csvDownload = page.waitForEvent("download");
			await page.getByTestId("chart-export-csv-showcase-daily-close").click();
			const csv = await csvDownload;
			expect(csv.suggestedFilename()).toBe("showcase-daily-close.csv");
			const csvPath = await csv.path();
			expect(csvPath, "downloaded csv must resolve to a local file").not.toBeNull();
			const csvText = readFileSync(csvPath!, "utf8");
			expect(csvText).toContain("as_of,snapshot_id,knowledge_cutoff,publication_cutoff,data_source,exported_at,product_version");
			expect(csvText).toContain("snap-a3f5c90e1b2d47f8a6e0c3d5918f2b74d6a8e1f0c2b4d6e8f0a1b3c5d7e9f24");

			await expectNoSeriousAccessibilityViolations(page);
			expect(browserErrors).toEqual([]);
		});
	});
