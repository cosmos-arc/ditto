import { readFileSync, readdirSync } from "node:fs";
import { basename, join, resolve } from "node:path";
import { JSDOM } from "jsdom";
import { chromium } from "playwright";
import { describe, expect, it } from "vitest";

const prototypesDir = resolve(import.meta.dirname, "../docs/designs/specs/prototypes");
const contractsDir = resolve(import.meta.dirname, "../docs/contracts/pages");
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
const railHrefs: Record<(typeof railDomains)[number], string> = {
	home: "page-home.html",
	markets: "page-cross-market.html",
	research: "page-research.html",
	trading: "page-trading-overview.html",
	platform: "page-platform.html",
};
const bannedRailLabels = new Set(["AI", "运维", "Platform", "Home", "Markets", "Research", "Trading"]);
const hamburgerPathSet = ["M3 4h14", "M3 10h14", "M3 16h14"].sort().join("|");
const contextSectionTitleSelector = ".context-section-title, .inspector-section-title, .section-title, [data-section-title]";
const bottomTrayPageIds = ["strategy-studio", "agent-console", "platform", "trading-overview"] as const;
const bottomTrayPageIdSet = new Set<string>(bottomTrayPageIds);
const bottomTrayStates = ["collapsed", "peek", "expanded"] as const;
const bottomTrayStateSet = new Set<string>(bottomTrayStates);
const bottomTrayUiByState: Record<(typeof bottomTrayStates)[number], { ariaExpanded: string; symbol: string }> = {
	collapsed: { ariaExpanded: "false", symbol: "⌄" },
	peek: { ariaExpanded: "true", symbol: "▴" },
	expanded: { ariaExpanded: "true", symbol: "—" },
};
const playwrightTestTimeoutMs = 15_000;
const pageDomainById: Record<string, (typeof railDomains)[number]> = {
	home: "home",
	"cross-market": "markets",
	"markets-screener": "markets",
	"instrument-hub": "markets",
	"markets-intelligence": "markets",
	"markets-calendar": "markets",
	"a-shares": "markets",
	watchlist: "markets",
	research: "research",
	"strategy-studio": "research",
	"strategies-detail": "research",
	"factor-analysis": "research",
	"backtest-result": "research",
	"regime-monitor": "research",
	"factor-list": "research",
	"strategy-list": "research",
	"backtest-list": "research",
	"experiment-list": "research",
	"universe-list": "research",
	"trading-overview": "trading",
	"signals-inbox": "trading",
	"orders-ledger": "trading",
	"risk-center": "trading",
	portfolio: "trading",
	platform: "platform",
	"agent-console": "platform",
	"platform-settings": "platform",
};

type ManifestPage = {
	id: string;
	file: string;
	shellFamily?: string;
};

type EditionManifest = {
	pages: ManifestPage[];
};

type PageContract = {
	id: string;
	prototypeRef?: string;
	route?: string;
};

type BottomTrayState = (typeof bottomTrayStates)[number];

function readJson<T>(path: string): T {
	return JSON.parse(readFileSync(path, "utf8")) as T;
}

let manifestCache: EditionManifest | undefined;
const prototypeDocumentCache = new Map<string, Document>();
let pageContractsCache: PageContract[] | undefined;
let contractRouteByPageIdCache: Map<string, string> | undefined;
let contractRouteByPrototypeFileCache: Map<string, string> | undefined;
let sharedInteractionsScriptCache: string | undefined;

function readManifest(): EditionManifest {
	manifestCache ??= readJson<EditionManifest>(join(prototypesDir, ".edition-manifest.json"));
	return manifestCache;
}

function readPageContracts(): PageContract[] {
	pageContractsCache ??= readdirSync(contractsDir)
		.filter((file) => file.endsWith(".json"))
		.map((file) => readJson<PageContract>(join(contractsDir, file)));
	return pageContractsCache;
}

function contractRouteByPageId(): Map<string, string> {
	if (contractRouteByPageIdCache) return contractRouteByPageIdCache;

	contractRouteByPageIdCache = new Map(
		readPageContracts().flatMap((contract) => (contract.route ? [[contract.id, contract.route]] : [])),
	);
	return contractRouteByPageIdCache;
}

