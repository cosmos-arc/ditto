import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { JSDOM } from "jsdom";
import { describe, expect, it } from "vitest";

const root = process.cwd();
const prototypesDir = join(root, "docs/designs/specs/prototypes");
const highRiskScanTimeoutMs = 20_000;

type ManifestPage = {
	id: string;
	file: string;
	status: string;
};

type EditionManifest = {
	pages: ManifestPage[];
};

const requiredHighRiskKinds = [
	"delete",
	"pause-trading",
	"order-submit",
	"batch-approval",
	"signal-enable",
	"strategy-publish",
	"data-source-switch",
	"agent-approval",
] as const;

const allowedHighRiskKinds = [
	...requiredHighRiskKinds,
	"config-reset",
	"order-control",
	"risk-rule-change",
	"risk-simulation",
	"signal-review",
	"universe-edit",
] as const;

const highRiskKindValues = new Set<string>(allowedHighRiskKinds);
const documentCache = new Map<string, Document>();
const requiredHighRiskOverlays = [
	{ file: "page-home.html", overlay: "overlay-order-confirm", kind: "order-submit" },
	{ file: "page-trading-overview.html", overlay: "overlay-pause-trading", kind: "pause-trading" },
	{ file: "page-agent-console-v2.html", overlay: "overlay-approval-exact-action", kind: "agent-approval" },
	{ file: "page-backtest-result.html", overlay: "overlay-enable-signal", kind: "signal-enable" },
	{ file: "page-portfolio.html", overlay: "overlay-confirm-close-all", kind: "order-submit" },
	{ file: "page-strategy-studio.html", overlay: "overlay-save-strategy", kind: "strategy-publish" },
	{ file: "page-strategy-studio.html", overlay: "overlay-delete-strategy", kind: "delete" },
	{ file: "page-markets-intelligence.html", overlay: "overlay-delete-confirm", kind: "delete" },
	{ file: "page-watchlist.html", overlay: "overlay-bulk-delete", kind: "delete" },
	{
		file: "page-strategies-detail.html",
		selector: "[data-danger-confirmation][data-high-risk-confirmation]",
		kind: "delete",
	},
	{ file: "page-strategy-list.html", overlay: "overlay-strategy-delete", kind: "delete" },
	{ file: "page-universe-list.html", overlay: "overlay-universe-delete", kind: "delete" },
	{ file: "page-platform-settings.html", overlay: "overlay-save-config", kind: "data-source-switch" },
] as const;

function readManifest(): EditionManifest {
	return JSON.parse(readFileSync(join(prototypesDir, ".edition-manifest.json"), "utf8")) as EditionManifest;
}

function activePrototypePages(): ManifestPage[] {
	return readManifest().pages.filter((page) => page.status === "reviewed" && /^page-.*\.html$/.test(page.file));
}

function loadDocument(file: string): Document {
	const cachedDocument = documentCache.get(file);

	if (cachedDocument) return cachedDocument;

	const document = new JSDOM(readFileSync(join(prototypesDir, file), "utf8")).window.document;
	documentCache.set(file, document);

	return document;
}

function runtimeConfirmations(document: Document): HTMLElement[] {
	return [...document.querySelectorAll<HTMLElement>("[data-high-risk-confirmation]")].filter(
		(confirmation) => confirmation.closest("#overlays-gallery") === null,
	);
}

function overlayName(element: Element): string {
	return element.getAttribute("aria-label") ?? element.id ?? element.textContent?.replace(/\s+/g, " ").trim().slice(0, 80) ?? "unknown";
}

