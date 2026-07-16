import { existsSync, readFileSync } from "node:fs";
import { join, resolve } from "node:path";
import { chromium, type Browser, type Page } from "playwright";
import { afterAll, beforeAll, describe, expect, it } from "vitest";

const prototypesDir = resolve(import.meta.dirname, "../docs/designs/specs/prototypes");
const projectRoot = resolve(import.meta.dirname, "..");
const archivedPrototypeIds = new Set(["ai-overview", "ai-copilot"]);
const visualMatrixScriptPath = join(projectRoot, "scripts/prototype-visual-matrix.ts");
const visualMatrixPages = [
	"page-a-shares.html",
	"page-platform-settings.html",
	"page-home.html",
	"page-watchlist.html",
	"page-risk-center.html",
	"page-instrument-hub.html",
	"page-strategy-studio.html",
];
const chromiumLaunchOptions = {
	channel: "chromium",
	args: ["--disable-gpu"],
} as const;

type ManifestPage = {
	id: string;
	file: string;
	status?: string;
};

type EditionManifest = {
	pages: ManifestPage[];
};

type PreferenceSelectionState = {
	theme: string | null;
	preference: string | null;
	density: string | null;
	themeLabel: string | null | undefined;
	densityLabel: string | null | undefined;
	hasMenu: boolean;
};

type HeaderControlStyle = {
	kind: "command" | "icon" | "local";
	label: string;
	width: number;
	height: number;
	fontSize: string;
	color: string;
	backgroundColor: string;
	borderColor: string;
	borderWidth: string;
	borderRadius: string;
};

let browser: Browser;

async function launchViewPreferencesBrowser(): Promise<Browser> {
	return chromium.launch(chromiumLaunchOptions);
}

async function closeBrowserIfOpen(activeBrowser: Browser): Promise<void> {
	await Promise.race([
		activeBrowser.close().catch(() => undefined),
		new Promise<void>((resolve) => {
			setTimeout(resolve, 1_000);
		}),
	]);
}

function readManifest(): EditionManifest {
	return JSON.parse(readFileSync(join(prototypesDir, ".edition-manifest.json"), "utf8")) as EditionManifest;
}

function isActiveRoutePrototype(page: ManifestPage): boolean {
	return (
		page.file?.startsWith("page-") &&
		page.file.endsWith(".html") &&
		page.id !== "token-showcase" &&
		page.status !== "archived-specimen" &&
		!archivedPrototypeIds.has(page.id)
	);
}

async function getPreferenceSelectionState(page: Page): Promise<PreferenceSelectionState> {
	return page.evaluate(() => ({
		theme: document.documentElement.getAttribute("data-theme"),
		preference: document.documentElement.getAttribute("data-theme-preference"),
		density: document.documentElement.getAttribute("data-density"),
		themeLabel: document.querySelector("#theme-toggle")?.getAttribute("aria-label"),
		densityLabel: document.querySelector("#density-toggle")?.getAttribute("aria-label"),
		hasMenu: Boolean(document.querySelector("[data-view-preferences-menu]")),
	}));
}

async function closePageIfOpen(page: Page): Promise<void> {
	if (page.isClosed()) return;

	try {
		await Promise.race([
			page.close(),
			new Promise<void>((resolve) => {
				setTimeout(resolve, 500);
			}),
		]);
	} catch (error) {
		const message = error instanceof Error ? error.message : String(error);
		if (!message.includes("Target page, context or browser has been closed")) {
			throw error;
		}
	}
}

