import { mkdirSync } from "node:fs";
import { join, resolve } from "node:path";
import { chromium } from "playwright";

type MatrixPage = {
	id: string;
	file: string;
};

type MatrixPreference = {
	theme: "dark" | "light";
	density: "compact" | "comfortable";
};

const prototypesDir = resolve(import.meta.dirname, "../docs/designs/specs/prototypes");
const outputDir = resolve(import.meta.dirname, "../test-results/edition-review/visual-matrix");

const pages: MatrixPage[] = [
	{ id: "a-shares", file: "page-a-shares.html" },
	{ id: "platform-settings", file: "page-platform-settings.html" },
	{ id: "home", file: "page-home.html" },
	{ id: "watchlist", file: "page-watchlist.html" },
	{ id: "risk-center", file: "page-risk-center.html" },
	{ id: "instrument-hub", file: "page-instrument-hub.html" },
	{ id: "strategy-studio", file: "page-strategy-studio.html" },
];

const preferences: MatrixPreference[] = [
	{ theme: "dark", density: "compact" },
	{ theme: "dark", density: "comfortable" },
	{ theme: "light", density: "compact" },
	{ theme: "light", density: "comfortable" },
];

function screenshotPath(page: MatrixPage, preference: MatrixPreference): string {
	return join(outputDir, page.id, `${preference.theme}-${preference.density}.png`);
}

async function main() {
	const browser = await chromium.launch({ channel: "chromium" });
	let generated = 0;

	try {
		for (const prototype of pages) {
			for (const preference of preferences) {
				const page = await browser.newPage({ viewport: { width: 1366, height: 768 } });
				const path = screenshotPath(prototype, preference);

				try {
					await page.addInitScript(({ theme, density }: MatrixPreference) => {
						localStorage.setItem("ditto-theme", theme);
						localStorage.setItem("ditto-density", density);
					}, preference);
					await page.goto(`file://${join(prototypesDir, prototype.file)}`, {
						waitUntil: "load",
						timeout: 15_000,
					});
					await page.evaluate(({ theme, density }: MatrixPreference) => {
						document.documentElement.dataset.theme = theme;
						document.documentElement.dataset.themePreference = theme;
						document.documentElement.dataset.density = density;
					}, preference);

					mkdirSync(join(outputDir, prototype.id), { recursive: true });
					await page.screenshot({ path, fullPage: false });
					generated += 1;
				} finally {
					await page.close();
				}
			}
		}
	} finally {
		await browser.close();
	}

	console.log(`Generated ${generated} visual matrix screenshots in ${outputDir}`);
}

await main();
