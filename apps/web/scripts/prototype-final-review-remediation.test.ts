import { readFileSync, readdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { JSDOM } from "jsdom";
import { chromium } from "playwright";
import { describe, expect, it } from "vitest";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const prototypesDir = join(__dirname, "../docs/designs/specs/prototypes");

function readPage(file: string): string {
	return readFileSync(join(prototypesDir, file), "utf8");
}

function loadDocument(file: string): Document {
	return new JSDOM(readPage(file)).window.document;
}

function accessibleName(element: Element): string {
	return [
		element.getAttribute("aria-label"),
		element.getAttribute("title"),
		element.textContent,
	]
		.filter(Boolean)
		.join(" ")
		.replace(/\s+/g, " ")
		.trim();
}

function visibleBodyText(document: Document): string {
	const nodeFilter = document.defaultView?.NodeFilter;
	if (!nodeFilter) throw new Error("JSDOM NodeFilter is unavailable");

	const walker = document.createTreeWalker(document.body, nodeFilter.SHOW_TEXT, {
		acceptNode(node) {
			const parent = node.parentElement;
			if (!parent) return nodeFilter.FILTER_REJECT;
			if (["SCRIPT", "STYLE", "TEMPLATE", "NOSCRIPT"].includes(parent.tagName)) {
				return nodeFilter.FILTER_REJECT;
			}
			return nodeFilter.FILTER_ACCEPT;
		},
	});

	const chunks: string[] = [];
	let node = walker.nextNode();
	while (node) {
		const text = node.textContent?.replace(/\s+/g, " ").trim();
		if (text) chunks.push(text);
		node = walker.nextNode();
	}

	return chunks.join(" ");
}

const activePrototypeFiles = readdirSync(prototypesDir)
	.filter((file) => /^page-[a-z0-9-]+\.html$/.test(file))
	.sort();

const auditedActionLabels = [
	{
		file: "page-research.html",
		selector: 'label.inline-action-link[for="overlay-run-detail"]',
		expectedName: /价值因子 Q1 回测详情/,
	},
	{
		file: "page-research.html",
		selector: 'label.inline-action-link[for="overlay-review-action"]',
		expectedName: /行业轮动参数优化.*审核/,
	},
	{
		file: "page-trading-overview.html",
		selector: 'label.pipeline-stage[for="pipeline-signal-pool"]',
		expectedName: /信号池.*4/,
	},
	{
		file: "page-trading-overview.html",
		selector: 'label.pipeline-stage[for="pipeline-pending"]',
		expectedName: /待复核.*2/,
	},
	{
		file: "page-trading-overview.html",
		selector: 'label.pipeline-stage[for="pipeline-ordered"]',
		expectedName: /已下单.*3/,
	},
	{
		file: "page-trading-overview.html",
		selector: 'label.pipeline-stage[for="pipeline-filled"]',
		expectedName: /已成交.*47/,
	},
	{
		file: "page-a-shares.html",
		selector: 'label.context-bar-item[for="overlay-northbound-detail"]',
		expectedName: /北向.*12/,
	},
	{
		file: "page-a-shares.html",
		selector: 'label.rail-section-expand[for="overlay-northbound-detail"]',
		expectedName: /北向资金.*展开/,
	},
	{
		file: "page-cross-market.html",
		selector: 'label.pair-chart-close[for="pair-chart"]',
		expectedName: /关闭.*走势对比/,
	},
] as const;

describe("prototype final review remediation gates", () => {
	it("keeps audited label-driven actions keyboard reachable and explicitly named", () => {
		const failures: string[] = [];

		for (const target of auditedActionLabels) {
			const document = loadDocument(target.file);
			const label = document.querySelector<HTMLLabelElement>(target.selector);

			if (!label) {
				failures.push(`${target.file}: missing ${target.selector}`);
				continue;
			}

			const control = document.getElementById(label.htmlFor);
			if (!control) failures.push(`${target.file}: ${target.selector} points to missing #${label.htmlFor}`);
			if (label.getAttribute("role") !== "button") failures.push(`${target.file}: ${target.selector} needs role="button"`);
			if (label.getAttribute("tabindex") !== "0") failures.push(`${target.file}: ${target.selector} needs tabindex="0"`);
			if (!target.expectedName.test(accessibleName(label))) {
				failures.push(`${target.file}: ${target.selector} needs accessible name matching ${target.expectedName}`);
			}
		}

		expect(failures).toEqual([]);
	});

	it("binds Platform Settings visible form labels to controls or named groups", () => {
		const document = loadDocument("page-platform-settings.html");
		const failures: string[] = [];

		for (const label of document.querySelectorAll<HTMLLabelElement>("label.form-label")) {
			if (!label.htmlFor) {
				failures.push(`label "${accessibleName(label)}" is missing for=""`);
				continue;
			}

			const control = document.getElementById(label.htmlFor);
			if (!control) failures.push(`label "${accessibleName(label)}" points to missing #${label.htmlFor}`);
		}

		for (const group of document.querySelectorAll<HTMLElement>("[role='group'][aria-labelledby]")) {
			const labelId = group.getAttribute("aria-labelledby");
			if (!labelId || !document.getElementById(labelId)) {
				failures.push(`group "${accessibleName(group)}" points to missing #${labelId ?? ""}`);
			}
		}

		expect(failures).toEqual([]);
	});

	it("does not ship visible text or aria labels containing 占位 in active route prototypes", () => {
		const failures: string[] = [];

		for (const file of activePrototypeFiles) {
			const document = loadDocument(file);
			const visibleText = visibleBodyText(document);

			if (visibleText.includes("占位")) failures.push(`${file}: visible body text contains 占位`);

			for (const element of document.querySelectorAll<HTMLElement>("[aria-label]")) {
				const ariaLabel = element.getAttribute("aria-label") ?? "";
				if (ariaLabel.includes("占位")) {
					failures.push(`${file}: aria-label contains 占位 -> ${ariaLabel}`);
				}
			}
		}

		expect(failures).toEqual([]);
	}, 20_000);

	it("keeps Cross Market macro driver items inside the strip at desktop review widths", async () => {
		const browser = await chromium.launch({ headless: true });
		const page = await browser.newPage();

		try {
			for (const width of [1440, 1366, 1200]) {
				await page.setViewportSize({ width, height: 1000 });
				await page.goto(pathToFileURL(join(prototypesDir, "page-cross-market.html")).href);
				await page.waitForLoadState("domcontentloaded");

				const overflowingItems = await page.locator(".drivers-strip").evaluate((strip) => {
					const stripRect = strip.getBoundingClientRect();
					return Array.from(strip.querySelectorAll(".driver-item"))
						.map((item) => {
							const rect = item.getBoundingClientRect();
							return {
								name: item.textContent?.replace(/\s+/g, " ").trim(),
								left: rect.left,
								right: rect.right,
								stripLeft: stripRect.left,
								stripRight: stripRect.right,
								viewportRight: window.innerWidth,
							};
						})
						.filter((item) => item.left < item.stripLeft - 0.5 || item.right > item.stripRight + 0.5 || item.right > item.viewportRight + 0.5);
				});

				expect(overflowingItems, `${width}px`).toEqual([]);
			}
		} finally {
			await browser.close();
		}
	}, 20_000);
});