describe("prototype view preferences", () => {
	beforeAll(async () => {
		browser = await launchViewPreferencesBrowser();
	});

	afterAll(async () => {
		await closeBrowserIfOpen(browser);
	});

	it("wires the light and density visual matrix audit command", () => {
		const packageJson = JSON.parse(readFileSync(join(projectRoot, "package.json"), "utf8")) as {
			scripts?: Record<string, string>;
		};

		expect(packageJson.scripts?.["prototype:visual-matrix"]).toBe(
			"bun scripts/prototype-visual-matrix.ts",
		);
		expect(existsSync(visualMatrixScriptPath)).toBe(true);
	});

	it("renders representative light and comfortable direct preference toggles without menu chrome", async () => {
		const failures: string[] = [];

		for (const file of visualMatrixPages) {
			const page = await browser.newPage({ viewport: { width: 1366, height: 768 } });

			try {
				await page.addInitScript(() => {
					localStorage.setItem("ditto-theme", "light");
					localStorage.setItem("ditto-density", "comfortable");
				});
				await page.goto(`file://${join(prototypesDir, file)}`);
				await page.waitForLoadState("domcontentloaded");

				const state = await page.evaluate(() => {
					const theme = document.querySelector("#theme-toggle");
					const density = document.querySelector("#density-toggle");
					if (!(theme instanceof HTMLElement) || !(density instanceof HTMLElement)) return null;

					const themeRect = theme.getBoundingClientRect();
					const densityRect = density.getBoundingClientRect();
					return {
						theme: document.documentElement.getAttribute("data-theme"),
						density: document.documentElement.getAttribute("data-density"),
						hasMenu: Boolean(document.querySelector("[data-view-preferences-menu]")),
						themeWidth: themeRect.width,
						densityWidth: densityRect.width,
						themeLabel: theme.getAttribute("aria-label"),
						densityLabel: density.getAttribute("aria-label"),
						viewportWidth: window.innerWidth,
						viewportHeight: window.innerHeight,
					};
				});
				const screenshot = await page.screenshot({ fullPage: false });

				if (
					!state ||
					state.theme !== "light" ||
					state.density !== "comfortable" ||
					state.hasMenu ||
					state.themeWidth === 0 ||
					state.densityWidth === 0 ||
					!state.themeLabel?.includes("浅色") ||
					!state.densityLabel?.includes("宽松") ||
					screenshot.byteLength < 1000
				) {
					throw new Error(`invalid visual preference toggles: ${JSON.stringify(state)}`);
				}
			} catch (error) {
				const message = error instanceof Error ? error.message : String(error);
				failures.push(`${file}: ${message}`);
			} finally {
				await closePageIfOpen(page);
			}
		}

		expect(failures).toEqual([]);
	}, 120_000);

	it("supports theme and density interactions across every active prototype", async () => {
		const failures: string[] = [];
		let page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
		page.setDefaultNavigationTimeout(10_000);

		try {
			for (const prototype of readManifest().pages.filter(isActiveRoutePrototype)) {
				try {
					await page.addInitScript(() => {
						localStorage.removeItem("ditto-theme");
						localStorage.removeItem("ditto-density");
					});
					await page.goto(`file://${join(prototypesDir, prototype.file)}`, {
						waitUntil: "domcontentloaded",
						timeout: 10_000,
					});

					await page.click("#theme-toggle");
					await page.click("#density-toggle");

					const selectionState = await getPreferenceSelectionState(page);
					if (
						selectionState.theme !== "light" ||
						selectionState.preference !== "light" ||
						selectionState.density !== "comfortable" ||
						selectionState.hasMenu ||
						!selectionState.themeLabel?.includes("浅色") ||
						!selectionState.densityLabel?.includes("宽松")
					) {
						throw new Error(`selection did not stick: ${JSON.stringify(selectionState)}`);
					}
				} catch (error) {
					const message = error instanceof Error ? error.message : String(error);
					if (!message.includes("Target page") && !message.includes("browser has been closed")) {
						failures.push(`${prototype.id}: ${message}`);
						continue;
					}

					await closePageIfOpen(page);
					await closeBrowserIfOpen(browser);
					browser = await launchViewPreferencesBrowser();
					page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
					page.setDefaultNavigationTimeout(10_000);
					failures.push(`${prototype.id}: ${message}`);
				}
			}
		} finally {
			await closePageIfOpen(page);
		}

		expect(failures).toEqual([]);
	}, 120_000);

	it("renders one header control chrome across every active prototype", async () => {
		const failures: string[] = [];
		let page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
		page.setDefaultNavigationTimeout(10_000);

		try {
			for (const prototype of readManifest().pages.filter(isActiveRoutePrototype)) {
				try {
					await page.goto(`file://${join(prototypesDir, prototype.file)}`, {
						waitUntil: "domcontentloaded",
						timeout: 10_000,
					});

					const controls = await page.evaluate<HeaderControlStyle[]>(() => {
						const selectors: Array<{ kind: HeaderControlStyle["kind"]; selector: string }> = [
							{ kind: "command", selector: ".shell-header .header-command-trigger" },
							{ kind: "icon", selector: ".shell-header .header-utility-btn:not(.header-command-trigger)" },
							{ kind: "icon", selector: ".shell-header .header-action-btn" },
							{ kind: "icon", selector: ".shell-header .header-btn-badge" },
							{ kind: "local", selector: ".shell-header .header-actions :is(.btn, .btn-sm)" },
						];

						return selectors.flatMap(({ kind, selector }) =>
							Array.from(document.querySelectorAll<HTMLElement>(selector)).map((element) => {
								const rect = element.getBoundingClientRect();
								const style = getComputedStyle(element);

								return {
									kind,
									label:
										element.getAttribute("aria-label") ??
										element.getAttribute("title") ??
										element.textContent?.replace(/\s+/g, " ").trim() ??
										selector,
									width: Math.round(rect.width),
									height: Math.round(rect.height),
									fontSize: style.fontSize,
									color: style.color,
									backgroundColor: style.backgroundColor,
									borderColor: style.borderColor,
									borderWidth: style.borderWidth,
									borderRadius: style.borderRadius,
								};
							}),
						);
					});

					const reference = controls.find((control) => control.kind === "icon");
					if (!reference) {
						throw new Error("missing icon header control reference");
					}

					for (const control of controls) {
						if (control.kind === "command" && control.width !== 176) {
							failures.push(`${prototype.id}:${control.label}: expected command width 176, got ${control.width}`);
						}
						if (control.kind === "icon" && control.width !== 32) {
							failures.push(`${prototype.id}:${control.label}: expected icon width 32, got ${control.width}`);
						}
						if (control.height !== 32) {
							failures.push(`${prototype.id}:${control.label}: expected height 32, got ${control.height}`);
						}
						if (control.fontSize !== "12px") {
							failures.push(`${prototype.id}:${control.label}: expected 12px font, got ${control.fontSize}`);
						}
						if (control.color !== reference.color) {
							failures.push(`${prototype.id}:${control.label}: expected color ${reference.color}, got ${control.color}`);
						}
						if (control.backgroundColor !== reference.backgroundColor) {
							failures.push(
								`${prototype.id}:${control.label}: expected background ${reference.backgroundColor}, got ${control.backgroundColor}`,
							);
						}
						if (control.borderColor !== reference.borderColor) {
							failures.push(
								`${prototype.id}:${control.label}: expected border color ${reference.borderColor}, got ${control.borderColor}`,
							);
						}
						if (control.borderWidth !== "1px") {
							failures.push(`${prototype.id}:${control.label}: expected 1px border, got ${control.borderWidth}`);
						}
						if (control.borderRadius !== "6px") {
							failures.push(`${prototype.id}:${control.label}: expected 6px radius, got ${control.borderRadius}`);
						}
					}
				} catch (error) {
					const message = error instanceof Error ? error.message : String(error);
					if (!message.includes("Target page") && !message.includes("browser has been closed")) {
						failures.push(`${prototype.id}: ${message}`);
						continue;
					}

					await closePageIfOpen(page);
					await closeBrowserIfOpen(browser);
					browser = await launchViewPreferencesBrowser();
					page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
					page.setDefaultNavigationTimeout(10_000);
					failures.push(`${prototype.id}: ${message}`);
				}
			}
		} finally {
			await closePageIfOpen(page);
		}

		expect(failures).toEqual([]);
	}, 120_000);
});
