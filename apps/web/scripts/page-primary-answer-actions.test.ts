import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { JSDOM } from "jsdom";
import { chromium, type Browser } from "playwright";
import { afterAll, beforeAll, describe, expect, it } from "vitest";

const navigationTimeoutMs = 10_000;
const prototypesDir = resolve(import.meta.dirname, "../docs/designs/specs/prototypes");
const archivedPrototypeIds = new Set(["ai-overview", "ai-copilot"]);
let browser: Browser;

type ManifestPage = {
	id: string;
	file: string;
};

type EditionManifest = {
	pages: ManifestPage[];
};

function prototypeUrl(file: string): string {
	return `file://${resolve(prototypesDir, file)}`;
}

function activePages(): ManifestPage[] {
	const manifest = JSON.parse(
		readFileSync(resolve(prototypesDir, ".edition-manifest.json"), "utf8"),
	) as EditionManifest;

	return manifest.pages.filter(
		(page) =>
			page.file.startsWith("page-") &&
			page.file.endsWith(".html") &&
			page.id !== "token-showcase" &&
			!archivedPrototypeIds.has(page.id),
	);
}

function pagesWithCustomAriaControlsPrimaryAction(): ManifestPage[] {
	return activePages().filter((page) => {
		const html = readFileSync(resolve(prototypesDir, page.file), "utf8");
		const document = new JSDOM(html).window.document;
		const region = document.querySelector("[data-primary-answer], [data-primary-answer-equivalent]");
		const action = region?.matches("[data-answer-action][aria-controls], .answer-action[aria-controls]")
			? region
			: region?.querySelector("[data-answer-action][aria-controls], .answer-action[aria-controls]");

		return Boolean(action?.matches("[role='button'][aria-controls], [role='link'][aria-controls]"));
	});
}

describe("prototype primary answer actions", () => {
	beforeAll(async () => {
		browser = await chromium.launch({ channel: "chromium" });
	});

	afterAll(async () => {
		await browser.close();
	});

	it(
		"opens the Research run queue drilldown from the primary answer action",
		async () => {
			const page = await browser.newPage({ viewport: { width: 1536, height: 1080 } });

			try {
				await page.goto(prototypeUrl("page-research.html"), { waitUntil: "load", timeout: navigationTimeoutMs });
				await page.click('[data-answer-action][data-action-target="tab-backtest"]');

				const state = await page.evaluate(() => {
					const tab = document.querySelector<HTMLElement>("#tab-backtest");
					const panel = document.querySelector<HTMLElement>("#panel-backtest");

					return {
						selected: tab?.getAttribute("aria-selected"),
						hidden: panel?.getAttribute("aria-hidden"),
						display: panel ? getComputedStyle(panel).display : "missing",
					};
				});

				expect(state).toMatchObject({ selected: "true", hidden: "false" });
				expect(state.display).not.toBe("none");
			} finally {
				await page.close();
			}
		},
		15_000,
	);

	it(
		"opens the Portfolio attribution drilldown from the primary answer action",
		async () => {
			const page = await browser.newPage({ viewport: { width: 1536, height: 1080 } });

			try {
				await page.goto(prototypeUrl("page-portfolio.html"), { waitUntil: "load", timeout: navigationTimeoutMs });
				await page.click('[data-answer-action][for="tab-attribution"]');

				const state = await page.evaluate(() => {
					const radio = document.querySelector<HTMLInputElement>("#tab-attribution");
					const panel = document.querySelector<HTMLElement>("#panel-attribution");

					return {
						checked: radio?.checked ?? false,
						hidden: panel?.getAttribute("aria-hidden"),
						display: panel ? getComputedStyle(panel).display : "missing",
					};
				});

				expect(state).toMatchObject({ checked: true, hidden: "false" });
				expect(state.display).not.toBe("none");
			} finally {
				await page.close();
			}
		},
		15_000,
	);

	it(
		"activates every custom aria-controls primary answer drilldown",
		async () => {
			const page = await browser.newPage({ viewport: { width: 1536, height: 1080 } });
			const violations: string[] = [];

			try {
				for (const prototype of pagesWithCustomAriaControlsPrimaryAction()) {
					await page.goto(prototypeUrl(prototype.file), { waitUntil: "load", timeout: navigationTimeoutMs });

					const result = await page.evaluate(async () => {
						const region = document.querySelector("[data-primary-answer], [data-primary-answer-equivalent]");
						const action = region?.matches("[data-answer-action][aria-controls], .answer-action[aria-controls]")
							? (region as HTMLElement)
							: region?.querySelector<HTMLElement>("[data-answer-action][aria-controls], .answer-action[aria-controls]");

						if (!action) return { checked: true, reason: "no-custom-aria-controls-action" };

						const controlledIds = (action.getAttribute("aria-controls") ?? "").trim().split(/\s+/).filter(Boolean);
						const wasVisibleById = new Map(
							controlledIds.map((id) => {
								const target = document.getElementById(id);
								if (!target) return [id, false] as const;
								const style = getComputedStyle(target);
								return [
									id,
									target.getAttribute("aria-hidden") !== "true" &&
										style.display !== "none" &&
										style.visibility !== "hidden",
								] as const;
							}),
						);

						action.click();

						await new Promise<void>((resolveFrame) => {
							requestAnimationFrame(() => requestAnimationFrame(() => resolveFrame()));
						});

						const activated = controlledIds.some((id) => {
							const target = document.getElementById(id);
							if (!target) return false;

							const style = getComputedStyle(target);
							const visible = target.getAttribute("aria-hidden") !== "true" &&
								style.display !== "none" &&
								style.visibility !== "hidden";

							return visible && (
								wasVisibleById.get(id) === false ||
								target.getAttribute("data-primary-answer-drilldown") === "active" ||
								target === document.activeElement ||
								target.contains(document.activeElement)
							);
						});

						return {
							checked: activated,
							reason: activated ? "activated" : `inactive:${controlledIds.join(",")}`,
						};
					});

					if (!result.checked && result.reason !== "no-custom-aria-controls-action") {
						violations.push(`${prototype.id}:${result.reason}`);
					}
				}

				expect(violations).toEqual([]);
			} finally {
				await page.close();
			}
		},
		90_000,
	);
});
