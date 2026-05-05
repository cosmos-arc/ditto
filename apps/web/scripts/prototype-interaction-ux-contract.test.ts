import { readFileSync, readdirSync } from "node:fs";
import { basename, join, resolve } from "node:path";
import { JSDOM } from "jsdom";
import { chromium, type Browser } from "playwright";
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
const railIcons: Record<(typeof railDomains)[number], string> = {
	home: "home",
	markets: "trending-up",
	research: "book-open",
	trading: "candlestick-chart",
	platform: "server-cog",
};
const bannedRailLabels = new Set(["AI", "运维", "Platform", "Home", "Markets", "Research", "Trading"]);
const hamburgerPathSet = ["M3 4h14", "M3 10h14", "M3 16h14"].sort().join("|");
const contextSectionTitleSelector = ".context-section-title, .inspector-section-title, .section-title, [data-section-title]";
const bottomTrayPageIds = ["strategy-studio", "platform", "trading-overview"] as const;
const bottomTrayPageIdSet = new Set<string>(bottomTrayPageIds);
const bottomTrayStates = ["collapsed", "peek", "expanded"] as const;
const bottomTrayStateSet = new Set<string>(bottomTrayStates);
const bottomTrayUiByState: Record<(typeof bottomTrayStates)[number], { ariaExpanded: string; symbol: string }> = {
	collapsed: { ariaExpanded: "false", symbol: "⌄" },
	peek: { ariaExpanded: "true", symbol: "▴" },
	expanded: { ariaExpanded: "true", symbol: "—" },
};
const commandContextActionsByPageId: Record<string, string[]> = {
	home: ["review-signal", "open-risk", "open-orders", "explain-priority"],
	watchlist: ["generate-signal", "open-instrument-hub", "send-to-research", "remove-watch"],
	"strategy-list": ["run-backtest", "clone-strategy", "view-recent-runs", "pause-strategy"],
	"backtest-list": ["add-to-compare", "view-curve", "copy-params", "generate-report"],
	"signals-inbox": ["approve", "reject", "send-to-order", "view-evidence"],
	platform: ["retry", "view-logs", "mute-alert", "create-incident"],
};
const tableExpertContractPageIds = [
	"watchlist",
	"strategy-list",
	"backtest-list",
	"signals-inbox",
	"platform",
	"factor-list",
	"experiment-list",
	"universe-list",
	"markets-screener",
	"orders-ledger",
] as const;
const tableExpertContractAttributes = [
	"data-table-column-resize-ready",
	"data-table-freeze-ready",
	"data-row-context-menu-ready",
] as const;
const interactiveSelector = [
	"button",
	"a[href]",
	"[role='button']",
	"[role='tab']",
	"label[role='button']",
	"[data-answer-action]",
].join(",");
const targetSizeAuditViewports = [
	{ name: "1366x768", width: 1366, height: 768 },
	{ name: "1536x1080", width: 1536, height: 1080 },
] as const;
const semanticPolishPageIds = ["alpha-explorer", "agent-console-v2", "signals-inbox", "home"] as const;
const navigationTimeoutMs = 10_000;
const targetSizeNavigationTimeoutMs = 30_000;
const playwrightTestTimeoutMs = 15_000;
const jsdomInteractionTestTimeoutMs = 15_000;
const chromiumLaunchOptions = {
	channel: "chromium",
	args: ["--disable-gpu"],
} as const;
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
	status?: string;
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
const prototypeHtmlCache = new Map<string, string>();
const prototypeDocumentCache = new Map<string, Document>();
let pageContractsCache: PageContract[] | undefined;
let contractRouteByPageIdCache: Map<string, string> | undefined;
let contractRouteByPrototypeFileCache: Map<string, string> | undefined;
let sharedInteractionsScriptCache: string | undefined;
let screenerWorkflowScriptCache: string | undefined;

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
		page.status !== "archived-specimen" &&
		!archivedPrototypeIds.has(page.id)
	);
}

function activePages(): ManifestPage[] {
	return readManifest().pages.filter(isActiveRoutePrototype);
}

function readPrototypeHtml(page: ManifestPage): string {
	const path = join(prototypesDir, page.file);
	const cached = prototypeHtmlCache.get(path);
	if (cached) return cached;

	const html = readFileSync(path, "utf8");
	prototypeHtmlCache.set(path, html);
	return html;
}

function getStyleBlocks(html: string): string {
	return [...html.matchAll(/<style[^>]*>([\s\S]*?)<\/style>/gi)]
		.map((match) => match[1])
		.join("\n");
}

function readPrototypeDocument(page: ManifestPage): Document {
	const path = join(prototypesDir, page.file);
	const cached = prototypeDocumentCache.get(path);
	if (cached) return cached;

	const document = new JSDOM(readPrototypeHtml(page)).window.document;
	prototypeDocumentCache.set(path, document);
	return document;
}