function contractRouteByPrototypeFile(): Map<string, string> {
	if (contractRouteByPrototypeFileCache) return contractRouteByPrototypeFileCache;

	contractRouteByPrototypeFileCache = new Map(
		readPageContracts().flatMap((contract) =>
			contract.prototypeRef && contract.route ? [[basename(contract.prototypeRef), contract.route]] : [],
		),
	);
	return contractRouteByPrototypeFileCache;
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

function getActivePageById(pageId: string): ManifestPage {
	const page = activePages().find((candidate) => candidate.id === pageId);
	if (!page) throw new Error(`${pageId}: expected active prototype page`);

	return page;
}

function getPrototypeUrl(page: ManifestPage): string {
	return `file://${join(prototypesDir, page.file)}`;
}

function readSharedInteractionsScript(): string {
	sharedInteractionsScriptCache ??= readFileSync(join(prototypesDir, "shared/prototype-interactions.js"), "utf8");
	return sharedInteractionsScriptCache;
}

function installInteractiveWindowStubs(window: JSDOM["window"]): void {
	class MockIntersectionObserver implements IntersectionObserver {
		readonly root: Element | Document | null = null;
		readonly rootMargin = "0px";
		readonly thresholds: ReadonlyArray<number> = [0];

		disconnect(): void {
			// JSDOM contract test stub.
		}

		observe(): void {
			// JSDOM contract test stub.
		}

		takeRecords(): IntersectionObserverEntry[] {
			return [];
		}

		unobserve(): void {
			// JSDOM contract test stub.
		}
	}

	Object.defineProperty(window, "matchMedia", {
		configurable: true,
		value: (query: string): MediaQueryList => ({
			matches: false,
			media: query,
			onchange: null,
			addListener: () => undefined,
			removeListener: () => undefined,
			addEventListener: () => undefined,
			removeEventListener: () => undefined,
			dispatchEvent: () => true,
		}),
	});
	Object.defineProperty(window, "IntersectionObserver", {
		configurable: true,
		value: MockIntersectionObserver,
	});
}

function readInteractivePrototypeDocument(page: ManifestPage, prepare?: (document: Document) => void): Document {
	const dom = new JSDOM(readFileSync(join(prototypesDir, page.file), "utf8"), {
		pretendToBeVisual: true,
		runScripts: "outside-only",
		url: `https://prototype.local/${page.file}`,
	});
	const { document } = dom.window;

	prepare?.(document);
	installInteractiveWindowStubs(dom.window);
	dom.window.eval(readSharedInteractionsScript());

	if (document.readyState === "loading") {
		document.dispatchEvent(new dom.window.Event("DOMContentLoaded", { bubbles: true }));
	}

	return document;
}

function normalizePathData(value: string): string {
	return value.replace(/\s+/g, " ").trim();
}

function toRailDomain(value: string | null | undefined): (typeof railDomains)[number] | null {
	return value && railDomainSet.has(value) ? (value as (typeof railDomains)[number]) : null;
}

function getDomainFromRoute(route: string | null | undefined): (typeof railDomains)[number] | null {
	if (!route) return null;
	if (route === "/") return "home";
	if (route === "/markets" || route.startsWith("/markets/")) return "markets";
	if (route === "/research" || route.startsWith("/research/")) return "research";
	if (route === "/trading" || route.startsWith("/trading/")) return "trading";
	if (route === "/platform" || route.startsWith("/platform/")) return "platform";

	return null;
}

function getContractRoute(page: ManifestPage): string | null {
	return contractRouteByPrototypeFile().get(page.file) ?? contractRouteByPageId().get(page.id) ?? null;
}

function getPageDomain(page: ManifestPage): (typeof railDomains)[number] | null {
	return getDomainFromRoute(getContractRoute(page)) ?? pageDomainById[page.id] ?? null;
}

function getPrototypeDeclaredDomain(document: Document): (typeof railDomains)[number] | null {
	const shellDomain = document.querySelector<HTMLElement>(
		[
			"[data-page-domain]",
			"[data-shell-domain]",
			".shell-command[data-domain]",
			".shell-radar[data-domain]",
			".shell-analytical[data-domain]",
			".shell-catalog[data-domain]",
			".shell-studio[data-domain]",
			".shell-ops[data-domain]",
			".shell-object[data-domain]",
		].join(", "),
	);
	const candidates = [
		document.documentElement.dataset.domain,
		document.body.dataset.domain,
		shellDomain?.dataset.pageDomain,
		shellDomain?.dataset.shellDomain,
		shellDomain?.dataset.domain,
	];

	for (const candidate of candidates) {
		const domain = toRailDomain(candidate);
		if (domain) return domain;
	}

	return null;
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

function getBottomTrayState(element: Element): BottomTrayState | null {
	const state = element.getAttribute("data-bottom-tray-state");
	return state && bottomTrayStateSet.has(state) ? (state as BottomTrayState) : null;
}

function getDirectSummary(element: Element): Element | null {
	return Array.from(element.children).find((child) => child.tagName.toLowerCase() === "summary") ?? null;
}

function getContextSectionLabel(section: Element, index: number): string {
	return section.querySelector(contextSectionTitleSelector)?.textContent?.replace(/\s+/g, " ").trim() ?? `section ${index + 1}`;
}

function parseFiniteNumber(value: string | null): number | null {
	if (!value?.trim()) return null;

	const parsed = Number(value);
	return Number.isFinite(parsed) ? parsed : null;
}

function assertResizableGroupContract(pageId: string, group: Element | null, groupName: string): string[] {
	if (!group) return [`${pageId}: missing data-resizable-panel-group="${groupName}"`];

	const violations: string[] = [];
	const document = group.ownerDocument;
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

		const controls = separator.getAttribute("aria-controls")?.trim();
		if (controls) {
			for (const controlledId of controls.split(/\s+/)) {
				if (!document.getElementById(controlledId)) {
					violations.push(`${label}: aria-controls target "${controlledId}" does not exist`);
				}
			}
		}

		const min = parseFiniteNumber(separator.getAttribute("aria-valuemin"));
		const max = parseFiniteNumber(separator.getAttribute("aria-valuemax"));
		const now = parseFiniteNumber(separator.getAttribute("aria-valuenow"));

		if (separator.hasAttribute("aria-valuemin") && min === null) {
			violations.push(`${label}: aria-valuemin must be a finite number`);
		}
		if (separator.hasAttribute("aria-valuemax") && max === null) {
			violations.push(`${label}: aria-valuemax must be a finite number`);
		}
		if (separator.hasAttribute("aria-valuenow") && now === null) {
			violations.push(`${label}: aria-valuenow must be a finite number`);
		}
		if (min !== null && max !== null && min > max) {
			violations.push(`${label}: aria-valuemin must be less than or equal to aria-valuemax`);
		}
		if (min !== null && max !== null && now !== null && (now < min || now > max)) {
			violations.push(`${label}: aria-valuenow must be between aria-valuemin and aria-valuemax`);
		}
	});

	return violations;
}

