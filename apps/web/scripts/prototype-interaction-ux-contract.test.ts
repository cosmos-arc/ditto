import { readFileSync } from "node:fs";
import { join, resolve } from "node:path";
import { JSDOM } from "jsdom";
import { describe, expect, it } from "vitest";

const prototypesDir = resolve(import.meta.dirname, "../docs/designs/specs/prototypes");
const archivedPrototypeIds = new Set(["ai-overview", "ai-copilot"]);
const railDomains = ["home", "markets", "research", "trading", "platform"] as const;
const railDomainSet = new Set<string>(railDomains);
const railLabels: Record<(typeof railDomains)[number], string> = {
	home: "首页",
	markets: "市场",
	research: "研究",
	trading: "交易",
	platform: "平台",
};
const bannedRailLabels = new Set(["AI", "运维", "Platform", "Home", "Markets", "Research", "Trading"]);
const hamburgerPathSet = ["M3 4h14", "M3 10h14", "M3 16h14"].sort().join("|");

type ManifestPage = {
	id: string;
	file: string;
	shellFamily?: string;
};

type EditionManifest = {
	pages: ManifestPage[];
};

function readJson<T>(path: string): T {
	return JSON.parse(readFileSync(path, "utf8")) as T;
}

let manifestCache: EditionManifest | undefined;
const prototypeDocumentCache = new Map<string, Document>();

function readManifest(): EditionManifest {
	manifestCache ??= readJson<EditionManifest>(join(prototypesDir, ".edition-manifest.json"));
	return manifestCache;
}

function isActiveRoutePrototype(page: ManifestPage): boolean {
	return (
		page.file?.startsWith("page-") &&
		page.file.endsWith(".html") &&
		page.id !== "token-showcase" &&
		!archivedPrototypeIds.has(page.id)
	);
}

function activePages(): ManifestPage[] {
	return readManifest().pages.filter(isActiveRoutePrototype);
}

function readPrototypeDocument(page: ManifestPage): Document {
	const path = join(prototypesDir, page.file);
	const cached = prototypeDocumentCache.get(path);
	if (cached) return cached;

	const document = new JSDOM(readFileSync(path, "utf8")).window.document;
	prototypeDocumentCache.set(path, document);
	return document;
}

function normalizePathData(value: string): string {
	return value.replace(/\s+/g, " ").trim();
}

function getSvgPathSet(element: Element | null): string {
	if (!element) return "";

	return Array.from(element.querySelectorAll("svg path"))
		.map((path) => normalizePathData(path.getAttribute("d") ?? ""))
		.filter(Boolean)
		.sort()
		.join("|");
}

function getActionIcon(element: Element | null): string | null {
	return (
		element?.getAttribute("data-action-icon") ??
		element?.querySelector("[data-action-icon]")?.getAttribute("data-action-icon") ??
		null
	);
}

function findActionByLabel(document: Document, label: string): Element | null {
	return Array.from(document.querySelectorAll<HTMLElement>("button, a, label, [role='button']")).find((element) => {
		const text = element.textContent?.replace(/\s+/g, " ").trim() ?? "";
		return element.getAttribute("aria-label") === label || element.getAttribute("title") === label || text === label;
	}) ?? null;
}

function hasBellShapeSvg(element: Element): boolean {
	const paths = Array.from(element.querySelectorAll("svg path")).map((path) =>
		normalizePathData(path.getAttribute("d") ?? ""),
	);
	const hasBellBody = paths.some(
		(path) =>
			path.includes("v4l-2 2h14l-2-2V8") ||
			path.includes("v3l-2 3h16l-2-3V8") ||
			path.includes("v4l-2 2h14l-2-2V8a5") ||
			path.includes("v3l-2 3h16l-2-3V8a6"),
	);
	const hasBellClapper = paths.some((path) => path.includes("M8 16a2 2 0 004 0"));

	return hasBellBody && hasBellClapper;
}

function isNotificationAction(element: Element): boolean {
	const label = [
		element.getAttribute("aria-label"),
		element.getAttribute("title"),
		element.textContent?.replace(/\s+/g, " ").trim(),
	]
		.filter(Boolean)
		.join(" ")
		.toLowerCase();

	return element.getAttribute("data-shell-utility") === "notifications" || label.includes("通知") || label.includes("notification");
}

function getCollapsePriority(element: Element): "L1" | "L2" | "L3" | null {
	const priority = element.getAttribute("data-collapse-priority")?.toUpperCase();
	if (priority === "L1" || priority === "L2" || priority === "L3") return priority;

	return null;
}

function getDirectSummary(element: Element): Element | null {
	return Array.from(element.children).find((child) => child.tagName.toLowerCase() === "summary") ?? null;
}