function collectFocusRuleViolations(page: ManifestPage): string[] {
	const violations: string[] = [];
	const css = getStyleBlocks(readPrototypeHtml(page));
	const focusRule = /([^{}]+:focus-visible[^{}]*)\{([^{}]*)\}/gi;

	for (const match of css.matchAll(focusRule)) {
		const selector = match[1].trim();
		const body = match[2];
		if (/resize-separator|\[data-resize-separator\]/.test(selector)) continue;
		if (!/--(?:brand-accent|interaction-selected-[a-z-]+)/.test(body)) continue;
		if (/--interaction-focus-ring/.test(body)) continue;

		violations.push(`${page.id}:${selector}`);
	}

	return violations;
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

function readScreenerWorkflowScript(): string {
	screenerWorkflowScriptCache ??= readFileSync(join(prototypesDir, "shared/screener-workflow.js"), "utf8");
	return screenerWorkflowScriptCache;
}

function evaluateScreenerWorkflowScript(window: JSDOM["window"]): void {
	const runScreenerWorkflow = new Function(
		"window",
		"document",
		"getComputedStyle",
		"CustomEvent",
		"IntersectionObserver",
		"MutationObserver",
		"requestAnimationFrame",
		"cancelAnimationFrame",
		"setTimeout",
		"clearTimeout",
		readScreenerWorkflowScript(),
	);

	runScreenerWorkflow(
		window,
		window.document,
		window.getComputedStyle.bind(window),
		window.CustomEvent,
		window.IntersectionObserver,
		window.MutationObserver,
		window.requestAnimationFrame.bind(window),
		window.cancelAnimationFrame.bind(window),
		window.setTimeout.bind(window),
		window.clearTimeout.bind(window),
	);
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

function evaluateSharedInteractionsScript(window: JSDOM["window"]): void {
	const runSharedInteractions = new Function(
		"window",
		"document",
		"getComputedStyle",
		"CustomEvent",
		"IntersectionObserver",
		"MutationObserver",
		"requestAnimationFrame",
		"cancelAnimationFrame",
		"setTimeout",
		"clearTimeout",
		readSharedInteractionsScript(),
	);

	runSharedInteractions(
		window,
		window.document,
		window.getComputedStyle.bind(window),
		window.CustomEvent,
		window.IntersectionObserver,
		window.MutationObserver,
		window.requestAnimationFrame.bind(window),
		window.cancelAnimationFrame.bind(window),
		window.setTimeout.bind(window),
		window.clearTimeout.bind(window),
	);
}

function readInteractivePrototypeDocument(page: ManifestPage, prepare?: (document: Document) => void): Document {
	const dom = new JSDOM(readFileSync(join(prototypesDir, page.file), "utf8"), {
		pretendToBeVisual: true,
		url: `https://prototype.local/${page.file}`,
	});
	const { document } = dom.window;

	prepare?.(document);
	installInteractiveWindowStubs(dom.window);
	evaluateSharedInteractionsScript(dom.window);

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

function hasAccessibleName(element: Element): boolean {
	const directName = [
		element.getAttribute("aria-label"),
		element.getAttribute("title"),
	]
		.map((value) => value?.trim())
		.some(Boolean);
	if (directName) return true;

	const labelledBy = element.getAttribute("aria-labelledby")?.trim();
	if (!labelledBy) return false;

	return labelledBy
		.split(/\s+/)
		.some((id) => Boolean(element.ownerDocument.getElementById(id)?.textContent?.trim()));
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

function getDefaultPrototypeRoot(document: Document): ParentNode {
	return document.querySelector("#default-view") ?? document.body;
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
	const requiredAttributes = ["aria-controls", "aria-valuemin", "aria-valuemax", "aria-valuenow", "aria-valuetext"] as const;

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

function createResizablePanelDom(
	url: string,
	prepareWindow?: (window: JSDOM["window"]) => void,
): { document: Document; group: HTMLElement; separator: HTMLElement } {
	const dom = new JSDOM(
		`<!doctype html>
		<html>
			<body>
				<div id="workspace" data-resizable-panel-group="test-workspace" data-resize-var="--prototype-detail-width">
					<section id="test-main"></section>
					<div
						class="resize-separator"
						data-resize-separator
						data-resize-var="--prototype-detail-width"
						data-resize-default="320"
						data-resize-min="220"
						data-resize-max="520"
						role="separator"
						tabindex="0"
						aria-label="调整测试面板宽度"
						aria-orientation="vertical"
						aria-controls="test-main test-detail"
						aria-valuemin="220"
						aria-valuemax="520"
						aria-valuenow="320"
						aria-valuetext="调整测试面板宽度 320 像素"
					></div>
					<aside id="test-detail"></aside>
				</div>
			</body>
		</html>`,
		{ pretendToBeVisual: true, url },
	);
	const { document } = dom.window;
	const group = document.getElementById("workspace");
	const separator = document.querySelector<HTMLElement>("[data-resize-separator]");

	expect(group).not.toBeNull();
	expect(separator).not.toBeNull();
	if (!(group instanceof dom.window.HTMLElement) || !separator) {
		throw new Error("expected resizable panel fixture to be present");
	}

	prepareWindow?.(dom.window);
	installInteractiveWindowStubs(dom.window);
	evaluateSharedInteractionsScript(dom.window);
	if (document.readyState === "loading") {
		document.dispatchEvent(new dom.window.Event("DOMContentLoaded", { bubbles: true }));
	}

	return { document, group, separator };
}

function parseCommandContextActions(element: Element): Set<string> {
	return new Set(
		(element.getAttribute("data-command-context-actions") ?? "")
			.split(",")
			.map((action) => action.trim())
			.filter(Boolean),
	);
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

async function closePlaywrightPage(page: import("playwright").Page): Promise<void> {
	if (page.isClosed()) return;

	await Promise.race([
		page.close().catch(() => undefined),
		new Promise<void>((resolve) => {
			setTimeout(resolve, 500);
		}),
	]);
}

async function closePlaywrightBrowser(browser: Browser): Promise<void> {
	await Promise.race([
		browser.close().catch(() => undefined),
		new Promise<void>((resolve) => {
			setTimeout(resolve, 1_000);
		}),
	]);
}

async function launchPrototypeBrowser(): Promise<Browser> {
	return chromium.launch(chromiumLaunchOptions);
}

async function collectTargetSizeViolations(
	page: import("playwright").Page,
	pageMeta: ManifestPage,
	viewportName: string,
): Promise<string[]> {
	await page.goto(getPrototypeUrl(pageMeta), {
		waitUntil: "domcontentloaded",
		timeout: targetSizeNavigationTimeoutMs,
	});
	const pageViolations = await page.$$eval(interactiveSelector, (elements) => {
		function isInsideClosedDetails(element: Element): boolean {
			const closedDetails = element.closest("details:not([open])");
			return Boolean(closedDetails && !element.closest("summary"));
		}

		function isVisibleTarget(element: Element): boolean {
			if (element.closest("[hidden], [aria-hidden='true']")) return false;
			if (isInsideClosedDetails(element)) return false;

			const rect = element.getBoundingClientRect();
			if (rect.width <= 0 || rect.height <= 0) return false;
			if (
				rect.right <= 0 ||
				rect.bottom <= 0 ||
				rect.left >= window.innerWidth ||
				rect.top >= window.innerHeight
			) {
				return false;
			}

			const style = getComputedStyle(element);
			return style.display !== "none" && style.visibility !== "hidden";
		}

		function targetLabel(element: Element): string {
			const htmlElement = element as HTMLElement;
			return [
				element.getAttribute("aria-label"),
				element.getAttribute("title"),
				htmlElement.innerText,
				element.id ? `#${element.id}` : "",
				element.className ? `.${String(element.className).trim().replace(/\s+/g, ".")}` : "",
				element.tagName.toLowerCase(),
			]
				.filter(Boolean)
				.join(" ")
				.replace(/\s+/g, " ")
				.trim()
				.slice(0, 96);
		}

		return elements.flatMap((element) => {
			if (element.closest("[data-target-size-exception]")) return [];
			if (!isVisibleTarget(element)) return [];

			const rect = element.getBoundingClientRect();
			if (rect.width >= 24 && rect.height >= 24) return [];

			return [
				`${targetLabel(element)} ${Math.round(rect.width * 10) / 10}x${Math.round(rect.height * 10) / 10}`,
			];
		});
	});

	return pageViolations.map((violation) => `${pageMeta.id}@${viewportName}: ${violation}`);
}

describe("prototype interaction UX contracts", () => {
	it("activates role button elements from Enter and Space through shared interactions", () => {
		const dom = new JSDOM(
			`<!doctype html><html><body><div id="target" role="button" tabindex="0" aria-label="测试动作"></div></body></html>`,
			{
				pretendToBeVisual: true,
				url: "https://prototype.local/role-button-contract.html",
			},
		);
		const { document } = dom.window;
		const target = document.getElementById("target");
		let clickCount = 0;

		expect(target).not.toBeNull();
		if (!target) return;

		target.addEventListener("click", () => {
			clickCount += 1;
		});

		installInteractiveWindowStubs(dom.window);
		evaluateSharedInteractionsScript(dom.window);
		if (document.readyState === "loading") {
			document.dispatchEvent(new dom.window.Event("DOMContentLoaded", { bubbles: true }));
		}

		target.dispatchEvent(new dom.window.KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
		target.dispatchEvent(new dom.window.KeyboardEvent("keydown", { key: " ", bubbles: true }));

		expect(clickCount).toBe(2);
	});

	it("does not proxy nested native controls through parent role button keyboard activation", () => {
		const dom = new JSDOM(
			`<!doctype html>
			<html>
				<body>
					<div id="outer" role="button" tabindex="0" aria-label="审批卡片">
						<span id="plain-child">普通文本</span>
						<button id="inner-button" type="button">批准</button>
						<label id="inner-label" for="inner-input">确认</label>
						<input id="inner-input" type="checkbox">
					</div>
				</body>
			</html>`,
			{
				pretendToBeVisual: true,
				url: "https://prototype.local/nested-role-button-contract.html",
			},
		);
		const { document } = dom.window;
		const outer = document.getElementById("outer");
		let outerClicks = 0;

		expect(outer).not.toBeNull();
		if (!outer) return;

		outer.addEventListener("click", (event) => {
			if (event.target === outer) {
				outerClicks += 1;
			}
		});

		installInteractiveWindowStubs(dom.window);
		evaluateSharedInteractionsScript(dom.window);
		if (document.readyState === "loading") {
			document.dispatchEvent(new dom.window.Event("DOMContentLoaded", { bubbles: true }));
		}

		document.getElementById("plain-child")?.dispatchEvent(new dom.window.KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
		document.getElementById("inner-button")?.dispatchEvent(new dom.window.KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
		document.getElementById("inner-label")?.dispatchEvent(new dom.window.KeyboardEvent("keydown", { key: " ", bubbles: true }));
		document.getElementById("inner-input")?.dispatchEvent(new dom.window.KeyboardEvent("keydown", { key: " ", bubbles: true }));

		expect(outerClicks).toBe(1);
	});

	it("does not proxy nested ARIA interactive controls through parent role button keyboard activation", () => {
		const dom = new JSDOM(
			`<!doctype html>
			<html>
				<body>
					<div id="outer" role="button" tabindex="0" aria-label="审批卡片">
						<span id="plain-child">普通文本</span>
						<span id="inner-checkbox" role="checkbox" tabindex="0" aria-checked="false">复选</span>
						<span id="inner-switch" role="switch" tabindex="0" aria-checked="false">开关</span>
					</div>
				</body>
			</html>`,
			{
				pretendToBeVisual: true,
				url: "https://prototype.local/nested-aria-role-button-contract.html",
			},
		);
		const { document } = dom.window;
		const outer = document.getElementById("outer");
		let outerClicks = 0;

		expect(outer).not.toBeNull();
		if (!outer) return;

		outer.addEventListener("click", (event) => {
			if (event.target === outer) {
				outerClicks += 1;
			}
		});

		installInteractiveWindowStubs(dom.window);
		evaluateSharedInteractionsScript(dom.window);
		if (document.readyState === "loading") {
			document.dispatchEvent(new dom.window.Event("DOMContentLoaded", { bubbles: true }));
		}

		document.getElementById("plain-child")?.dispatchEvent(new dom.window.KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
		document.getElementById("inner-checkbox")?.dispatchEvent(new dom.window.KeyboardEvent("keydown", { key: " ", bubbles: true }));
		document.getElementById("inner-switch")?.dispatchEvent(new dom.window.KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
		outer.dispatchEvent(new dom.window.KeyboardEvent("keydown", { key: " ", bubbles: true }));

		expect(outerClicks).toBe(2);
	});

	it("caches shared CSS variable reads during interaction initialization", () => {
		const dom = new JSDOM(
			`<!doctype html>
			<html style="--chart-series-up: contract-up; --sparkline-width: 48; --sparkline-height: 20; --sparkline-stroke-width: 1.5">
				<body>
					<svg data-sparkline='{"data":[1,2,3],"series":"up"}'></svg>
					<svg data-sparkline='{"data":[1,3,2],"series":"up"}'></svg>
				</body>
			</html>`,
			{
				pretendToBeVisual: true,
				url: "https://prototype.local/css-var-cache-contract.html",
			},
		);
		let computedStyleReads = 0;
		const originalGetComputedStyle = dom.window.getComputedStyle.bind(dom.window);

		Object.defineProperty(dom.window, "getComputedStyle", {
			configurable: true,
			value: (element: Element, pseudoElt?: string | null): CSSStyleDeclaration => {
				if (element === dom.window.document.documentElement) {
					computedStyleReads += 1;
				}
				return originalGetComputedStyle(element, pseudoElt);
			},
		});

		installInteractiveWindowStubs(dom.window);
		evaluateSharedInteractionsScript(dom.window);
		if (dom.window.document.readyState === "loading") {
			dom.window.document.dispatchEvent(new dom.window.Event("DOMContentLoaded", { bubbles: true }));
		}

		expect(computedStyleReads).toBe(1);
	});

	it("invalidates shared CSS variable cache when theme or density attributes change", async () => {
		const dom = new JSDOM(
			`<!doctype html>
			<html style="--chart-series-up: first-series; --sparkline-width: 48; --sparkline-height: 20; --sparkline-stroke-width: 1.5">
				<body>
					<svg id="first-sparkline" data-sparkline='{"data":[1,2,3],"series":"up"}'></svg>
				</body>
			</html>`,
			{
				pretendToBeVisual: true,
				url: "https://prototype.local/css-var-invalidation-contract.html",
			},
		);
		let computedStyleReads = 0;
		const originalGetComputedStyle = dom.window.getComputedStyle.bind(dom.window);

		Object.defineProperty(dom.window, "getComputedStyle", {
			configurable: true,
			value: (element: Element, pseudoElt?: string | null): CSSStyleDeclaration => {
				if (element === dom.window.document.documentElement) {
					computedStyleReads += 1;
				}
				return originalGetComputedStyle(element, pseudoElt);
			},
		});

		installInteractiveWindowStubs(dom.window);
		evaluateSharedInteractionsScript(dom.window);
		if (dom.window.document.readyState === "loading") {
			dom.window.document.dispatchEvent(new dom.window.Event("DOMContentLoaded", { bubbles: true }));
		}

		expect(dom.window.document.querySelector("#first-sparkline path")?.getAttribute("stroke")).toBe("first-series");
		expect(computedStyleReads).toBe(1);

		dom.window.document.documentElement.style.setProperty("--chart-series-up", "second-series");
		dom.window.document.documentElement.setAttribute("data-theme", "light");
		await Promise.resolve();

		const secondSparkline = dom.window.document.createElementNS("http://www.w3.org/2000/svg", "svg");
		secondSparkline.id = "second-sparkline";
		secondSparkline.setAttribute("data-sparkline", '{"data":[1,3,2],"series":"up"}');
		dom.window.document.body.appendChild(secondSparkline);
		dom.window.document.dispatchEvent(new dom.window.Event("DOMContentLoaded", { bubbles: true }));

		expect(dom.window.document.querySelector("#second-sparkline path")?.getAttribute("stroke")).toBe("second-series");
		expect(computedStyleReads).toBe(2);
	});

	it("builds compare basket additions without unsafe innerHTML strings", () => {
		expect(readSharedInteractionsScript()).not.toMatch(/innerHTML\s*=\s*(?:\n\s*)?["'`]\s*</);
	});

	it("escapes compare basket text through DOM text nodes", () => {
		const dom = new JSDOM(
			`<!doctype html>
			<html>
				<body>
					<div data-screener-workflow>
						<table class="data-table" data-compare-source>
							<thead>
								<tr><th>代码</th><th>名称</th><th>涨跌</th></tr>
							</thead>
							<tbody>
								<tr class="row">
									<td class="cell-ticker"></td>
									<td class="cell-name"></td>
									<td class="cell-change-up">+1.2%</td>
								</tr>
							</tbody>
						</table>
						<div class="catalog-detail">
							<div data-compare-basket-body><button class="compare-cta" type="button">开始对比</button></div>
						</div>
						<div class="compare-list"></div>
						<span data-compare-count>0</span>
					</div>
				</body>
			</html>`,
			{
				pretendToBeVisual: true,
				url: "https://prototype.local/compare-escaping-contract.html",
			},
		);
		const { document } = dom.window;
		const maliciousTicker = "<script>alert(1)</script>";
		const maliciousName = `"><img src=x onerror=alert(1)>`;

		const tickerCell = document.querySelector(".cell-ticker");
		const nameCell = document.querySelector(".cell-name");
		expect(tickerCell).not.toBeNull();
		expect(nameCell).not.toBeNull();
		if (!tickerCell || !nameCell) return;

		tickerCell.textContent = maliciousTicker;
		nameCell.textContent = maliciousName;

		installInteractiveWindowStubs(dom.window);
		evaluateSharedInteractionsScript(dom.window);
		evaluateScreenerWorkflowScript(dom.window);
		if (document.readyState === "loading") {
			document.dispatchEvent(new dom.window.Event("DOMContentLoaded", { bubbles: true }));
		}

		const compareButton = document.querySelector("[data-compare-add]");
		expect(compareButton).not.toBeNull();
		compareButton?.dispatchEvent(new dom.window.MouseEvent("click", { bubbles: true }));

		expect(document.querySelector(".compare-item-name")?.textContent).toBe(maliciousName);
		expect(document.querySelector(".compare-row-ticker")?.textContent).toBe(maliciousTicker);
		expect(document.querySelector(".compare-item img, .compare-row img, .compare-item script, .compare-row script")).toBeNull();
		expect(document.querySelector("[data-compare-count]")?.textContent).toBe("1");
	});

	it("updates separated tab panels from shared tab interactions", () => {
		const dom = new JSDOM(
			`<!doctype html>
			<html>
				<body>
					<main class="prototype-shell">
						<div data-tabs="research-tabs" role="tablist" aria-label="研究视图切换">
							<button data-tab-target="factors" role="tab" id="tab-factors" aria-selected="true" aria-controls="panel-factors">因子</button>
							<button data-tab-target="reports" role="tab" id="tab-reports" aria-selected="false" aria-controls="panel-reports">研报</button>
						</div>
						<section class="research-panels">
							<div data-tab-panel="factors" id="panel-factors" role="tabpanel" aria-labelledby="tab-factors" aria-hidden="false">因子内容</div>
							<div data-tab-panel="reports" id="panel-reports" role="tabpanel" aria-labelledby="tab-reports" aria-hidden="true">研报内容</div>
						</section>
					</main>
				</body>
			</html>`,
			{
				pretendToBeVisual: true,
				url: "https://prototype.local/separated-tabs-contract.html",
			},
		);
		const { document } = dom.window;

		installInteractiveWindowStubs(dom.window);
		evaluateSharedInteractionsScript(dom.window);
		if (document.readyState === "loading") {
			document.dispatchEvent(new dom.window.Event("DOMContentLoaded", { bubbles: true }));
		}

		document.getElementById("tab-reports")?.click();

		expect(document.getElementById("tab-factors")?.getAttribute("aria-selected")).toBe("false");
		expect(document.getElementById("tab-factors")?.getAttribute("tabindex")).toBe("-1");
		expect(document.getElementById("panel-factors")?.getAttribute("aria-hidden")).toBe("true");
		expect(document.getElementById("panel-factors")?.style.display).toBe("none");
		expect(document.getElementById("tab-reports")?.getAttribute("aria-selected")).toBe("true");
		expect(document.getElementById("tab-reports")?.getAttribute("tabindex")).toBe("0");
		expect(document.getElementById("panel-reports")?.getAttribute("aria-hidden")).toBe("false");
		expect(document.getElementById("panel-reports")?.style.display).toBe("");

		document
			.getElementById("tab-factors")
			?.dispatchEvent(new dom.window.KeyboardEvent("keydown", { key: " ", bubbles: true }));

		expect(document.getElementById("tab-factors")?.getAttribute("aria-selected")).toBe("true");
		expect(document.getElementById("panel-factors")?.getAttribute("aria-hidden")).toBe("false");
		expect(document.getElementById("tab-reports")?.getAttribute("aria-selected")).toBe("false");
		expect(document.getElementById("panel-reports")?.getAttribute("aria-hidden")).toBe("true");
		expect(document.getElementById("panel-reports")?.style.display).toBe("none");
	});

	it("uses aria-controls to isolate separated tabsets that reuse target names", () => {
		const dom = new JSDOM(
			`<!doctype html>
			<html>
				<body>
					<main>
						<section id="first-tabset">
							<div data-tabs="first-tabs" role="tablist" aria-label="第一组">
								<button data-tab-target="overview" role="tab" id="first-overview-tab" aria-selected="true" aria-controls="first-overview-panel">概览</button>
								<button data-tab-target="all" role="tab" id="first-all-tab" aria-selected="false" aria-controls="first-all-panel">全部</button>
							</div>
						</section>
						<section id="second-tabset">
							<div data-tabs="second-tabs" role="tablist" aria-label="第二组">
								<button data-tab-target="overview" role="tab" id="second-overview-tab" aria-selected="true" aria-controls="second-overview-panel">概览</button>
								<button data-tab-target="all" role="tab" id="second-all-tab" aria-selected="false" aria-controls="second-all-panel">全部</button>
							</div>
						</section>
						<section id="shared-separated-panels">
							<div id="first-overview-panel" data-tab-panel="overview" role="tabpanel" aria-labelledby="first-overview-tab" aria-hidden="false">第一组概览</div>
							<div id="first-all-panel" data-tab-panel="all" role="tabpanel" aria-labelledby="first-all-tab" aria-hidden="true">第一组全部</div>
							<div id="second-overview-panel" data-tab-panel="overview" role="tabpanel" aria-labelledby="second-overview-tab" aria-hidden="false">第二组概览</div>
							<div id="second-all-panel" data-tab-panel="all" role="tabpanel" aria-labelledby="second-all-tab" aria-hidden="true">第二组全部</div>
						</section>
					</main>
				</body>
			</html>`,
			{
				pretendToBeVisual: true,
				url: "https://prototype.local/reused-target-tabsets-contract.html",
			},
		);
		const { document } = dom.window;

		installInteractiveWindowStubs(dom.window);
		evaluateSharedInteractionsScript(dom.window);
		if (document.readyState === "loading") {
			document.dispatchEvent(new dom.window.Event("DOMContentLoaded", { bubbles: true }));
		}

		document.getElementById("first-all-tab")?.click();

		expect(document.getElementById("first-overview-tab")?.getAttribute("aria-selected")).toBe("false");
		expect(document.getElementById("first-overview-panel")?.getAttribute("aria-hidden")).toBe("true");
		expect(document.getElementById("first-all-tab")?.getAttribute("aria-selected")).toBe("true");
		expect(document.getElementById("first-all-panel")?.getAttribute("aria-hidden")).toBe("false");
		expect(document.getElementById("second-overview-tab")?.getAttribute("aria-selected")).toBe("true");
		expect(document.getElementById("second-overview-panel")?.getAttribute("aria-hidden")).toBe("false");
		expect(document.getElementById("second-all-tab")?.getAttribute("aria-selected")).toBe("false");
		expect(document.getElementById("second-all-panel")?.getAttribute("aria-hidden")).toBe("true");
		expect(document.getElementById("second-all-panel")?.style.display).toBe("none");
	});

	it("fails closed for separated tabsets without aria-controls when target names are reused", () => {
		const dom = new JSDOM(
			`<!doctype html>
			<html>
				<body>
					<main>
						<section id="first-tabset">
							<div data-tabs="first-tabs" role="tablist" aria-label="第一组">
								<button data-tab-target="overview" role="tab" id="first-overview-tab" aria-selected="true">概览</button>
								<button data-tab-target="all" role="tab" id="first-all-tab" aria-selected="false">全部</button>
							</div>
						</section>
						<section id="second-tabset">
							<div data-tabs="second-tabs" role="tablist" aria-label="第二组">
								<button data-tab-target="overview" role="tab" id="second-overview-tab" aria-selected="true">概览</button>
								<button data-tab-target="all" role="tab" id="second-all-tab" aria-selected="false">全部</button>
							</div>
						</section>
						<section id="shared-separated-panels">
							<div id="first-overview-panel" data-tab-panel="overview" role="tabpanel" aria-labelledby="first-overview-tab" aria-hidden="false">第一组概览</div>
							<div id="first-all-panel" data-tab-panel="all" role="tabpanel" aria-labelledby="first-all-tab" aria-hidden="true">第一组全部</div>
							<div id="second-overview-panel" data-tab-panel="overview" role="tabpanel" aria-labelledby="second-overview-tab" aria-hidden="false">第二组概览</div>
							<div id="second-all-panel" data-tab-panel="all" role="tabpanel" aria-labelledby="second-all-tab" aria-hidden="true">第二组全部</div>
						</section>
					</main>
				</body>
			</html>`,
			{
				pretendToBeVisual: true,
				url: "https://prototype.local/reused-target-tabsets-without-controls-contract.html",
			},
		);
		const { document } = dom.window;

		installInteractiveWindowStubs(dom.window);
		evaluateSharedInteractionsScript(dom.window);
		if (document.readyState === "loading") {
			document.dispatchEvent(new dom.window.Event("DOMContentLoaded", { bubbles: true }));
		}

		document.getElementById("first-all-tab")?.click();

		expect(document.getElementById("first-overview-tab")?.getAttribute("aria-selected")).toBe("true");
		expect(document.getElementById("first-overview-panel")?.getAttribute("aria-hidden")).toBe("false");
		expect(document.getElementById("first-all-tab")?.getAttribute("aria-selected")).toBe("false");
		expect(document.getElementById("first-all-panel")?.getAttribute("aria-hidden")).toBe("true");
		expect(document.getElementById("second-overview-tab")?.getAttribute("aria-selected")).toBe("true");
		expect(document.getElementById("second-overview-panel")?.getAttribute("aria-hidden")).toBe("false");
		expect(document.getElementById("second-all-tab")?.getAttribute("aria-selected")).toBe("false");
		expect(document.getElementById("second-all-panel")?.getAttribute("aria-hidden")).toBe("true");
	});

	it("keeps active prototype tabs wired to labelled tab panels", () => {
		const violations: string[] = [];

		for (const page of activePages()) {
			const document = readPrototypeDocument(page);
			const tabs = Array.from(document.querySelectorAll<HTMLElement>('[role="tab"], [data-tab-target]'));
			const panels = Array.from(document.querySelectorAll<HTMLElement>('[role="tabpanel"], [data-tab-panel]'));
			const tabsById = new Map(tabs.flatMap((tab) => (tab.id ? [[tab.id, tab]] : [])));
			const controllingTabIdByPanelId = new Map<string, string>();
			const controllingTabLabelsByPanelId = new Map<string, string[]>();

			tabs.forEach((tab, index) => {
				const label = `${page.id}:tab ${index + 1}`;
				const controls = tab.getAttribute("aria-controls")?.trim() ?? "";

				if (tab.getAttribute("role") !== "tab") {
					violations.push(`${label}:missing-role-tab`);
				}
				if (!tab.id) {
					violations.push(`${label}:missing-id`);
				}
				if (!tab.hasAttribute("aria-selected")) {
					violations.push(`${label}:missing-aria-selected`);
				}
				if (!controls) {
					violations.push(`${label}:missing-aria-controls`);
					return;
				}

				const controllingTabLabels = controllingTabLabelsByPanelId.get(controls) ?? [];
				controllingTabLabels.push(tab.id || label);
				controllingTabLabelsByPanelId.set(controls, controllingTabLabels);
				if (controllingTabLabels.length > 1) {
					violations.push(`${page.id}:tabpanel:${controls}:duplicate-controlling-tabs:${controllingTabLabels.join(",")}`);
				}

				const panel = document.getElementById(controls);
				if (!panel) {
					violations.push(`${label}:missing-controlled-panel:${controls}`);
					return;
				}
				if (panel.getAttribute("role") !== "tabpanel") {
					violations.push(`${label}:controlled-target-not-tabpanel:${controls}`);
				}
				if (tab.id) {
					controllingTabIdByPanelId.set(controls, tab.id);
				}
			});

			panels.forEach((panel, index) => {
				const label = `${page.id}:tabpanel ${index + 1}`;
				const labelledBy = panel.getAttribute("aria-labelledby")?.trim() ?? "";
				const labelledByIds = labelledBy.split(/\s+/).filter(Boolean);
				const labelledByTab = labelledByIds.some((id) => tabsById.has(id));
				const controllingTabId = panel.id ? controllingTabIdByPanelId.get(panel.id) : undefined;

				if (panel.getAttribute("role") !== "tabpanel") {
					violations.push(`${label}:missing-role-tabpanel`);
				}
				if (!panel.id) {
					violations.push(`${label}:missing-id`);
				}
				if (!labelledBy) {
					violations.push(`${label}:missing-aria-labelledby`);
				} else if (!labelledByTab) {
					violations.push(`${label}:aria-labelledby-not-tab:${labelledBy}`);
				}
				if (panel.id && !controllingTabId) {
					violations.push(`${label}:orphan-tabpanel:${panel.id}`);
				}
				if (controllingTabId && !tabsById.has(controllingTabId)) {
					violations.push(`${label}:controlling-tab-not-found:${controllingTabId}`);
				}
				if (controllingTabId && !labelledByIds.includes(controllingTabId)) {
					violations.push(`${label}:aria-labelledby-missing-controlling-tab:${controllingTabId}`);
				}
			});
		}

		expect(violations).toEqual([]);
	}, 15_000);

	it("keeps page-local focus rings on the shared interaction focus token", () => {
		const violations = activePages().flatMap(collectFocusRuleViolations);

		expect(violations).toEqual([]);
	});

	it("keeps representative prototype status bars, sparklines, and overlays semantically named", () => {
		const violations: string[] = [];

		for (const pageId of semanticPolishPageIds) {
			const page = getActivePageById(pageId);
			const document = readPrototypeDocument(page);
			const statusBar = document.querySelector(
				"#default-view .status-bar[data-contract-slot='status'], #default-view .status-bar[role='status'], #default-view .shell-status-bar",
			);

			if (!statusBar) {
				violations.push(`${page.id}:status-bar:missing`);
			} else {
				if (statusBar.tagName.toLowerCase() !== "footer") {
					violations.push(`${page.id}:status-bar:tag:${statusBar.tagName.toLowerCase()}`);
				}
				if (statusBar.getAttribute("role") !== "status") {
					violations.push(`${page.id}:status-bar:role`);
				}
				if (!hasAccessibleName(statusBar)) {
					violations.push(`${page.id}:status-bar:name`);
				}
			}

			for (const sparkline of document.querySelectorAll("svg[data-sparkline]")) {
				if (sparkline.getAttribute("aria-hidden") === "true") continue;
				if (!hasAccessibleName(sparkline)) {
					violations.push(`${page.id}:sparkline:name`);
				}
			}

			for (const overlay of document.querySelectorAll(".overlay-surface")) {
				if (overlay.getAttribute("role") !== "dialog") {
					violations.push(`${page.id}:overlay:role`);
				}
				if (overlay.getAttribute("aria-modal") !== "true") {
					violations.push(`${page.id}:overlay:modal`);
				}
				if (!hasAccessibleName(overlay)) {
					violations.push(`${page.id}:overlay:name`);
				}
			}
		}

		expect(violations).toEqual([]);
	});

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
				const expectedIcon = railDomainSet.has(domain) ? railIcons[domain as keyof typeof railIcons] : undefined;
				const label = item.getAttribute("aria-label");
				const title = item.getAttribute("title");
				const href = item.getAttribute("href");

				if (item.tagName.toLowerCase() !== "a") {
					violations.push(`${page.id}:${domain}: rail item must be an anchor, found <${item.tagName.toLowerCase()}>`);
				}
				if (expectedHref && href !== expectedHref) {
					violations.push(`${page.id}:${domain}: expected href="${expectedHref}", found "${href ?? ""}"`);
				}
				if (expectedIcon && item.getAttribute("data-icon") !== expectedIcon) {
					violations.push(
						`${page.id}:${domain}: expected data-icon="${expectedIcon}", found "${item.getAttribute("data-icon") ?? ""}"`,
					);
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
	}, 15_000);

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
					const isHomeDataHealth = page.id === "home" && section.getAttribute("data-contract-slot") === "data-health";
					if (section.hasAttribute("open") && !isHomeDataHealth) {
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

		expect(tray.getAttribute("data-bottom-tray-state")).toBe("collapsed");
		toggle.click();
		expect(tray.getAttribute("data-bottom-tray-state")).toBe("peek");
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
		const browser = await launchPrototypeBrowser();

		try {
			for (const pageId of ["trading-overview"] as const) {
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

	it("keeps visible interactive targets at least 24px by 24px or explicitly exempted", async () => {
		let browser = await launchPrototypeBrowser();
		const violations: string[] = [];

		try {
			for (const viewport of targetSizeAuditViewports) {
				let page = await browser.newPage({ viewport });
				page.setDefaultNavigationTimeout(navigationTimeoutMs);

				for (const pageMeta of activePages()) {
					try {
						violations.push(...(await collectTargetSizeViolations(page, pageMeta, viewport.name)));
					} catch (error) {
						const message = error instanceof Error ? error.message : String(error);
						if (
							!message.includes("Target page") &&
							!message.includes("browser has been closed") &&
							!message.includes("Timeout")
						) {
							throw error;
						}

						await closePlaywrightPage(page);
						await closePlaywrightBrowser(browser);
						browser = await launchPrototypeBrowser();
						page = await browser.newPage({ viewport });
						page.setDefaultNavigationTimeout(navigationTimeoutMs);
						violations.push(...(await collectTargetSizeViolations(page, pageMeta, viewport.name)));
					}
				}

				await closePlaywrightPage(page);
			}
		} finally {
			await closePlaywrightBrowser(browser);
		}

		expect(violations).toEqual([]);
	}, 120_000);

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

	it("persists resizable panel values with a route-scoped preference key", () => {
		const { document, separator } = createResizablePanelDom("https://prototype.local/research/strategies");
		const storageKey = "ditto:prototype:layout:/research/strategies:--prototype-detail-width";

		separator.dispatchEvent(new document.defaultView!.KeyboardEvent("keydown", { key: "ArrowLeft", bubbles: true }));

		expect(document.defaultView!.localStorage.getItem(storageKey)).toBe("360");
	});

	it("restores persisted resizable panel values only when they are inside separator bounds", () => {
		const storageKey = "ditto:prototype:layout:/research/strategies:--prototype-detail-width";
		const { group, separator } = createResizablePanelDom("https://prototype.local/research/strategies", (window) => {
			window.localStorage.setItem(storageKey, "448");
		});

		expect(separator.getAttribute("aria-valuenow")).toBe("448");
		expect(group.style.getPropertyValue("--prototype-detail-width")).toBe("448px");

		const outOfRange = createResizablePanelDom("https://prototype.local/research/strategies", (window) => {
			window.localStorage.setItem(storageKey, "999");
		});

		expect(outOfRange.separator.getAttribute("aria-valuenow")).toBe("320");
		expect(outOfRange.group.style.getPropertyValue("--prototype-detail-width")).toBe("320px");
	});

	it("keeps resizable separator keyboard and double-click efficiency shortcuts explicit", () => {
		const { document, group, separator } = createResizablePanelDom("https://prototype.local/research/strategies");

		separator.dispatchEvent(new document.defaultView!.KeyboardEvent("keydown", { key: "ArrowLeft", bubbles: true }));
		expect(separator.getAttribute("aria-valuenow")).toBe("360");
		expect(separator.getAttribute("aria-valuetext")).toBe("调整测试面板宽度 360 像素");
		expect(group.style.getPropertyValue("--prototype-detail-width")).toBe("360px");

		separator.dispatchEvent(
			new document.defaultView!.KeyboardEvent("keydown", { key: "ArrowRight", shiftKey: true, bubbles: true }),
		);
		expect(separator.getAttribute("aria-valuenow")).toBe("352");
		expect(separator.getAttribute("aria-valuetext")).toBe("调整测试面板宽度 352 像素");
		expect(group.style.getPropertyValue("--prototype-detail-width")).toBe("352px");

		separator.dispatchEvent(new document.defaultView!.MouseEvent("dblclick", { bubbles: true }));
		expect(separator.getAttribute("aria-valuenow")).toBe("320");
		expect(separator.getAttribute("aria-valuetext")).toBe("调整测试面板宽度 320 像素");
		expect(group.style.getPropertyValue("--prototype-detail-width")).toBe("320px");
	});

	it("exposes selected-object regions on active pages with selected rows", () => {
		const violations: string[] = [];

		for (const page of activePages()) {
			const document = readPrototypeDocument(page);
			const root = getDefaultPrototypeRoot(document);
			const selectedRows = root.querySelectorAll(".row.selected, tr[aria-selected='true'], [data-row-selection-marker]");
			if (selectedRows.length === 0) continue;

			if (!root.querySelector("[data-selected-object-region]")) {
				violations.push(`${page.id}: selected rows require a [data-selected-object-region] hook`);
			}
		}

		expect(violations).toEqual([]);
	});

	it("exposes command scope on every active page command trigger", () => {
		const violations: string[] = [];

		for (const page of activePages()) {
			const document = readPrototypeDocument(page);
			document.querySelectorAll("[data-shell-utility='command'], .header-command-trigger").forEach((trigger, index) => {
				if (!trigger.getAttribute("data-command-scope")) {
					violations.push(`${page.id}: command trigger ${index + 1} is missing data-command-scope`);
				}
			});
		}

		expect(violations).toEqual([]);
	});

	it("exposes command context actions on selected-object representative pages", () => {
		const violations: string[] = [];

		for (const [pageId, expectedActions] of Object.entries(commandContextActionsByPageId)) {
			const document = readPrototypeDocument(getActivePageById(pageId));
			const root = getDefaultPrototypeRoot(document);
			const actionContract = root.querySelector("[data-command-context-object][data-command-context-actions]");
			if (!actionContract) {
				violations.push(`${pageId}: missing [data-command-context-object][data-command-context-actions]`);
				continue;
			}
			if (!actionContract.getAttribute("data-command-context-object")?.trim()) {
				violations.push(`${pageId}: missing selected command context object`);
			}

			const actualActions = parseCommandContextActions(actionContract);
			for (const expectedAction of expectedActions) {
				if (!actualActions.has(expectedAction)) {
					violations.push(`${pageId}: missing command context action "${expectedAction}"`);
				}
			}
		}

		expect(violations).toEqual([]);
	});

	it("renders keyboard-reachable command suggestions from selected-object context", () => {
		const violations: string[] = [];

		for (const [pageId, expectedActions] of Object.entries(commandContextActionsByPageId)) {
			const document = readInteractivePrototypeDocument(getActivePageById(pageId));
			const trigger = document.querySelector<HTMLElement>("[data-shell-utility='command'], .header-command-trigger");
			if (!trigger) {
				violations.push(`${pageId}: missing command trigger`);
				continue;
			}

			trigger.click();

			const palette = document.querySelector<HTMLElement>("[data-command-palette]");
			if (!palette) {
				violations.push(`${pageId}: missing command palette`);
				continue;
			}
			if (palette.hidden || palette.getAttribute("aria-hidden") === "true") {
				violations.push(`${pageId}: command palette did not open`);
			}

			for (const expectedAction of expectedActions) {
				const suggestion = palette.querySelector<HTMLElement>(
					`[data-command-suggestion][data-command-action="${expectedAction}"]`,
				);
				if (!suggestion) {
					violations.push(`${pageId}: missing command suggestion "${expectedAction}"`);
					continue;
				}
				if (suggestion.tabIndex < 0) {
					violations.push(`${pageId}: command suggestion "${expectedAction}" is not keyboard reachable`);
				}
			}
		}

		expect(violations).toEqual([]);
	}, jsdomInteractionTestTimeoutMs);

	it("exposes table expert efficiency hooks on selected-object representative pages", () => {
		const violations: string[] = [];

		for (const pageId of tableExpertContractPageIds) {
			const document = readPrototypeDocument(getActivePageById(pageId));
			const root = getDefaultPrototypeRoot(document);
			const tables = [...root.querySelectorAll("table.data-table, table.ledger-table")].filter(
				(table) => !table.closest(".gallery-group"),
			);
			if (tables.length === 0) {
				violations.push(`${pageId}: expected a data table for expert table contracts`);
				continue;
			}

			for (const table of tables) {
				const tableLabel = table.getAttribute("aria-label") ?? "unlabelled table";
				for (const attribute of tableExpertContractAttributes) {
					if (!table.hasAttribute(attribute)) {
						violations.push(`${pageId}: ${tableLabel} missing ${attribute}`);
					}
				}
			}
			if (!root.querySelector("[data-bulk-action-bar]")) {
				violations.push(`${pageId}: missing [data-bulk-action-bar]`);
			}
			root.querySelectorAll("[data-bulk-action-bar]").forEach((bulkBar, index) => {
				if (!bulkBar.matches(".bulk-action-bar, .batch-bar, [role='toolbar'], [data-contract-slot='bulk-action-bar']")) {
					violations.push(`${pageId}: bulk action contract ${index + 1} is not on a toolbar/bar element`);
				}
			});
			if (!root.querySelector("[data-active-filters-summary]")) {
				violations.push(`${pageId}: missing [data-active-filters-summary]`);
			}
			root.querySelectorAll("[data-batch-action-bar]").forEach((legacyBar, index) => {
				if (!legacyBar.hasAttribute("data-bulk-action-bar")) {
					violations.push(`${pageId}: legacy batch action bar ${index + 1} missing data-bulk-action-bar`);
				}
			});
		}
		const sharedLayoutCss = readFileSync(join(prototypesDir, "shared/layout-components.css"), "utf8");
		if (/\.batch-bar\[data-bulk-action-bar\]/.test(sharedLayoutCss)) {
			violations.push("shared-layout: batch bars keep page-local styling when marked as bulk contract");
		}

		expect(violations).toEqual([]);
	});

	it("updates resizable panel CSS variables through keyboard, drag, and reset interactions", () => {
		const document = readInteractivePrototypeDocument(getActivePageById("home"), (preparedDocument) => {
			const group = preparedDocument.createElement("div");
			group.setAttribute("data-resizable-panel-group", "test-workspace");
			group.style.setProperty("--prototype-detail-width", "320px");
			group.style.setProperty("--prototype-source-width", "240px");
			group.innerHTML = `
				<section id="test-main"></section>
				<div
					class="resize-separator"
					data-resize-separator
					data-resize-var="--prototype-detail-width"
					data-resize-default="320"
					data-resize-min="220"
					data-resize-max="520"
					role="separator"
					tabindex="0"
					aria-label="调整测试面板宽度"
					aria-orientation="vertical"
					aria-controls="test-main test-detail"
					aria-valuemin="220"
					aria-valuemax="520"
					aria-valuenow="320"
					aria-valuetext="调整测试面板宽度 320 像素"
				></div>
				<aside id="test-detail"></aside>
				<div
					class="resize-separator"
					data-resize-separator
					data-resize-var="--prototype-source-width"
					data-resize-edge="start"
					data-resize-default="240"
					data-resize-min="180"
					data-resize-max="360"
					role="separator"
					tabindex="0"
					aria-label="调整测试资源栏宽度"
					aria-orientation="vertical"
					aria-controls="test-source test-main"
					aria-valuemin="180"
					aria-valuemax="360"
					aria-valuenow="240"
					aria-valuetext="调整测试资源栏宽度 240 像素"
				></div>
				<aside id="test-source"></aside>
			`;
			preparedDocument.body.append(group);
		});
		const group = document.querySelector<HTMLElement>('[data-resizable-panel-group="test-workspace"]');
		const separator = document.querySelector<HTMLElement>('[data-resize-var="--prototype-detail-width"]');
		const startEdgeSeparator = document.querySelector<HTMLElement>('[data-resize-var="--prototype-source-width"]');

		expect(group).not.toBeNull();
		expect(separator).not.toBeNull();
		expect(startEdgeSeparator).not.toBeNull();
		if (!group || !separator || !startEdgeSeparator) return;

		separator.dispatchEvent(new document.defaultView!.KeyboardEvent("keydown", { key: "ArrowLeft", bubbles: true }));
		expect(separator.getAttribute("aria-valuenow")).toBe("360");
		expect(separator.getAttribute("aria-valuetext")).toBe("调整测试面板宽度 360 像素");
		expect(group.style.getPropertyValue("--prototype-detail-width")).toBe("360px");

		separator.dispatchEvent(
			new document.defaultView!.KeyboardEvent("keydown", { key: "ArrowRight", shiftKey: true, bubbles: true }),
		);
		expect(separator.getAttribute("aria-valuenow")).toBe("352");
		expect(separator.getAttribute("aria-valuetext")).toBe("调整测试面板宽度 352 像素");
		expect(group.style.getPropertyValue("--prototype-detail-width")).toBe("352px");

		separator.dispatchEvent(new document.defaultView!.MouseEvent("pointerdown", { clientX: 400, bubbles: true }));
		document.defaultView!.dispatchEvent(new document.defaultView!.MouseEvent("pointermove", { clientX: 360, bubbles: true }));
		document.defaultView!.dispatchEvent(new document.defaultView!.MouseEvent("pointerup", { bubbles: true }));
		expect(separator.getAttribute("aria-valuenow")).toBe("392");
		expect(separator.getAttribute("aria-valuetext")).toBe("调整测试面板宽度 392 像素");
		expect(group.style.getPropertyValue("--prototype-detail-width")).toBe("392px");

		separator.dispatchEvent(new document.defaultView!.MouseEvent("dblclick", { bubbles: true }));
		expect(separator.getAttribute("aria-valuenow")).toBe("320");
		expect(separator.getAttribute("aria-valuetext")).toBe("调整测试面板宽度 320 像素");
		expect(group.style.getPropertyValue("--prototype-detail-width")).toBe("320px");

		startEdgeSeparator.dispatchEvent(
			new document.defaultView!.KeyboardEvent("keydown", { key: "ArrowRight", bubbles: true }),
		);
		expect(startEdgeSeparator.getAttribute("aria-valuenow")).toBe("280");
		expect(startEdgeSeparator.getAttribute("aria-valuetext")).toBe("调整测试资源栏宽度 280 像素");
		expect(group.style.getPropertyValue("--prototype-source-width")).toBe("280px");

		startEdgeSeparator.dispatchEvent(
			new document.defaultView!.KeyboardEvent("keydown", { key: "ArrowLeft", shiftKey: true, bubbles: true }),
		);
		expect(startEdgeSeparator.getAttribute("aria-valuenow")).toBe("272");
		expect(startEdgeSeparator.getAttribute("aria-valuetext")).toBe("调整测试资源栏宽度 272 像素");
		expect(group.style.getPropertyValue("--prototype-source-width")).toBe("272px");
	});

		/* ── Phase 1 a11y contract tests ─────────────── */

		describe("Phase 1 accessibility features", () => {
			it("navigates between tabs with ArrowRight, ArrowLeft, Home, and End keys", () => {
				const dom = new JSDOM(
					`<!doctype html>
					<html>
						<body>
							<main>
								<div data-tabs="a11y-tabs" role="tablist" aria-label="无障碍标签页">
									<button data-tab-target="tab-a" role="tab" id="tab-btn-a" aria-selected="true" aria-controls="panel-a">标签 A</button>
									<button data-tab-target="tab-b" role="tab" id="tab-btn-b" aria-selected="false" aria-controls="panel-b">标签 B</button>
									<button data-tab-target="tab-c" role="tab" id="tab-btn-c" aria-selected="false" aria-controls="panel-c">标签 C</button>
								</div>
								<div id="panel-a" data-tab-panel="tab-a" role="tabpanel" aria-labelledby="tab-btn-a" aria-hidden="false">A 内容</div>
								<div id="panel-b" data-tab-panel="tab-b" role="tabpanel" aria-labelledby="tab-btn-b" aria-hidden="true">B 内容</div>
								<div id="panel-c" data-tab-panel="tab-c" role="tabpanel" aria-labelledby="tab-btn-c" aria-hidden="true">C 内容</div>
							</main>
						</body>
					</html>`,
					{ pretendToBeVisual: true, url: "https://prototype.local/a11y-tabs-arrows.html" },
				);
				const { document } = dom.window;

				installInteractiveWindowStubs(dom.window);
				evaluateSharedInteractionsScript(dom.window);
				if (document.readyState === "loading") {
					document.dispatchEvent(new dom.window.Event("DOMContentLoaded", { bubbles: true }));
				}

				const tabA = document.getElementById("tab-btn-a");
				const tabB = document.getElementById("tab-btn-b");
				const tabC = document.getElementById("tab-btn-c");

				/* ArrowRight: A -> B */
				tabA?.dispatchEvent(new dom.window.KeyboardEvent("keydown", { key: "ArrowRight", bubbles: true }));
				expect(tabB?.getAttribute("aria-selected")).toBe("true");
				expect(tabB?.getAttribute("tabindex")).toBe("0");
				expect(tabA?.getAttribute("aria-selected")).toBe("false");
				expect(document.getElementById("panel-b")?.getAttribute("aria-hidden")).toBe("false");
				expect(document.getElementById("panel-a")?.getAttribute("aria-hidden")).toBe("true");

				/* ArrowRight: B -> C */
				tabB?.dispatchEvent(new dom.window.KeyboardEvent("keydown", { key: "ArrowRight", bubbles: true }));
				expect(tabC?.getAttribute("aria-selected")).toBe("true");
				expect(document.getElementById("panel-c")?.getAttribute("aria-hidden")).toBe("false");

				/* ArrowRight wraps: C -> A */
				tabC?.dispatchEvent(new dom.window.KeyboardEvent("keydown", { key: "ArrowRight", bubbles: true }));
				expect(tabA?.getAttribute("aria-selected")).toBe("true");
				expect(document.getElementById("panel-a")?.getAttribute("aria-hidden")).toBe("false");

				/* ArrowLeft wraps: A -> C */
				tabA?.dispatchEvent(new dom.window.KeyboardEvent("keydown", { key: "ArrowLeft", bubbles: true }));
				expect(tabC?.getAttribute("aria-selected")).toBe("true");
				expect(document.getElementById("panel-c")?.getAttribute("aria-hidden")).toBe("false");

				/* Home: goes to first tab */
				tabC?.dispatchEvent(new dom.window.KeyboardEvent("keydown", { key: "Home", bubbles: true }));
				expect(tabA?.getAttribute("aria-selected")).toBe("true");
				expect(document.getElementById("panel-a")?.getAttribute("aria-hidden")).toBe("false");

				/* End: goes to last tab */
				tabA?.dispatchEvent(new dom.window.KeyboardEvent("keydown", { key: "End", bubbles: true }));
				expect(tabC?.getAttribute("aria-selected")).toBe("true");
				expect(document.getElementById("panel-c")?.getAttribute("aria-hidden")).toBe("false");
			});

			it("wraps Tab focus within the command palette dialog", () => {
				const dom = new JSDOM(
					`<!doctype html>
					<html>
						<body>
							<button id="cmd-trigger" type="button" data-shell-utility="command" data-command-scope="home">命令</button>
							<div data-command-context-object="测试对象" data-command-context-actions="review-signal,open-risk"></div>
						</body>
					</html>`,
					{ pretendToBeVisual: true, url: "https://prototype.local/a11y-cmd-focus-trap.html" },
				);
				const { document } = dom.window;

				installInteractiveWindowStubs(dom.window);
				evaluateSharedInteractionsScript(dom.window);
				if (document.readyState === "loading") {
					document.dispatchEvent(new dom.window.Event("DOMContentLoaded", { bubbles: true }));
				}

				const trigger = document.getElementById("cmd-trigger");
				trigger?.click();

				const palette = document.querySelector("[data-command-palette]");
				expect(palette).not.toBeNull();
				expect(palette?.hidden).toBe(false);
				if (!palette) return;

				const suggestions = palette.querySelectorAll("[data-command-suggestion]");
				expect(suggestions.length).toBeGreaterThanOrEqual(2);

				const first = suggestions[0];
				const last = suggestions[suggestions.length - 1];

				/* Focus on last item, Tab wraps to first */
				(last as HTMLElement).focus();
				palette.dispatchEvent(new dom.window.KeyboardEvent("keydown", { key: "Tab", bubbles: true }));
				expect(document.activeElement).toBe(first);

				/* Focus on first item, Shift+Tab wraps to last */
				(first as HTMLElement).focus();
				palette.dispatchEvent(new dom.window.KeyboardEvent("keydown", { key: "Tab", shiftKey: true, bubbles: true }));
				expect(document.activeElement).toBe(last);
			});

			it("restores focus to the trigger element when command palette closes", () => {
				const dom = new JSDOM(
					`<!doctype html>
					<html>
						<body>
							<button id="cmd-trigger" type="button" data-shell-utility="command" data-command-scope="home">命令</button>
							<div data-command-context-object="测试对象" data-command-context-actions="review-signal"></div>
						</body>
					</html>`,
					{ pretendToBeVisual: true, url: "https://prototype.local/a11y-cmd-focus-restore.html" },
				);
				const { document } = dom.window;

				installInteractiveWindowStubs(dom.window);
				evaluateSharedInteractionsScript(dom.window);
				if (document.readyState === "loading") {
					document.dispatchEvent(new dom.window.Event("DOMContentLoaded", { bubbles: true }));
				}

				const trigger = document.getElementById("cmd-trigger") as HTMLElement | null;
				expect(trigger).not.toBeNull();
				if (!trigger) return;

				trigger.focus();
				trigger.click();

				const palette = document.querySelector("[data-command-palette]");
				expect(palette?.hidden).toBe(false);

				/* Close with Escape */
				document.dispatchEvent(new dom.window.KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
				expect(palette?.hidden).toBe(true);
				expect(document.activeElement).toBe(trigger);
			});

			it("opens the keyboard shortcuts overlay with global and route-context actions", () => {
				const dom = new JSDOM(
					`<!doctype html>
					<html>
						<body>
							<button id="help-trigger" type="button">帮助</button>
							<button id="cmd-trigger" type="button" data-shell-utility="command" data-command-scope="home">命令</button>
							<button id="theme-toggle" type="button" data-shell-utility="theme">主题</button>
							<button id="density-toggle" type="button" data-shell-utility="density">密度</button>
							<div
								data-command-context-route="/alpha"
								data-command-context-object="测试对象"
								data-command-context-actions="review-signal,open-risk"
							></div>
							<div data-resizable-panel-group>
								<div data-resize-separator aria-label="调整测试面板宽度"></div>
							</div>
						</body>
					</html>`,
					{ pretendToBeVisual: true, url: "https://prototype.local/shortcut-overlay.html" },
				);
				const { document } = dom.window;

				installInteractiveWindowStubs(dom.window);
				evaluateSharedInteractionsScript(dom.window);
				if (document.readyState === "loading") {
					document.dispatchEvent(new dom.window.Event("DOMContentLoaded", { bubbles: true }));
				}

				const trigger = document.getElementById("help-trigger") as HTMLElement | null;
				expect(trigger).not.toBeNull();
				if (!trigger) return;

				trigger.focus();
				document.dispatchEvent(new dom.window.KeyboardEvent("keydown", { key: "?", bubbles: true }));

				const overlay = document.querySelector<HTMLElement>("[data-shortcuts-overlay]");
				expect(overlay).not.toBeNull();
				expect(overlay?.getAttribute("role")).toBe("dialog");
				expect(overlay?.getAttribute("aria-modal")).toBe("true");
				expect(overlay?.hidden).toBe(false);
				expect(document.activeElement).toBe(overlay?.querySelector("[data-shortcuts-close]"));

				expect(overlay?.textContent).toContain("Ctrl K");
				expect(overlay?.textContent).toContain("/");
				expect(overlay?.textContent).toContain("Esc");
				expect(overlay?.textContent).toContain("?");
				expect(overlay?.textContent).toContain("主题");
				expect(overlay?.textContent).toContain("密度");
				expect(overlay?.textContent).toContain("双击");
				expect(overlay?.textContent).toContain("复核信号");
				expect(overlay?.textContent).toContain("打开风控");

				document.dispatchEvent(new dom.window.KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
				expect(overlay?.hidden).toBe(true);
				expect(document.activeElement).toBe(trigger);
			});

			it("wraps Tab focus within the keyboard shortcuts overlay", () => {
				const dom = new JSDOM(
					`<!doctype html>
					<html>
						<body>
							<button id="help-trigger" type="button">帮助</button>
							<div data-command-context-object="测试对象" data-command-context-actions="review-signal"></div>
						</body>
					</html>`,
					{ pretendToBeVisual: true, url: "https://prototype.local/shortcut-overlay-focus.html" },
				);
				const { document } = dom.window;

				installInteractiveWindowStubs(dom.window);
				evaluateSharedInteractionsScript(dom.window);
				if (document.readyState === "loading") {
					document.dispatchEvent(new dom.window.Event("DOMContentLoaded", { bubbles: true }));
				}

				document.getElementById("help-trigger")?.focus();
				document.dispatchEvent(new dom.window.KeyboardEvent("keydown", { key: "?", bubbles: true }));

				const overlay = document.querySelector<HTMLElement>("[data-shortcuts-overlay]");
				expect(overlay).not.toBeNull();
				if (!overlay) return;

				const focusables = [
					...overlay.querySelectorAll<HTMLElement>("[data-shortcuts-close], [data-shortcuts-item]"),
				];
				expect(focusables.length).toBeGreaterThanOrEqual(2);

				const first = focusables[0];
				const last = focusables[focusables.length - 1];

				last.focus();
				overlay.dispatchEvent(new dom.window.KeyboardEvent("keydown", { key: "Tab", bubbles: true }));
				expect(document.activeElement).toBe(first);

				first.focus();
				overlay.dispatchEvent(new dom.window.KeyboardEvent("keydown", { key: "Tab", shiftKey: true, bubbles: true }));
				expect(document.activeElement).toBe(last);
			});

			it("activates command actions into visible operational feedback and scoped recents", () => {
				const dom = new JSDOM(
					`<!doctype html>
					<html>
						<body>
							<button id="cmd-trigger" type="button" data-shell-utility="command" data-command-scope="home">命令</button>
							<div
								data-command-context-route="/alpha"
								data-command-context-object="测试对象"
								data-command-context-actions="review-signal,open-risk"
							></div>
						</body>
					</html>`,
					{ pretendToBeVisual: true, url: "https://prototype.local/action-bus.html" },
				);
				const { document } = dom.window;

				installInteractiveWindowStubs(dom.window);
				evaluateSharedInteractionsScript(dom.window);
				if (document.readyState === "loading") {
					document.dispatchEvent(new dom.window.Event("DOMContentLoaded", { bubbles: true }));
				}

				const trigger = document.getElementById("cmd-trigger");
				trigger?.click();
				const palette = document.querySelector<HTMLElement>("[data-command-palette]");
				const action = palette?.querySelector<HTMLElement>('[data-command-action="review-signal"]');

				expect(palette).not.toBeNull();
				expect(action).not.toBeNull();
				action?.click();

				const feedback = document.querySelector<HTMLElement>("[data-command-action-feedback]");
				expect(feedback).not.toBeNull();
				expect(feedback?.hidden).toBe(false);
				expect(feedback?.getAttribute("data-command-feedback-action")).toBe("review-signal");
				expect(feedback?.textContent).toContain("复核信号");
				expect(feedback?.textContent).toContain("测试对象");
				expect(feedback?.textContent).toContain("检查证据链");
				expect(feedback?.textContent).toContain("已排入复核工作流");
				expect(palette?.hidden).toBe(true);

				const storageKey = `ditto-recent-commands::${encodeURIComponent("/alpha")}::${encodeURIComponent("测试对象")}`;
				expect(document.defaultView!.localStorage.getItem("ditto-recent-commands")).toBeNull();
				expect(document.defaultView!.localStorage.getItem(storageKey)).toContain("review-signal");

				trigger?.click();
				const recentSection = document.querySelector<HTMLElement>("[data-command-palette] [data-command-recent-section]");
				expect(recentSection?.textContent).toContain("复核信号");

				const context = document.querySelector<HTMLElement>("[data-command-context-object]");
				context?.setAttribute("data-command-context-route", "/beta");
				trigger?.click();
				const betaRecentSection = document.querySelector<HTMLElement>("[data-command-palette] [data-command-recent-section]");
				expect(betaRecentSection?.textContent ?? "").not.toContain("复核信号");
			});

			it("keeps command recent storage keys stable when route or object contains delimiters", () => {
				const dom = new JSDOM(
					`<!doctype html>
					<html>
						<body>
							<button id="cmd-trigger" type="button" data-shell-utility="command" data-command-scope="home">命令</button>
							<div
								data-command-context-route="/alpha::desk"
								data-command-context-object="对象::A"
								data-command-context-actions="review-signal"
							></div>
						</body>
					</html>`,
					{ pretendToBeVisual: true, url: "https://prototype.local/recent-key-collision.html" },
				);
				const { document } = dom.window;

				installInteractiveWindowStubs(dom.window);
				evaluateSharedInteractionsScript(dom.window);
				if (document.readyState === "loading") {
					document.dispatchEvent(new dom.window.Event("DOMContentLoaded", { bubbles: true }));
				}

				document.getElementById("cmd-trigger")?.click();
				document.querySelector<HTMLElement>('[data-command-action="review-signal"]')?.click();

				const encodedKey = `ditto-recent-commands::${encodeURIComponent("/alpha::desk")}::${encodeURIComponent("对象::A")}`;
				const ambiguousKey = "ditto-recent-commands::/alpha::desk::对象::A";
				expect(document.defaultView!.localStorage.getItem(encodedKey)).toContain("review-signal");
				expect(document.defaultView!.localStorage.getItem(ambiguousKey)).toBeNull();
			});

			it("renders recent command actions in stored recency order", () => {
				const dom = new JSDOM(
					`<!doctype html>
					<html>
						<body>
							<button id="cmd-trigger" type="button" data-shell-utility="command" data-command-scope="home">命令</button>
							<div
								data-command-context-route="alpha"
								data-command-context-object="object"
								data-command-context-actions="review-signal,open-risk,open-orders"
							></div>
						</body>
					</html>`,
					{ pretendToBeVisual: true, url: "https://prototype.local/recent-order.html" },
				);
				const { document } = dom.window;
				document.defaultView!.localStorage.setItem(
					"ditto-recent-commands::alpha::object",
					JSON.stringify(["open-orders", "review-signal"]),
				);

				installInteractiveWindowStubs(dom.window);
				evaluateSharedInteractionsScript(dom.window);
				if (document.readyState === "loading") {
					document.dispatchEvent(new dom.window.Event("DOMContentLoaded", { bubbles: true }));
				}

				document.getElementById("cmd-trigger")?.click();
				const recentActions = [
					...document.querySelectorAll<HTMLElement>("[data-command-recent-section] [data-command-action]"),
				].map((action) => action.getAttribute("data-command-action"));

				expect(recentActions).toEqual(["open-orders", "review-signal"]);
			});

			it("routes high-risk command actions through an accessible confirmation dialog", () => {
				const dom = new JSDOM(
					`<!doctype html>
					<html>
						<body>
							<button id="cmd-trigger" type="button" data-shell-utility="command" data-command-scope="strategy">命令</button>
							<div
								data-command-context-route="/research/strategies"
								data-command-context-object="策略 V3.2"
								data-command-context-actions="pause-strategy,clone-strategy"
							></div>
						</body>
					</html>`,
					{ pretendToBeVisual: true, url: "https://prototype.local/high-risk-action.html" },
				);
				const { document } = dom.window;

				installInteractiveWindowStubs(dom.window);
				evaluateSharedInteractionsScript(dom.window);
				if (document.readyState === "loading") {
					document.dispatchEvent(new dom.window.Event("DOMContentLoaded", { bubbles: true }));
				}

				const trigger = document.getElementById("cmd-trigger");
				trigger?.click();
				document.querySelector<HTMLElement>('[data-command-action="pause-strategy"]')?.click();

				const dialog = document.querySelector<HTMLElement>("[data-command-confirmation]");
				expect(dialog).not.toBeNull();
				expect(dialog?.getAttribute("role")).toBe("dialog");
				expect(dialog?.getAttribute("aria-modal")).toBe("true");
				const describedBy = dialog?.getAttribute("aria-describedby");
				expect(describedBy).toBe("command-confirmation-body");
				expect(describedBy ? document.getElementById(describedBy) : null).not.toBeNull();
				expect(dialog?.hidden).toBe(false);
				expect(dialog?.textContent).toContain("暂停策略");
				expect(dialog?.textContent).toContain("策略 V3.2");
				expect(document.querySelector("[data-command-action-feedback]")).toBeNull();

				const cancel = dialog?.querySelector<HTMLElement>("[data-command-confirm-cancel]");
				cancel?.click();
				expect(dialog?.hidden).toBe(true);
				expect(document.querySelector("[data-command-action-feedback]")).toBeNull();

				trigger?.click();
				document.querySelector<HTMLElement>('[data-command-action="pause-strategy"]')?.click();
				const reopenedDialog = document.querySelector<HTMLElement>("[data-command-confirmation]");
				expect(reopenedDialog?.hidden).toBe(false);
				document.dispatchEvent(new dom.window.KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
				expect(reopenedDialog?.hidden).toBe(true);

				trigger?.click();
				document.querySelector<HTMLElement>('[data-command-action="pause-strategy"]')?.click();
				document.querySelector<HTMLElement>("[data-command-confirm-submit]")?.click();

				const feedback = document.querySelector<HTMLElement>("[data-command-action-feedback]");
				expect(feedback).not.toBeNull();
				expect(feedback?.getAttribute("data-command-feedback-risk")).toBe("high");
				expect(feedback?.textContent).toContain("暂停策略");
				expect(feedback?.textContent).toContain("策略 V3.2");
				expect(feedback?.textContent).toContain("已提交暂停请求");
				expect(
					document.defaultView!.localStorage.getItem(
						`ditto-recent-commands::${encodeURIComponent("/research/strategies")}::${encodeURIComponent("策略 V3.2")}`,
					),
				).toContain("pause-strategy");
			});

			it("sets aria-describedby on tooltip trigger on show and clears on hide", async () => {
				const dom = new JSDOM(
					`<!doctype html>
					<html>
						<body>
							<button id="tip-trigger" type="button" data-tooltip="提示文字" data-tooltip-delay="0">悬停我</button>
						</body>
					</html>`,
					{ pretendToBeVisual: true, url: "https://prototype.local/a11y-tooltip-describedby.html" },
				);
				const { document } = dom.window;

				installInteractiveWindowStubs(dom.window);
				evaluateSharedInteractionsScript(dom.window);
				if (document.readyState === "loading") {
					document.dispatchEvent(new dom.window.Event("DOMContentLoaded", { bubbles: true }));
				}

				const trigger = document.getElementById("tip-trigger");
				const tooltipEl = document.querySelector(".ditto-tooltip[role='tooltip']");
				expect(trigger).not.toBeNull();
				expect(tooltipEl).not.toBeNull();
				if (!trigger || !tooltipEl) return;

				/* Before show: no aria-describedby on trigger */
				expect(trigger.getAttribute("aria-describedby")).toBeNull();

				/* Hover to trigger show (delay=0, but setTimeout is still async in JSDOM) */
				trigger.dispatchEvent(new dom.window.MouseEvent("mouseover", { bubbles: true }));

				/* Wait for the setTimeout(0) to flush */
				await new Promise((resolve) => setTimeout(resolve, 50));

				/* After show: trigger should have aria-describedby pointing to the tooltip */
				const describedBy = trigger.getAttribute("aria-describedby");
				expect(describedBy).not.toBeNull();
				expect(describedBy?.startsWith("ditto-tooltip-")).toBe(true);
				expect(tooltipEl.id).toBe(describedBy);
				expect(tooltipEl.getAttribute("aria-hidden")).toBe("false");

				/* Leave to trigger hide */
				trigger.dispatchEvent(new dom.window.MouseEvent("mouseout", { bubbles: true, relatedTarget: null }));

				/* Wait for the hide setTimeout(150) to flush */
				await new Promise((resolve) => setTimeout(resolve, 200));

				/* After hide: aria-describedby cleared */
				expect(trigger.getAttribute("aria-describedby")).toBeNull();
			});

			it("activates filter chips with Enter and Space keys", () => {
				const dom = new JSDOM(
					`<!doctype html>
					<html>
						<body>
							<div class="filter-group">
								<button class="filter-chip active" type="button">选项 A</button>
								<button class="filter-chip" type="button">选项 B</button>
								<button class="filter-chip" type="button">选项 C</button>
							</div>
						</body>
					</html>`,
					{ pretendToBeVisual: true, url: "https://prototype.local/a11y-filter-chips-keyboard.html" },
				);
				const { document } = dom.window;

				installInteractiveWindowStubs(dom.window);
				evaluateSharedInteractionsScript(dom.window);
				if (document.readyState === "loading") {
					document.dispatchEvent(new dom.window.Event("DOMContentLoaded", { bubbles: true }));
				}

				const chips = Array.from(document.querySelectorAll(".filter-chip")) as HTMLElement[];
				expect(chips.length).toBe(3);

				/* Initial state: first chip is active */
				expect(chips[0].getAttribute("aria-pressed")).toBe("true");
				expect(chips[1].getAttribute("aria-pressed")).toBe("false");

				/* Activate second chip with Enter */
				chips[1].dispatchEvent(new dom.window.KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
				expect(chips[1].getAttribute("aria-pressed")).toBe("true");
				expect(chips[1].classList.contains("active")).toBe(true);
				expect(chips[0].getAttribute("aria-pressed")).toBe("false");
				expect(chips[0].classList.contains("active")).toBe(false);

				/* Activate third chip with Space */
				chips[2].dispatchEvent(new dom.window.KeyboardEvent("keydown", { key: " ", bubbles: true }));
				expect(chips[2].getAttribute("aria-pressed")).toBe("true");
				expect(chips[2].classList.contains("active")).toBe(true);
				expect(chips[1].getAttribute("aria-pressed")).toBe("false");
				expect(chips[1].classList.contains("active")).toBe(false);
			});

			it("generates a stable aria-labelledby ID for tab buttons without explicit IDs", () => {
				const dom = new JSDOM(
					`<!doctype html>
					<html>
						<body>
							<main>
								<div data-tabs="auto-id-tabs" role="tablist" aria-label="自动 ID 标签页">
									<button data-tab-target="auto-a" role="tab" aria-selected="true" aria-controls="panel-auto-a">标签 A</button>
									<button data-tab-target="auto-b" role="tab" aria-selected="false" aria-controls="panel-auto-b">标签 B</button>
								</div>
								<div id="panel-auto-a" data-tab-panel="auto-a" role="tabpanel" aria-hidden="false">A 内容</div>
								<div id="panel-auto-b" data-tab-panel="auto-b" role="tabpanel" aria-hidden="true">B 内容</div>
							</main>
						</body>
					</html>`,
					{ pretendToBeVisual: true, url: "https://prototype.local/a11y-tabs-auto-id.html" },
				);
				const { document } = dom.window;

				installInteractiveWindowStubs(dom.window);
				evaluateSharedInteractionsScript(dom.window);
				if (document.readyState === "loading") {
					document.dispatchEvent(new dom.window.Event("DOMContentLoaded", { bubbles: true }));
				}

				const buttons = Array.from(document.querySelectorAll("[data-tab-target]"));
				const panels = Array.from(document.querySelectorAll("[data-tab-panel]"));

				/* Each button should now have an auto-generated ID */
				for (const button of buttons) {
					expect(button.id, "tab button should have an auto-generated ID").toBeTruthy();
					expect(button.id.startsWith("ditto-tab-"), "auto-generated ID should have ditto-tab- prefix").toBe(true);
				}

				/* Each panel should have aria-labelledby pointing to its controlling button */
				const panelA = panels.find((p) => p.getAttribute("data-tab-panel") === "auto-a");
				const panelB = panels.find((p) => p.getAttribute("data-tab-panel") === "auto-b");
				const btnA = buttons.find((b) => b.getAttribute("data-tab-target") === "auto-a");
				const btnB = buttons.find((b) => b.getAttribute("data-tab-target") === "auto-b");

				expect(panelA?.getAttribute("aria-labelledby")).toBe(btnA?.id);
				expect(panelB?.getAttribute("aria-labelledby")).toBe(btnB?.id);

				/* The generated IDs should be unique */
				const ids = buttons.map((b) => b.id);
				expect(new Set(ids).size).toBe(ids.length);
			});
		});
	});