async function readBottomTrayStatusMetrics(page: import("playwright").Page) {
	return page.$eval("[data-bottom-tray]", (tray) => {
		const toggle = tray.querySelector<HTMLElement>("[data-bottom-tray-toggle]");
		const contentId = toggle?.getAttribute("aria-controls") ?? "";
		const content = contentId ? document.getElementById(contentId) : null;
		if (!content) throw new Error(`missing bottom tray content "${contentId}"`);

		const trayRect = tray.getBoundingClientRect();
		const contentRect = content.getBoundingClientRect();
		const trayStyle = getComputedStyle(tray);
		const contentStyle = getComputedStyle(content);

		return {
			state: tray.getAttribute("data-bottom-tray-state") ?? "",
			height: trayRect.height,
			flexBasis: trayStyle.flexBasis,
			overflow: trayStyle.overflow,
			contentBottom: contentRect.bottom,
			contentClientHeight: content.clientHeight,
			contentOverflow: contentStyle.overflow,
			contentScrollHeight: content.scrollHeight,
			trayBottom: trayRect.bottom,
		};
	});
}

async function cycleBottomTrayTo(page: import("playwright").Page, state: BottomTrayState) {
	for (let attempt = 0; attempt < bottomTrayStates.length; attempt++) {
		const current = await page.$eval("[data-bottom-tray]", (tray) => tray.getAttribute("data-bottom-tray-state"));
		if (current === state) return;

		await page.click("[data-bottom-tray-toggle]");
	}

	throw new Error(`bottom tray did not reach ${state}`);
}