describe("prototype high-risk confirmation contract", () => {
	it("keeps the high-risk confirmation scan aligned with all 28 active route prototypes", () => {
		expect(activePrototypePages()).toHaveLength(28);
	});

	it("keeps every declared high-risk confirmation auditable and recoverable", () => {
		const failures: string[] = [];

		for (const page of activePrototypePages()) {
			const document = loadDocument(page.file);
			const confirmations = runtimeConfirmations(document);

			for (const confirmation of confirmations) {
				const name = overlayName(confirmation);
				const rawKinds = confirmation.getAttribute("data-high-risk-kind")?.trim();
				const requiredSelectors = [
					"[data-impact-preview]",
					"[data-risk-object-list]",
					"[data-audit-record]",
					"[data-recovery-path]",
					"[data-cancel-control]",
					"[data-confirm-control]",
				];

				if (!rawKinds) {
					failures.push(`${page.file}:${name}: missing data-high-risk-kind`);
				} else {
					for (const kind of rawKinds.split(/\s+/)) {
						if (!highRiskKindValues.has(kind)) {
							failures.push(`${page.file}:${name}: invalid data-high-risk-kind "${kind}"`);
						}
					}
				}

				for (const selector of requiredSelectors) {
					if (!confirmation.querySelector(selector)) {
						failures.push(`${page.file}:${name}: missing ${selector}`);
					}
				}
			}
		}

		expect(failures).toEqual([]);
	}, highRiskScanTimeoutMs);

	it("covers the required high-risk action categories in active prototypes", () => {
		const discoveredKinds = new Set<string>();

		for (const page of activePrototypePages()) {
			const document = loadDocument(page.file);

			for (const confirmation of runtimeConfirmations(document)) {
				for (const kind of confirmation.getAttribute("data-high-risk-kind")?.trim().split(/\s+/) ?? []) {
					discoveredKinds.add(kind);
				}
			}
		}

		const missingKinds = requiredHighRiskKinds.filter((kind) => !discoveredKinds.has(kind));

		expect(missingKinds).toEqual([]);
	}, highRiskScanTimeoutMs);

	it("routes known high-risk surfaces through the unified confirmation contract", () => {
		const failures: string[] = [];

		for (const requirement of requiredHighRiskOverlays) {
			const document = loadDocument(requirement.file);
			const target = "overlay" in requirement
				? document.querySelector(`[data-overlay="${requirement.overlay}"]`)
				: document.querySelector(requirement.selector);
			const confirmation = target?.matches("[data-high-risk-confirmation]")
				? (target as HTMLElement)
				: target?.querySelector<HTMLElement>("[data-high-risk-confirmation]");
			const kinds = confirmation?.getAttribute("data-high-risk-kind")?.trim().split(/\s+/) ?? [];

			if (!confirmation) {
				const targetName = "overlay" in requirement ? requirement.overlay : requirement.selector;
				failures.push(`${requirement.file}:${targetName}: missing [data-high-risk-confirmation]`);
				continue;
			}

			if (!kinds.includes(requirement.kind)) {
				const targetName = "overlay" in requirement ? requirement.overlay : requirement.selector;
				failures.push(`${requirement.file}:${targetName}: missing kind ${requirement.kind}`);
			}
		}

		expect(failures).toEqual([]);
	}, highRiskScanTimeoutMs);

	it("does not leave danger confirmations outside the high-risk contract", () => {
		const failures: string[] = [];

		for (const page of activePrototypePages()) {
			const document = loadDocument(page.file);
			const dangerConfirmations = [...document.querySelectorAll<HTMLElement>("[data-danger-confirmation]")].filter(
				(confirmation) => confirmation.closest("#overlays-gallery") === null,
			);

			for (const confirmation of dangerConfirmations) {
				if (!confirmation.hasAttribute("data-high-risk-confirmation")) {
					failures.push(`${page.file}:${overlayName(confirmation)}: missing [data-high-risk-confirmation]`);
				}
			}
		}

		expect(failures).toEqual([]);
	}, highRiskScanTimeoutMs);

	it("does not leave superseded root Agent Console in active high-risk scope", () => {
		const rootFiles = readdirSync(prototypesDir).filter((file) => /^page-.*\.html$/.test(file));
		const failures = rootFiles.filter((file) => file === "page-agent-console.html");

		expect(failures).toEqual([]);
	});
});