function assertResizableGroupContract(pageId: string, group: Element | null, groupName: string): string[] {
	if (!group) return [`${pageId}: missing data-resizable-panel-group="${groupName}"`];

	const violations: string[] = [];
	const separators = Array.from(group.querySelectorAll<HTMLElement>("[data-resize-separator]"));
	const requiredAttributes = ["aria-controls", "aria-valuemin", "aria-valuemax", "aria-valuenow"] as const;

	if (separators.length === 0) {
		violations.push(`${pageId}:${groupName}: expected at least one [data-resize-separator]`);
	}

	separators.forEach((separator, index) => {
		const label = `${pageId}:${groupName}:separator ${index + 1}`;

		if (separator.getAttribute("role") !== "separator") {
			violations.push(`${label}: expected role="separator"`);
		}
		if (separator.getAttribute("tabindex") !== "0") {
			violations.push(`${label}: expected tabindex="0"`);
		}
		for (const attribute of requiredAttributes) {
			if (!separator.hasAttribute(attribute) || separator.getAttribute(attribute) === "") {
				violations.push(`${label}: missing ${attribute}`);
			}
		}
	});

	return violations;
}

describe("prototype interaction UX contracts", () => {
	it("keeps every active route on the fixed five-domain anchor rail contract", () => {
		const violations: string[] = [];

		for (const page of activePages()) {
			const document = readPrototypeDocument(page);
			const railItems = Array.from(document.querySelectorAll<HTMLElement>(".shell-rail [data-rail-domain]"));
			const domains = railItems.map((item) => item.dataset.railDomain ?? "");
			const uniqueSortedDomains = [...new Set(domains)].sort();

			if (railItems.length !== railDomains.length) {
				violations.push(`${page.id}: expected 5 rail items, found ${railItems.length}`);
			}
			if (uniqueSortedDomains.join(",") !== [...railDomains].sort().join(",")) {
				violations.push(`${page.id}: expected rail domains ${railDomains.join(",")}, found ${domains.join(",")}`);
			}

			for (const item of railItems) {
				const domain = item.dataset.railDomain ?? "";
				const expectedLabel = railDomainSet.has(domain) ? railLabels[domain as keyof typeof railLabels] : undefined;
				const label = item.getAttribute("aria-label");
				const title = item.getAttribute("title");

				if (item.tagName.toLowerCase() !== "a") {
					violations.push(`${page.id}:${domain}: rail item must be an anchor, found <${item.tagName.toLowerCase()}>`);
				}
				if (expectedLabel && (label !== expectedLabel || title !== expectedLabel)) {
					violations.push(
						`${page.id}:${domain}: expected aria-label/title "${expectedLabel}", found "${label ?? ""}"/"${title ?? ""}"`,
					);
				}
				if ((label && bannedRailLabels.has(label)) || (title && bannedRailLabels.has(title))) {
					violations.push(`${page.id}:${domain}: banned rail label "${label ?? title ?? ""}"`);
				}

				for (const svg of item.querySelectorAll("svg")) {
					if (svg.getAttribute("aria-hidden") !== "true") {
						violations.push(`${page.id}:${domain}: rail SVG must declare aria-hidden="true"`);
					}
				}
			}

			const currentItems = railItems.filter((item) => item.getAttribute("aria-current") === "page");
			if (currentItems.length !== 1) {
				violations.push(`${page.id}: expected exactly one current rail item, found ${currentItems.length}`);
			}
		}

		expect(violations).toEqual([]);
	});

	it("keeps header and strategy action icons collision-free", () => {
		const violations: string[] = [];
		const strategyStudio = activePages().find((page) => page.file === "page-strategy-studio.html");

		for (const page of activePages()) {
			const document = readPrototypeDocument(page);
			const densityToggle = document.querySelector("#density-toggle");
			const densityIcon = densityToggle?.getAttribute("data-icon");
			const densityPathSet = getSvgPathSet(densityToggle);
			const copilot = document.querySelector("[data-shell-utility='copilot']");
			const copilotIcon = copilot?.getAttribute("data-icon");

			if (densityIcon !== "density-levels") {
				violations.push(`${page.id}: #density-toggle expected data-icon="density-levels", found "${densityIcon ?? ""}"`);
			}
			if (!densityPathSet || densityPathSet === hamburgerPathSet) {
				violations.push(`${page.id}: #density-toggle must not use the three-line hamburger SVG path set`);
			}
			if (copilotIcon !== "sparkles" && copilotIcon !== "bot") {
				violations.push(`${page.id}: Copilot expected data-icon="sparkles" or "bot", found "${copilotIcon ?? ""}"`);
			}

			for (const action of document.querySelectorAll<HTMLElement>("button, a, label, [role='button']")) {
				const icon = action.getAttribute("data-icon") ?? action.querySelector("[data-icon]")?.getAttribute("data-icon");
				if (!isNotificationAction(action) && (icon === "bell" || hasBellShapeSvg(action))) {
					const label =
						action.getAttribute("aria-label") ??
						action.getAttribute("title") ??
						action.textContent?.replace(/\s+/g, " ").trim() ??
						"unlabeled action";
					violations.push(`${page.id}: non-notification action "${label}" must not use a bell notification icon`);
				}
			}
		}

		if (!strategyStudio) {
			violations.push("strategy-studio: page not found in active prototypes");
		} else {
			const document = readPrototypeDocument(strategyStudio);
			const validation = findActionByLabel(document, "校验策略");
			const dryRun = findActionByLabel(document, "Dry Run");
			const submitBacktest = findActionByLabel(document, "提交回测");
			const submitIcon = getActionIcon(submitBacktest);

			if (getActionIcon(validation) !== "shield-check") {
				violations.push(
					`strategy-studio: validation expected data-action-icon="shield-check", found "${getActionIcon(validation) ?? ""}"`,
				);
			}
			if (getActionIcon(dryRun) !== "test-tube") {
				violations.push(`strategy-studio: Dry Run expected data-action-icon="test-tube", found "${getActionIcon(dryRun) ?? ""}"`);
			}
			if (submitIcon !== "rocket" && submitIcon !== "timer") {
				violations.push(
					`strategy-studio: submit backtest expected data-action-icon="rocket" or "timer", found "${submitIcon ?? ""}"`,
				);
			}
		}

		expect(violations).toEqual([]);
	});

	it("keeps context sections on the L1/L2/L3 collapsible contract", () => {
		const violations: string[] = [];
		const pagesWithContextSections = activePages().filter(
			(page) => readPrototypeDocument(page).querySelectorAll(".context-section").length > 0,
		);

		for (const page of pagesWithContextSections) {
			const document = readPrototypeDocument(page);
			const sections = Array.from(document.querySelectorAll<HTMLElement>(".context-section"));

			sections.forEach((section, index) => {
				const priority = getCollapsePriority(section);
				const label =
					section.querySelector(".context-section-title, .inspector-section-title")?.textContent?.replace(/\s+/g, " ").trim() ??
					`section ${index + 1}`;
				const isDetails = section.tagName.toLowerCase() === "details";

				if (!section.hasAttribute("data-collapse-priority")) {
					violations.push(`${page.id}:${label}: missing data-collapse-priority`);
				}
				if (section.hasAttribute("data-collapse-priority") && !priority) {
					violations.push(
						`${page.id}:${label}: data-collapse-priority must be L1, L2, or L3, found "${section.getAttribute(
							"data-collapse-priority",
						) ?? ""}"`,
					);
				}

				if ((priority === "L2" || priority === "L3") && !isDetails) {
					violations.push(`${page.id}:${label}: ${priority} context section must be a <details> element`);
				}
				if (!isDetails && priority !== "L1") {
					violations.push(`${page.id}:${label}: plain non-details context section is allowed only for L1`);
				}
				if (isDetails && priority === "L2" && !section.hasAttribute("open")) {
					violations.push(`${page.id}:${label}: L2 details must be open by default`);
				}
				if (isDetails && priority === "L3") {
					if (section.hasAttribute("open")) {
						violations.push(`${page.id}:${label}: L3 details must be collapsed by default`);
					}

					const summary = getDirectSummary(section);
					if (!summary?.querySelector(".collapse-count")) {
						violations.push(`${page.id}:${label}: L3 summary must include .collapse-count`);
					}
					if (!summary?.querySelector(".collapse-summary")) {
						violations.push(`${page.id}:${label}: L3 summary must include .collapse-summary`);
					}
				}
			});
		}

		expect(pagesWithContextSections.length).toBeGreaterThan(0);
		expect(violations).toEqual([]);
	});

	it("exposes P0 resizable panel groups with accessible separators", () => {
		const violations: string[] = [];

		for (const page of activePages()) {
			const document = readPrototypeDocument(page);

			if (page.shellFamily === "catalog" && document.querySelector(".catalog-detail, [data-contract-slot='detail']")) {
				violations.push(
					...assertResizableGroupContract(
						page.id,
						document.querySelector('[data-resizable-panel-group="catalog-main-detail"]'),
						"catalog-main-detail",
					),
				);
			}

			if (page.file === "page-strategy-studio.html" || page.file === "page-agent-console.html") {
				violations.push(
					...assertResizableGroupContract(
						page.id,
						document.querySelector('[data-resizable-panel-group="studio-workspace"]'),
						"studio-workspace",
					),
				);
			}
		}

		expect(violations).toEqual([]);
	});
});