async function waitForExpandedStatusBarLayout(page: import("playwright").Page, collapsedHeight: number) {
	await page.waitForFunction(
		(height) => {
			const tray = document.querySelector<HTMLElement>("[data-bottom-tray]");
			const toggle = tray?.querySelector<HTMLElement>("[data-bottom-tray-toggle]");
			const contentId = toggle?.getAttribute("aria-controls") ?? "";
			const content = contentId ? document.getElementById(contentId) : null;

			return (
				tray?.getAttribute("data-bottom-tray-state") === "expanded" &&
				tray.getBoundingClientRect().height > height &&
				Boolean(content && content.clientHeight + 1 >= content.scrollHeight)
			);
		},
		collapsedHeight,
		{ timeout: 1_500 },
	);
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
				const expectedHref = railDomainSet.has(domain) ? railHrefs[domain as keyof typeof railHrefs] : undefined;
				const label = item.getAttribute("aria-label");
				const title = item.getAttribute("title");
				const href = item.getAttribute("href");

				if (item.tagName.toLowerCase() !== "a") {
					violations.push(`${page.id}:${domain}: rail item must be an anchor, found <${item.tagName.toLowerCase()}>`);
				}
				if (expectedHref && href !== expectedHref) {
					violations.push(`${page.id}:${domain}: expected href="${expectedHref}", found "${href ?? ""}"`);
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
			} else {
				const pageDomain = getPageDomain(page);
				const currentDomain = currentItems[0].dataset.railDomain ?? "";
				if (pageDomain && currentDomain !== pageDomain) {
					violations.push(`${page.id}: current rail domain expected "${pageDomain}", found "${currentDomain}"`);
				}
			}

			const contractDomain = getDomainFromRoute(getContractRoute(page));
			const declaredDomain = getPrototypeDeclaredDomain(document);
			if (contractDomain && declaredDomain && declaredDomain !== contractDomain) {
				violations.push(`${page.id}: data-domain expected "${contractDomain}" from page contract, found "${declaredDomain}"`);
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
				const label = getContextSectionLabel(section, index);
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
				if (isDetails && (priority === "L2" || priority === "L3")) {
					const summary = getDirectSummary(section);

					if (!summary?.matches("summary.context-section-header")) {
						violations.push(`${page.id}:${label}: ${priority} details must include direct summary.context-section-header`);
					}
					if (!summary?.querySelector(contextSectionTitleSelector)) {
						violations.push(`${page.id}:${label}: ${priority} summary must include a section title`);
					}
					if (!summary?.querySelector(".collapse-count")) {
						violations.push(`${page.id}:${label}: ${priority} summary must include .collapse-count`);
					}
				}
				if (isDetails && priority === "L3") {
					if (section.hasAttribute("open")) {
						violations.push(`${page.id}:${label}: L3 details must be collapsed by default`);
					}

					const summary = getDirectSummary(section);
					if (!summary?.querySelector(".collapse-summary")) {
						violations.push(`${page.id}:${label}: L3 summary must include .collapse-summary`);
					}
				}
			});
		}

		expect(pagesWithContextSections.length).toBeGreaterThan(0);
		expect(violations).toEqual([]);
	});

	it("keeps bottom trays on the collapsed/peek/expanded accessibility contract", () => {
		const violations: string[] = [];
		const pagesWithBottomTrays: string[] = [];

		for (const page of activePages()) {
			const document = readPrototypeDocument(page);
			const trays = Array.from(document.querySelectorAll<HTMLElement>("[data-bottom-tray]"));

			if (trays.length > 0) pagesWithBottomTrays.push(page.id);
			if (bottomTrayPageIdSet.has(page.id) && trays.length !== 1) {
				violations.push(`${page.id}: expected exactly one [data-bottom-tray], found ${trays.length}`);
			}
			if (!bottomTrayPageIdSet.has(page.id) && trays.length > 0) {
				violations.push(`${page.id}: unexpected [data-bottom-tray]`);
			}

			trays.forEach((tray, index) => {
				const label = `${page.id}:bottom tray ${index + 1}`;
				const state = getBottomTrayState(tray);
				const toggle = tray.querySelector<HTMLElement>("[data-bottom-tray-toggle]");
				const controls = toggle?.getAttribute("aria-controls")?.trim() ?? "";
				const content = controls ? document.getElementById(controls) : null;
				const ariaLabel = toggle?.getAttribute("aria-label")?.trim() ?? "";

				if (!state) {
					violations.push(
						`${label}: data-bottom-tray-state must be collapsed, peek, or expanded; found "${tray.getAttribute(
							"data-bottom-tray-state",
						) ?? ""}"`,
					);
				}
				if (!toggle) {
					violations.push(`${label}: missing [data-bottom-tray-toggle]`);
				}
				if (toggle && !controls) {
					violations.push(`${label}: toggle missing aria-controls`);
				}
				if (controls && !content) {
					violations.push(`${label}: aria-controls target "${controls}" does not exist`);
				}
				if (toggle && !ariaLabel) {
					violations.push(`${label}: toggle must have an explicit aria-label`);
				}
				if (toggle && state) {
					const expectedExpanded = bottomTrayUiByState[state].ariaExpanded;
					const actualExpanded = toggle.getAttribute("aria-expanded");
					if (actualExpanded !== expectedExpanded) {
						violations.push(`${label}: expected aria-expanded="${expectedExpanded}" for ${state}, found "${actualExpanded ?? ""}"`);
					}
				}
			});
		}

		expect(pagesWithBottomTrays.sort()).toEqual([...bottomTrayPageIds].sort());
		expect(violations).toEqual([]);
	});

	it("cycles bottom tray state through shared prototype interactions", () => {
		for (const pageId of bottomTrayPageIds) {
			const page = activePages().find((candidate) => candidate.id === pageId);
			expect(page, `${pageId}: expected active prototype page`).toBeDefined();
			if (!page) continue;

			const document = readInteractivePrototypeDocument(page, (preparedDocument) => {
				preparedDocument.querySelector("[data-bottom-tray]")?.setAttribute("data-bottom-tray-state", "collapsed");
			});
			const tray = document.querySelector<HTMLElement>("[data-bottom-tray]");
			expect(tray, `${pageId}: expected [data-bottom-tray]`).not.toBeNull();
			if (!tray) continue;

			const toggle = tray.querySelector<HTMLButtonElement>("[data-bottom-tray-toggle]");
			expect(toggle, `${pageId}: expected [data-bottom-tray-toggle]`).not.toBeNull();
			if (!toggle) continue;

			const controls = toggle.getAttribute("aria-controls") ?? "";
			const content = controls ? document.getElementById(controls) : null;
			expect(content, `${pageId}: expected controlled bottom tray content`).not.toBeNull();
			expect(content?.textContent?.replace(/\s+/g, " ").trim(), `${pageId}: expected controlled content text`).not.toBe("");

			const labels = new Set<string>();
			const assertState = (state: BottomTrayState): void => {
				const expected = bottomTrayUiByState[state];
				const label = toggle.getAttribute("aria-label")?.trim() ?? "";

				expect(tray.getAttribute("data-bottom-tray-state"), `${pageId}: state`).toBe(state);
				expect(toggle.getAttribute("aria-expanded"), `${pageId}: aria-expanded for ${state}`).toBe(expected.ariaExpanded);
				expect(toggle.textContent?.trim(), `${pageId}: visible toggle symbol for ${state}`).toBe(expected.symbol);
				expect(label, `${pageId}: aria-label for ${state}`).not.toBe("");
				expect(content?.getAttribute("aria-hidden"), `${pageId}: content aria-hidden for ${state}`).toBe(
					state === "collapsed" ? "true" : "false",
				);
				labels.add(label);
			};

			assertState("collapsed");
			toggle.click();
			assertState("peek");
			toggle.click();
			assertState("expanded");
			toggle.click();
			assertState("collapsed");
			expect(labels.size, `${pageId}: aria-label should communicate each state transition`).toBe(3);
		}
	});

	it("keeps strategy log tab visibility isolated from bottom tray visibility", () => {
		const document = readInteractivePrototypeDocument(getActivePageById("strategy-studio"));
		const tray = document.querySelector<HTMLElement>("[data-bottom-tray]");
		const toggle = tray?.querySelector<HTMLButtonElement>("[data-bottom-tray-toggle]");
		const validationPanel = document.querySelector<HTMLElement>('[data-tab-panel="validation"]');
		const dryRunPanel = document.querySelector<HTMLElement>('[data-tab-panel="dry-run"]');
		const dryRunTab = document.querySelector<HTMLElement>('[data-log-tab="dry-run"]');

		expect(tray).not.toBeNull();
		expect(toggle).not.toBeNull();
		expect(validationPanel).not.toBeNull();
		expect(dryRunPanel).not.toBeNull();
		expect(dryRunTab).not.toBeNull();
		if (!tray || !toggle || !validationPanel || !dryRunPanel || !dryRunTab) return;

		dryRunTab.click();
		expect(validationPanel.getAttribute("aria-hidden")).toBe("true");
		expect(validationPanel.style.display).toBe("none");
		expect(dryRunPanel.getAttribute("aria-hidden")).toBe("false");
		expect(dryRunPanel.style.display).not.toBe("none");

		toggle.click();
		expect(tray.getAttribute("data-bottom-tray-state")).toBe("expanded");
		expect(validationPanel.getAttribute("aria-hidden")).toBe("true");
		expect(validationPanel.style.display).toBe("none");
		expect(dryRunPanel.getAttribute("aria-hidden")).toBe("false");
		expect(dryRunPanel.style.display).not.toBe("none");

		toggle.click();
		expect(tray.getAttribute("data-bottom-tray-state")).toBe("collapsed");
		expect(validationPanel.getAttribute("aria-hidden")).toBe("true");
		expect(dryRunPanel.getAttribute("aria-hidden")).toBe("false");
	});

	it("lets status-bar bottom trays expand without clipping content in browser layout", async () => {
		const browser = await chromium.launch({ channel: "chromium" });

		try {
			for (const pageId of ["agent-console", "trading-overview"] as const) {
				const page = await browser.newPage({ viewport: { width: 1536, height: 1080 } });

				try {
					await page.goto(getPrototypeUrl(getActivePageById(pageId)), { waitUntil: "load" });
					await cycleBottomTrayTo(page, "collapsed");
					const collapsed = await readBottomTrayStatusMetrics(page);

					await cycleBottomTrayTo(page, "expanded");
					await waitForExpandedStatusBarLayout(page, collapsed.height);
					const expanded = await readBottomTrayStatusMetrics(page);

					expect(expanded.state, `${pageId}: expanded state`).toBe("expanded");
					expect(expanded.height, `${pageId}: expanded height should exceed collapsed height`).toBeGreaterThan(collapsed.height);
					expect(expanded.flexBasis, `${pageId}: expanded flex-basis`).toBe("auto");
					expect(expanded.overflow, `${pageId}: expanded overflow`).not.toBe("hidden");
					expect(expanded.contentScrollHeight, `${pageId}: content scroll height`).toBeLessThanOrEqual(
						expanded.contentClientHeight + 1,
					);
					expect(expanded.contentBottom, `${pageId}: content bottom inside tray`).toBeLessThanOrEqual(expanded.trayBottom + 1);
				} finally {
					await page.close();
				}
			}
		} finally {
			await browser.close();
		}
	}, playwrightTestTimeoutMs);

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
