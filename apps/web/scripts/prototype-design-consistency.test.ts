import { existsSync, readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { JSDOM } from "jsdom";
import { describe, expect, it } from "vitest";
import {
	buildDefaultPrototypeGateArgs,
	buildPassthroughGateArgs,
	defaultViewportArgs,
} from "./run-prototype-gates";
import { findHardcodedColors } from "./prototype-color-audit";

const root = process.cwd();
const prototypesDir = join(root, "docs/designs/specs/prototypes");
const contractsDir = join(root, "docs/contracts/pages");
const prototypeFontsCss = join(prototypesDir, "shared/fonts.css");
const prototypeLayoutCss = join(prototypesDir, "shared/layout-shell.css");
const prototypeLayoutModulePaths = [
	"shared/layout-shell.css",
	"shared/layout-gallery.css",
	"shared/layout-components.css",
	"shared/layout-overlay.css",
	"shared/layout-state.css",
] as const;
function readAllLayoutCss(): string {
	return prototypeLayoutModulePaths.map((p) => readFileSync(join(prototypesDir, p), "utf8")).join("\n");
}

function readLayoutCssSources(): CssSource[] {
	return prototypeLayoutModulePaths.map((path) => ({
		label: path,
		css: readFileSync(join(prototypesDir, path), "utf8"),
	}));
}
const prototypeThemeSwitcherCss = join(prototypesDir, "shared/theme-switcher.css");
const prototypeTogglesCss = join(prototypesDir, "shared/prototype-toggles.css");
const prototypeTokensStyleCss = join(prototypesDir, "tokens-style.css");
const designSpec = join(root, "DESIGN.md");
const pagePatternLibrarySpec = join(root, "docs/designs/specs/11_ditto_page_pattern_library.md");
const tokenNamingLayeringSpec = join(
	root,
	"docs/designs/specs/14_ditto_token_naming_layering_spec.md",
);
const tokenStabilizationSpec = join(
	root,
	"docs/designs/specs/15_ditto_token_stabilization_spec.md",
);
const expectedActiveRoutePrototypeCount = 28;
const archivedPrototypeIds = new Set(["ai-overview", "ai-copilot"]);
const auditedPrototypeFiles = ["page-alpha-explorer.html", "page-agent-console-v2.html"] as const;
const prototypeStructuralDimensionTokens = {
	"--panel-header-height": "38px",
	"--tab-bar-height": "42px",
	"--progress-bar-height": "6px",
	"--surface-noise-opacity": "0.018",
} as const;

type ManifestPage = {
	id: string;
	file: string;
	shellFamily?: string;
	status?: string;
	landing?: {
		overlayStatus?: string;
	};
};

type EditionManifest = {
	pages: ManifestPage[];
};

type PageContract = {
	id: string;
	prototypeRef: string;
	nextPrototypeRef?: string;
	shellFamily: string;
	overlays?: Array<{ id: string; prototypeSelector: string }>;
	nextOverlays?: Array<{ prototypeSelector: string }>;
	nextSlots?: unknown[];
};

type CssSource = {
	label: string;
	css: string;
};

type CssBlock = {
	body: string;
	start: number;
	end: number;
};

type CssRule = {
	selector: string;
	selectors: string[];
	body: string;
	start: number;
	end: number;
	mediaMaxWidth?: number;
};

function readJson<T>(path: string): T {
	return JSON.parse(readFileSync(path, "utf8")) as T;
}

let manifestCache: EditionManifest | undefined;
const prototypeHtmlCache = new Map<string, string>();
const prototypeDocumentCache = new Map<string, Document>();
let contractsCache: PageContract[] | undefined;

function readManifest(): EditionManifest {
	manifestCache ??= readJson<EditionManifest>(join(prototypesDir, ".edition-manifest.json"));
	return manifestCache;
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

function readPrototypeHtml(page: ManifestPage): string {
	const path = join(prototypesDir, page.file);
	const cached = prototypeHtmlCache.get(path);
	if (cached) return cached;

	const html = readFileSync(path, "utf8");
	prototypeHtmlCache.set(path, html);
	return html;
}

function getOverlayIds(html: string): string[] {
	return [...new Set([...html.matchAll(/id="(overlay-[^"]+)"/g)].map((match) => match[1]))];
}

function selectorReferencesOverlayId(selector: string, id: string): boolean {
	return (
		selector === `#${id}` ||
		selector === `[data-overlay='${id}']` ||
		selector === `[data-overlay="${id}"]` ||
		selector === `[data-overlay-ref='${id}']` ||
		selector === `[data-overlay-ref="${id}"]`
	);
}

function readContracts(): PageContract[] {
	contractsCache ??= readdirSync(contractsDir)
		.filter((file) => file.endsWith(".json"))
		.map((file) => readJson<PageContract>(join(contractsDir, file)));
	return contractsCache;
}

function countMatches(value: string, pattern: RegExp): number {
	return [...value.matchAll(pattern)].length;
}

function getElementBodyById(html: string, id: string): string {
	const openTag = new RegExp(`<([a-z]+)[^>]*id="${id}"[^>]*>`, "i").exec(html);
	if (!openTag?.index) return "";

	const tagName = openTag[1];
	const bodyStart = openTag.index + openTag[0].length;
	const closeTag = new RegExp(`</${tagName}>`, "i");
	const closeMatch = closeTag.exec(html.slice(bodyStart));

	return closeMatch ? html.slice(bodyStart, bodyStart + closeMatch.index) : "";
}

function getStyleBlocks(html: string): string {
	return [...html.matchAll(/<style[^>]*>([\s\S]*?)<\/style>/gi)]
		.map((match) => match[1])
		.join("\n");
}

function stripCssComments(css: string): string {
	return css.replace(/\/\*[\s\S]*?\*\//g, (comment) =>
		comment
			.split("")
			.map((char) => (char === "\n" ? "\n" : " "))
			.join(""),
	);
}

function getBalancedCssBlock(css: string, openBraceIndex: number): CssBlock | undefined {
	let depth = 0;
	for (let index = openBraceIndex; index < css.length; index += 1) {
		const char = css[index];
		if (char === "{") depth += 1;
		if (char === "}") depth -= 1;
		if (depth === 0) {
			return {
				body: css.slice(openBraceIndex + 1, index),
				start: openBraceIndex + 1,
				end: index,
			};
		}
	}

	return undefined;
}

function getMediaBlock(css: string, maxWidthPx: number): string | undefined {
	const mediaMatch = new RegExp(`@media\\s*\\(\\s*max-width\\s*:\\s*${maxWidthPx}px\\s*\\)\\s*\\{`, "i")
		.exec(css);
	if (mediaMatch?.index === undefined) return undefined;

	const openBraceIndex = css.indexOf("{", mediaMatch.index);
	return getBalancedCssBlock(css, openBraceIndex)?.body;
}

function getMediaBlocksMatching(css: string, pattern: RegExp): string[] {
	const blocks: string[] = [];
	let searchIndex = 0;

	while (searchIndex < css.length) {
		const mediaIndex = css.indexOf("@media", searchIndex);
		if (mediaIndex === -1) break;

		const openBraceIndex = css.indexOf("{", mediaIndex);
		if (openBraceIndex === -1) break;

		const query = css.slice(mediaIndex, openBraceIndex);
		const block = getBalancedCssBlock(css, openBraceIndex);
		if (!block) break;
		if (pattern.test(query)) blocks.push(block.body);

		searchIndex = block.end + 1;
	}

	return blocks;
}

function readTopLevelCssRules(css: string, offset = 0, mediaMaxWidth?: number): CssRule[] {
	const rules: CssRule[] = [];
	let index = 0;

	while (index < css.length) {
		const openBraceIndex = css.indexOf("{", index);
		if (openBraceIndex === -1) break;

		const selector = css.slice(index, openBraceIndex).trim();
		const block = getBalancedCssBlock(css, openBraceIndex);
		if (!block) break;

		if (selector.startsWith("@media")) {
			const maxWidthMatch = /\(\s*max-width\s*:\s*(\d+)px\s*\)/i.exec(selector);
			if (maxWidthMatch) {
				rules.push(
					...readTopLevelCssRules(
						block.body,
						offset + block.start,
						Number.parseInt(maxWidthMatch[1], 10),
					),
				);
			}
		} else if (!selector.startsWith("@")) {
			rules.push({
				selector,
				selectors: selector.split(",").map((item) => item.trim()),
				body: block.body,
				start: offset + index,
				end: offset + block.end,
				mediaMaxWidth,
			});
		}

		index = block.end + 1;
	}

	return rules;
}

function getSelectorRuleBody(css: string, selector: string): string | undefined {
	return readTopLevelCssRules(stripCssComments(css)).find((rule) => rule.selectors.includes(selector))
		?.body;
}

function hasDeclaration(body: string | undefined, property: string, valuePattern: RegExp): boolean {
	if (!body) return false;

	return [...body.matchAll(new RegExp(`${property}\\s*:\\s*([^;]+)`, "gi"))].some((match) =>
		valuePattern.test(match[1].trim()),
	);
}

function getLineNumber(value: string, index: number): number {
	return value.slice(0, index).split("\n").length;
}

function hasFixedCanvasException(css: string, index: number): boolean {
	const lineStart = css.lastIndexOf("\n", index) + 1;
	const lineEnd = css.indexOf("\n", index);
	const previousLineEnd = lineStart > 0 ? lineStart - 1 : -1;
	const previousLineStart = previousLineEnd > 0 ? css.lastIndexOf("\n", previousLineEnd - 1) + 1 : 0;
	const lines = [
		css.slice(previousLineStart, previousLineEnd === -1 ? 0 : previousLineEnd),
		css.slice(lineStart, lineEnd === -1 ? css.length : lineEnd),
	].join("\n");

	return /fixed canvas exception|fixed-canvas-exception/i.test(lines);
}

function declarationHasNonNoneValue(body: string, property: "outline"): boolean {
	const declaration = new RegExp(`${property}\\s*:\\s*([^;]+)`, "gi");

	return [...body.matchAll(declaration)].some((match) => {
		const value = match[1].trim();
		return !/^none(?:\s*!important)?$/i.test(value);
	});
}

function hasFocusSelector(selector: string): boolean {
	return /:focus(?:-visible|-within)?\b/.test(selector);
}

function hasFocusRingBoxShadow(body: string): boolean {
	return [...body.matchAll(/box-shadow\s*:\s*([^;]+)/gi)].some((match) => {
		const value = match[1].trim();
		if (/^none(?:\s*!important)?$/i.test(value)) return false;

		return (
			/var\(\s*--(?:interaction-focus-ring|interaction-focus-border|focus-ring|brand-accent)\b/.test(value) ||
			/\b0\s+0\s+0\b/.test(value)
		);
	});
}

function readPrototypeCssSources(): CssSource[] {
	return [
		{ label: "shared/fonts.css", css: readFileSync(prototypeFontsCss, "utf8") },
		{ label: "shared/layout-shell.css", css: readFileSync(prototypeLayoutCss, "utf8") },
		{ label: "shared/layout-gallery.css", css: readFileSync(join(prototypesDir, "shared/layout-gallery.css"), "utf8") },
		{ label: "shared/layout-components.css", css: readFileSync(join(prototypesDir, "shared/layout-components.css"), "utf8") },
		{ label: "shared/layout-overlay.css", css: readFileSync(join(prototypesDir, "shared/layout-overlay.css"), "utf8") },
		{ label: "shared/layout-state.css", css: readFileSync(join(prototypesDir, "shared/layout-state.css"), "utf8") },
		{ label: "shared/theme-switcher.css", css: readFileSync(prototypeThemeSwitcherCss, "utf8") },
		{ label: "shared/prototype-toggles.css", css: readFileSync(prototypeTogglesCss, "utf8") },
		{ label: "tokens-style.css", css: readFileSync(prototypeTokensStyleCss, "utf8") },
		...activePages().map((page) => ({
			label: `${page.id}:inline-css`,
			css: getStyleBlocks(readPrototypeHtml(page)),
		})),
	];
}

function getFirstElementBody(html: string, selectorPattern: RegExp): string {
	const openTag = selectorPattern.exec(html);
	if (openTag?.index === undefined) return "";

	const fullOpenTag = openTag[0];
	const tagName = /<([a-z]+)/i.exec(fullOpenTag)?.[1];
	if (!tagName) return "";

	const bodyStart = openTag.index + fullOpenTag.length;
	const closeMatch = new RegExp(`</${tagName}>`, "i").exec(html.slice(bodyStart));
	return closeMatch ? html.slice(bodyStart, bodyStart + closeMatch.index) : "";
}

function getHeaderHtml(html: string): string {
	return getFirstElementBody(html, /<header\b[^>]*class="[^"]*shell-header[^"]*"[^>]*>/i);
}

function getRailHtml(html: string): string {
	return getFirstElementBody(html, /<nav\b[^>]*class="[^"]*shell-rail[^"]*"[^>]*>/i);
}

function readPrototypeDocument(page: ManifestPage): Document {
	const path = join(prototypesDir, page.file);
	const cached = prototypeDocumentCache.get(path);
	if (cached) return cached;

	const document = new JSDOM(readPrototypeHtml(page)).window.document;
	prototypeDocumentCache.set(path, document);
	return document;
}

const shellDomains = new Set(["home", "markets", "research", "trading", "platform"]);
const requiredHeaderUtilities = [
	"command",
	"copilot",
	"notifications",
	"help",
	"theme",
	"density",
	"account",
] as const;
const bottomTrayPages = ["strategy-studio", "agent-console", "platform", "trading-overview"];
const dataVizContractPages = [
	"a-shares",
	"cross-market",
	"risk-center",
	"regime-monitor",
	"factor-analysis",
	"backtest-result",
];
const catalogContractPages = [
	"watchlist",
	"factor-list",
	"strategy-list",
	"backtest-list",
	"experiment-list",
	"universe-list",
	"markets-screener",
	"markets-calendar",
];
const highRiskActionPages = [
	"platform-settings",
	"trading-overview",
	"universe-list",
	"strategy-list",
];
const approvedHeaderTitleTerms = ["Alpha"] as const;
const homeTokenFocusSelectors = [
	".header-utility-btn",
	".decision-cta",
	".panel-action",
	".overlay-btn",
	".state-empty-cta",
	'.worklist-row[role="row"]',
] as const;
const sharedCanonicalFocusSelectors = [
	".rail-icon",
	".btn",
	".header-utility-btn",
	".header-action-btn",
	".header-avatar",
	".header-btn-badge",
	".decision-cta",
	".panel-action",
	".overlay-btn",
	".state-empty-cta",
	".filter-btn",
	".filter-chip",
	".tab",
	".mode-tab",
	".hub-tab",
	".meta-chip",
	".data-table tr.row",
	'.worklist-row[role="row"]',
	".collapsible-strip-toggle",
] as const;
const motionRemediationPageIds = [
	"alpha-explorer",
	"signals-inbox",
	"agent-console-v2",
	"research",
] as const;
const signalsInboxReducedMotionFamilies = [
	"dot-pulse",
	"row-enter",
	"detail-slide-in",
	"spin",
	"scope-tab-enter",
] as const;
const catalogSubtypeSummaryRequirements: Record<string, Array<{ label: string; pattern: RegExp }>> = {
	"strategy-list": [
		{ label: "可运行", pattern: /可运行/ },
		{ label: "需处理", pattern: /需处理/ },
		{ label: "Sharpe", pattern: /Sharpe/i },
		{ label: "风险约束", pattern: /风险约束/ },
		{ label: "最佳健康策略", pattern: /最佳健康策略/ },
		{ label: "暂停原因", pattern: /暂停原因/ },
		{ label: "最近运行", pattern: /最近运行/ },
	],
	"backtest-list": [
		{ label: "对比", pattern: /对比/ },
		{ label: "失败", pattern: /失败/ },
		{ label: "基线", pattern: /基线/ },
		{ label: "MDD", pattern: /MDD/i },
	],
	"experiment-list": [
		{ label: "胜出", pattern: /胜出/ },
		{ label: "参数稳定性", pattern: /参数稳定性/ },
		{ label: "显著性", pattern: /显著性/ },
		{ label: "失败原因", pattern: /失败原因/ },
		{ label: "待复核", pattern: /待复核/ },
	],
	"factor-list": [
		{ label: "IC", pattern: /\bIC\b/i },
		{ label: "IR", pattern: /\bIR\b/i },
		{ label: "衰减", pattern: /衰减/ },
		{ label: "覆盖率", pattern: /覆盖率/ },
		{ label: "关联策略", pattern: /关联策略/ },
		{ label: "最近失效信号", pattern: /最近失效信号/ },
	],
	watchlist: [
		{ label: "触发动作", pattern: /触发动作/ },
		{ label: "信号结构", pattern: /信号结构/ },
		{ label: "stale", pattern: /stale/i },
		{ label: "下一步", pattern: /下一步/ },
	],
};

function activePages(): ManifestPage[] {
	return readManifest().pages.filter(isActiveRoutePrototype);
}

function activePageById(id: string): ManifestPage {
	const page = activePages().find((prototype) => prototype.id === id);
	if (!page) throw new Error(`Active prototype not found: ${id}`);

	return page;
}

function readTokenCssBundle(): string {
	const tokenDir = join(root, "src/styles/design-tokens");
	const tokenCss = readdirSync(tokenDir)
		.filter((file) => file.endsWith(".css"))
		.map((file) => readFileSync(join(tokenDir, file), "utf8"))
		.join("\n");

	return [
		tokenCss,
		readFileSync(prototypeTokensStyleCss, "utf8"),
		readFileSync(prototypeThemeSwitcherCss, "utf8"),
		readAllLayoutCss(),
	].join("\n");
}

function extractCustomPropertyDefinitions(css: string): Set<string> {
	return new Set([...css.matchAll(/(--[a-z0-9-]+)\s*:/gi)].map((match) => match[1]));
}

function extractCustomPropertyReferences(css: string): Set<string> {
	return new Set([...css.matchAll(/var\(\s*(--[a-z0-9-]+)/gi)].map((match) => match[1]));
}

function getCssFontSizeValues(body: string): string[] {
	return [...body.matchAll(/font-size\s*:\s*([^;]+)/gi)].map((match) => match[1].trim());
}

function getPrototypeCssRules(page: ManifestPage): CssRule[] {
	return readTopLevelCssRules(stripCssComments(getStyleBlocks(readPrototypeHtml(page))));
}

function parseFontSizeMinimumPx(value: string): number | undefined {
	const tokenMatch = /var\(\s*--font-size-(\d+)\s*\)/i.exec(value);
	if (tokenMatch) return Number.parseInt(tokenMatch[1], 10);

	const pxMatch = /(\d+(?:\.\d+)?)px\b/i.exec(value);
	if (pxMatch) return Number.parseFloat(pxMatch[1]);

	return undefined;
}

function usesFontSizeToken(body: string, token: string): boolean {
	return getCssFontSizeValues(body).some((fontSize) =>
		new RegExp(`var\\(\\s*${token}\\s*\\)`, "i").test(fontSize),
	);
}

function hasCursorPointer(body: string): boolean {
	return hasDeclaration(body, "cursor", /^pointer$/i);
}

function stripSelectorForDom(selector: string): string {
	return selector
		.replace(/::?[a-z-]+(?:\([^)]*\))?/gi, "")
		.replace(/\s+/g, " ")
		.trim();
}

function querySelectorAllSafe(document: Document, selector: string): Element[] {
	const domSelector = stripSelectorForDom(selector);
	if (!domSelector) return [];

	try {
		return [...document.querySelectorAll(domSelector)];
	} catch {
		return [];
	}
}

function elementClosestSafe(element: Element, selector: string): Element | null {
	const domSelector = stripSelectorForDom(selector);
	if (!domSelector) return null;

	try {
		return element.closest(domSelector);
	} catch {
		return null;
	}
}

function isInteractivePrototypeElement(element: Element): boolean {
	return element.matches(
		"button, a, label, input, select, textarea, summary, [role='button'], [role='switch'], [role='tab']",
	);
}

function isInsideInteractivePrototypeTarget(element: Element): boolean {
	return Boolean(
		element.closest(
			[
				"button",
				"a",
				"label",
				"input",
				"select",
				"textarea",
				"summary",
				"[role='button']",
				"[role='switch']",
				"[role='tab']",
				".tab",
				".tabs",
				".segmented-control",
			].join(", "),
		),
	);
}

function isInsideOperationalTableLikeContainer(element: Element): boolean {
	return Boolean(
		element.closest(
			[
				"table",
				"[role='grid']",
				"[role='table']",
				"[role='row']",
				".data-table",
				".catalog-table",
				".compare-table",
				".ledger-table",
				".matrix-table",
				".orders-table",
				".risk-table",
				".signals-table",
				".worklist",
				".worklist-row",
			].join(", "),
		),
	);
}

function isInsideOperationalAnswerContainer(element: Element): boolean {
	const hasHeaderLikeClass = (candidate: Element) =>
		[...candidate.classList].some((className) => /\bheader\b|(?:^|-)header(?:-|$)/i.test(className));
	const headerLikeAncestor = element.closest("*");

	return Boolean(
		element.closest(
			[
				"header",
				"[data-contract-slot='header']",
				"[data-primary-answer]",
				"[data-primary-answer-equivalent]",
			].join(", "),
		) ??
			(() => {
				let current: Element | null = headerLikeAncestor;
				while (current) {
					if (hasHeaderLikeClass(current)) return current;
					current = current.parentElement;
				}
				return null;
			})(),
	);
}

function selectorDescendsFromSelector(selector: string, ancestorSelector: string): boolean {
	const normalizeSelector = (value: string) =>
		stripSelectorForDom(value)
			.replace(/\s*([>+~])\s*/g, " $1 ")
			.replace(/\s+/g, " ")
			.trim();
	const normalizedSelector = normalizeSelector(selector);
	const normalizedAncestor = normalizeSelector(ancestorSelector);
	if (!normalizedSelector || !normalizedAncestor) return false;

	return normalizedSelector.startsWith(`${normalizedAncestor} `);
}

function hasPointerAncestorSelector(selector: string, pointerSelectors: string[]): boolean {
	return pointerSelectors.some((pointerSelector) =>
		selectorDescendsFromSelector(selector, pointerSelector),
	);
}

function isOperationalElevenPxSelector(selector: string): boolean {
	const normalized = selector.toLowerCase();
	return /(?:button|btn|tab|header|strip|title|table|\btbl\b|primary-answer|interactive|\blink\b|\baction\b|role=['"]button['"])/.test(
		normalized,
	);
}

function hasOperationalElevenPxUsage(
	document: Document,
	rule: CssRule,
	selector: string,
	pointerSelectors: string[],
): boolean {
	if (isOperationalElevenPxSelector(selector) || hasCursorPointer(rule.body)) return true;
	if (hasPointerAncestorSelector(selector, pointerSelectors)) return true;

	const elements = querySelectorAllSafe(document, selector);
	return elements.some(
		(element) =>
			isInteractivePrototypeElement(element) ||
			isInsideInteractivePrototypeTarget(element) ||
			isInsideOperationalTableLikeContainer(element) ||
			isInsideOperationalAnswerContainer(element) ||
			pointerSelectors.some((pointerSelector) => elementClosestSafe(element, pointerSelector)),
	);
}

function isHiddenFromPrimaryContract(element: Element | null): boolean {
	return Boolean(element?.closest("[aria-hidden='true']"));
}

function getVisibleTextContent(element: Element): string {
	const collectText = (node: Node): string[] => {
		if (node.nodeType === 3) return [node.textContent ?? ""];
		if (node.nodeType !== 1) return [];

		const childElement = node as Element;
		if (isHiddenFromPrimaryContract(childElement)) return [];

		return [...childElement.childNodes].flatMap(collectText);
	};

	return collectText(element).join(" ").replace(/\s+/g, " ").trim();
}

function getReadablePrimaryText(element: Element | null): string {
	if (!element || isHiddenFromPrimaryContract(element)) return "";

	return (
		getVisibleTextContent(element) ||
		element.getAttribute("value")?.replace(/\s+/g, " ").trim() ||
		element.getAttribute("aria-label")?.replace(/\s+/g, " ").trim() ||
		""
	);
}

function hasReadableText(element: Element | null): boolean {
	return Boolean(getReadablePrimaryText(element));
}

function hasReadableTextMatch(element: Element, pattern: RegExp): boolean {
	return pattern.test(getReadablePrimaryText(element));
}

function isDefaultVisibleElement(element: Element): boolean {
	if (element.closest("[hidden], [aria-hidden='true']")) return false;

	const closedDetails = element.closest("details:not([open])");
	if (!closedDetails) return true;

	const summary = element.closest("summary");
	return Boolean(summary && closedDetails.contains(summary));
}

function firstNumberFromText(value: string | null | undefined): number | undefined {
	const numberMatch = value?.match(/\d+/);
	return numberMatch ? Number(numberMatch[0]) : undefined;
}

function fallbackTextMatchesCounter(element: Element): boolean {
	const rawCounterValue = element.getAttribute("data-counter");
	if (!rawCounterValue?.trim()) return false;

	const counterValue = Number(rawCounterValue);
	if (!Number.isFinite(counterValue)) return false;
	const signedCounterValue = element.getAttribute("data-counter-prefix")?.trim().startsWith("-")
		? -Math.abs(counterValue)
		: counterValue;

	const text = (element.textContent ?? "").replace(/,/g, "").trim();
	const textNumberMatch = /[-+]?\d+(?:\.\d+)?/.exec(text);
	if (!textNumberMatch) return false;

	const textValue = Number(textNumberMatch[0]);
	if (!Number.isFinite(textValue)) return false;

	const decimals = Number.parseInt(element.getAttribute("data-counter-decimals") ?? "2", 10);
	const precision = Number.isFinite(decimals) ? Math.max(0, decimals) : 2;
	const tolerance = precision === 0 ? 0 : 1 / 10 ** precision;

	return Math.abs(textValue - signedCounterValue) <= tolerance;
}

function hasExistingIdTarget(element: Element, attribute: string): boolean {
	const value = element.getAttribute(attribute)?.trim();
	if (!value) return false;

	return value.split(/\s+/).every((id) => element.ownerDocument.getElementById(id) !== null);
}

function hasVisibleAriaControlsTarget(element: Element): boolean {
	const value = element.getAttribute("aria-controls")?.trim();
	if (!value) return false;

	return value.split(/\s+/).every((id) => {
		const target = element.ownerDocument.getElementById(id);
		return target !== null && target.getAttribute("aria-hidden") !== "true";
	});
}

function hasMatchingAttributeTarget(element: Element, attribute: string, targetAttribute: string): boolean {
	const value = element.getAttribute(attribute)?.trim();
	if (!value) return false;

	const targets = [...element.ownerDocument.querySelectorAll(`[${targetAttribute}]`)];

	return value.split(/\s+/).every((targetValue) =>
		targets.some((target) => target.getAttribute(targetAttribute) === targetValue),
	);
}

function hasOverlayTarget(element: Element): boolean {
	const value = element.getAttribute("data-overlay-ref")?.trim();
	if (!value) return false;

	const overlays = [...element.ownerDocument.querySelectorAll("[data-overlay]")];

	return value.split(/\s+/).every((targetValue) =>
		element.ownerDocument.getElementById(targetValue) !== null ||
		overlays.some((overlay) => overlay.getAttribute("data-overlay") === targetValue),
	);
}

function hasActionTarget(element: Element): boolean {
	const tagName = element.tagName.toLowerCase();
	if (tagName === "button") return true;
	if (tagName === "a") return Boolean(element.getAttribute("href")?.trim());

	return (
		hasExistingIdTarget(element, "for") ||
		hasVisibleAriaControlsTarget(element) ||
		element.hasAttribute("onclick") ||
		hasMatchingAttributeTarget(element, "data-tab-target", "data-tab-panel") ||
		hasOverlayTarget(element) ||
		hasExistingIdTarget(element, "data-action-target") ||
		hasExistingIdTarget(element, "data-drilldown-target")
	);
}

function isActionablePrimaryAnswerElement(element: Element): boolean {
	const tagName = element.tagName.toLowerCase();
	if (tagName === "button") return true;
	if (tagName === "a") return Boolean(element.getAttribute("href")?.trim());

	const role = element.getAttribute("role");
	const tabindex = element.getAttribute("tabindex");

	return (role === "button" || role === "link") && tabindex === "0" && hasActionTarget(element);
}

function hasPrimaryAnswerJudgment(region: Element): boolean {
	return (
		hasReadableText(region.querySelector("[data-answer-judgment], .answer-judgment")) ||
		[...region.querySelectorAll("h1, h2, h3, h4, [role='heading'], .summary-label, .eyebrow")].some(
			hasReadableText,
		)
	);
}

function hasPrimaryAnswerMetric(region: Element): boolean {
	return (
		hasReadableText(region.querySelector("[data-answer-metric], .answer-metric")) ||
		[...region.querySelectorAll("[class*='metric'], [class*='kpi'], [class*='stat'], data, output")].some(
			(element) => hasReadableTextMatch(element, /\d/),
		)
	);
}

function hasPrimaryAnswerAction(region: Element): boolean {
	const markedActionSelector = "[data-answer-action], .answer-action";
	const markedActions = [
		...(region.matches(markedActionSelector) ? [region] : []),
		...region.querySelectorAll(markedActionSelector),
	];

	return markedActions.some((element) => isActionablePrimaryAnswerElement(element) && hasReadableText(element));
}

function getPrimaryAnswerEvidenceCount(region: Element): number {
	return [...region.querySelectorAll("[data-answer-evidence], .answer-evidence")].filter(hasReadableText).length;
}

function hasPrimaryAnswerScope(region: Element): boolean {
	if (hasReadableText(region.querySelector("[data-answer-scope], .answer-scope"))) return true;

	const ariaLabel = region.getAttribute("aria-label")?.trim();
	if (ariaLabel && /(?:scope|范围|覆盖|影响)/i.test(ariaLabel)) return true;

	return hasReadableTextMatch(region, /(?:scope|范围|覆盖|影响|全局|当前|账户|组合|市场|标的|策略|实验|服务)/i);
}

function removeApprovedHeaderTitleTerms(text: string): string {
	return approvedHeaderTitleTerms.reduce(
		(current, term) => current.replace(new RegExp(`\\b${term}\\b`, "gi"), ""),
		text,
	);
}

function hasTokenFocusRule(css: string, selector: string): boolean {
	return readTopLevelCssRules(stripCssComments(css)).some(
		(rule) =>
			hasFocusSelector(rule.selector) &&
			rule.selector.includes(selector) &&
			/--interaction-focus-ring/.test(rule.body),
	);
}

function hasCanonicalFocusOutlineRule(css: string, selector: string): boolean {
	return readTopLevelCssRules(stripCssComments(css)).some(
		(rule) =>
			hasFocusSelector(rule.selector) &&
			rule.selector.includes(selector) &&
			hasDeclaration(rule.body, "outline", /^2px\s+solid\s+var\(\s*--interaction-focus-ring\s*\)$/i) &&
			hasDeclaration(rule.body, "outline-offset", /^2px$/i),
	);
}

function usesNonCanonicalFocusColor(body: string): boolean {
	return /--(?:brand-accent|interaction-selected-[a-z-]+)/.test(body);
}

function getMotionDeclarations(css: string): Array<{ line: number; property: string; value: string }> {
	return [...css.matchAll(/\b(transition|animation)\s*:\s*([^;{}]+);/gi)].flatMap((match) => {
		const value = match[2].trim();
		if (match[1].toLowerCase() === "animation" && /^none(?:\s*!important)?$/i.test(value)) {
			return [];
		}

		return [
			{
				line: getLineNumber(css, match.index ?? 0),
				property: match[1].toLowerCase(),
				value,
			},
		];
	});
}

function getTransitionItems(value: string): string[] {
	return value
		.split(",")
		.map((item) => item.trim())
		.filter(Boolean);
}

describe("prototype design consistency", () => {
	it("keeps exactly 28 active route prototypes", () => {
		const activePages = readManifest().pages.filter(isActiveRoutePrototype);

		expect(activePages).toHaveLength(expectedActiveRoutePrototypeCount);
	});

	it("keeps audited prototype pages active in the manifest", () => {
		const manifestFiles = new Set(activePages().map((page) => page.file));
		const inactive = auditedPrototypeFiles.filter((file) => !manifestFiles.has(file));

		expect(inactive).toEqual([]);
	});

	it("keeps Agent Console v2 as the only active canonical prototype", () => {
		const agentConsolePages = readManifest().pages.filter((page) =>
			page.id.startsWith("agent-console"),
		);
		const activeAgentConsolePages = agentConsolePages.filter(isActiveRoutePrototype);
		const canonicalContract = readContracts().find((contract) => contract.id === "agent-console");

		expect(activeAgentConsolePages.map((page) => page.file)).toEqual([
			"page-agent-console-v2.html",
		]);
		expect(agentConsolePages.find((page) => page.id === "agent-console")?.status).toBe(
			"archived-specimen",
		);
		expect(canonicalContract?.prototypeRef).toBe(
			"docs/designs/specs/prototypes/page-agent-console-v2.html",
		);
		expect(canonicalContract?.nextPrototypeRef).toBeUndefined();
		expect(canonicalContract?.nextSlots).toBeUndefined();
		expect(canonicalContract?.nextOverlays).toBeUndefined();
	});

	it("keeps deprecated AI route specimens in the prototype archive", () => {
		const manifest = readManifest();
		const archivedPages = [...archivedPrototypeIds].map((id) => manifest.pages.find((page) => page.id === id));

		for (const page of archivedPages) {
			expect(page?.status).toBe("archived-specimen");
			expect(page?.file).toMatch(/^archive\/2026-04-30\/page-ai-(?:overview|copilot)\.html$/);
			expect(existsSync(join(prototypesDir, page?.file ?? ""))).toBe(true);
		}
	});

	it("keeps active route prototypes on the five IA domains", () => {
		const violations = readManifest()
			.pages.filter(isActiveRoutePrototype)
			.flatMap((page) => {
				const domain = /data-domain="([^"]+)"/.exec(readPrototypeHtml(page))?.[1];
				return domain && !shellDomains.has(domain) ? [`${page.id}:${domain}`] : [];
			});

		expect(violations).toEqual([]);
	});

	it("keeps rail limited to top-level product navigation", () => {
		const violations: string[] = [];

		for (const page of readManifest().pages.filter(isActiveRoutePrototype)) {
			const rail = getRailHtml(readPrototypeHtml(page));
			if (/id="density-toggle"|id="theme-toggle"|aria-label="设置"|aria-label="用户"/.test(rail)) {
				violations.push(page.id);
			}
		}

		expect(violations).toEqual([]);
	});

	it("exposes the same global header utilities in active route prototypes", () => {
		const violations: string[] = [];

		for (const page of readManifest().pages.filter(isActiveRoutePrototype)) {
			const header = getHeaderHtml(readPrototypeHtml(page));
			for (const utility of requiredHeaderUtilities) {
				if (!header.includes(`data-shell-utility="${utility}"`)) {
					violations.push(`${page.id}:${utility}`);
				}
			}
		}

		expect(violations).toEqual([]);
	});

	it(
		"keeps global header utilities in one semantic utility bar",
		() => {
			const violations: string[] = [];

			for (const page of readManifest().pages.filter(isActiveRoutePrototype)) {
				const document = readPrototypeDocument(page);
				const header = document.querySelector(".shell-header");
				if (!header) {
					violations.push(`${page.id}:missing-header`);
					continue;
				}

				const utilityBars = header.querySelectorAll("[data-header-utility-bar]");
				if (utilityBars.length !== 1) {
					violations.push(`${page.id}:utility-bars:${utilityBars.length}`);
				}

				for (const utility of header.querySelectorAll("[data-shell-utility]")) {
					if (!utility.closest("[data-header-utility-bar]")) {
						violations.push(
							`${page.id}:orphan:${utility.getAttribute("data-shell-utility") ?? "unknown"}`,
						);
					}
				}
			}

			expect(violations).toEqual([]);
		},
		20_000,
	);

	it("keeps global header utilities in contract DOM order", () => {
		const violations: string[] = [];

		for (const page of readManifest().pages.filter(isActiveRoutePrototype)) {
			const document = readPrototypeDocument(page);
			const utilities = [
				...document.querySelectorAll(".shell-header [data-shell-utility]"),
			].map((element) => element.getAttribute("data-shell-utility"));

			if (utilities.join(">") !== requiredHeaderUtilities.join(">")) {
				violations.push(`${page.id}:${utilities.join(">")}`);
			}
		}

		expect(violations).toEqual([]);
	});

	it("uses button semantics for every global header utility", () => {
		const violations: string[] = [];

		for (const page of activePages()) {
			const document = readPrototypeDocument(page);
			for (const utility of document.querySelectorAll(".shell-header [data-shell-utility]")) {
				const utilityName = utility.getAttribute("data-shell-utility") ?? "unknown";
				if (utility.tagName.toLowerCase() !== "button") {
					violations.push(`${page.id}:${utilityName}:tag:${utility.tagName.toLowerCase()}`);
				}

				if (utility.getAttribute("type") !== "button") {
					violations.push(`${page.id}:${utilityName}:type`);
				}

				if (
					utilityName === "command" &&
					!utility.classList.contains("header-command-trigger")
				) {
					violations.push(`${page.id}:command:visual-form`);
				}
			}
		}

		expect(violations).toEqual([]);
	});

	it("exposes one semantic page h1 and keeps prototype style labels hidden from assistive tech", () => {
		const violations: string[] = [];

		for (const page of activePages()) {
			const document = readPrototypeDocument(page);
			const h1Count = document.querySelectorAll("h1").length;
			const visibleStyleLabelCount = document.querySelectorAll(".style-label:not([aria-hidden='true'])").length;

			if (h1Count !== 1) {
				violations.push(`${page.id}:h1:${h1Count}`);
			}
			if (visibleStyleLabelCount > 0) {
				violations.push(`${page.id}:visible-style-label:${visibleStyleLabelCount}`);
			}
		}

		expect(violations).toEqual([]);
	});

	it("exposes exactly one complete primary answer contract in every active prototype", () => {
		const violations: string[] = [];

		for (const page of activePages()) {
			const document = readPrototypeDocument(page);
			const primaryAnswerRegions = [
				...document.querySelectorAll("[data-primary-answer], [data-primary-answer-equivalent]"),
			];

			if (primaryAnswerRegions.length !== 1) {
				violations.push(`${page.id}:primary-answer-count:${primaryAnswerRegions.length}`);
				continue;
			}

			const [region] = primaryAnswerRegions;
			if (!hasPrimaryAnswerJudgment(region)) {
				violations.push(`${page.id}:missing-judgment`);
			}
			if (!hasPrimaryAnswerMetric(region)) {
				violations.push(`${page.id}:missing-metric`);
			}
			if (!hasPrimaryAnswerAction(region)) {
				violations.push(`${page.id}:missing-action`);
			}
			const evidenceCount = getPrimaryAnswerEvidenceCount(region);
			if (evidenceCount < 2 || evidenceCount > 3) {
				violations.push(`${page.id}:evidence-count:${evidenceCount}`);
			}
			if (!hasPrimaryAnswerScope(region)) {
				violations.push(`${page.id}:missing-scope`);
			}
		}

		expect(violations).toEqual([]);
	});

	it("keeps data-counter fallback text numerically aligned with animated values", () => {
		const violations: string[] = [];

		for (const page of activePages()) {
			const document = readPrototypeDocument(page);
			const counterElements = document.querySelectorAll("[data-counter]");

			for (const element of counterElements) {
				if (element.hasAttribute("data-counter-fallback-exception")) continue;

				const value = element.getAttribute("data-counter");
				if (!fallbackTextMatchesCounter(element)) {
					violations.push(`${page.id}: data-counter fallback must match ${value}`);
				}
			}
		}

		expect(violations).toEqual([]);
	});

	it("keeps the Home first screen centered on one decision surface", () => {
		const document = readPrototypeDocument(activePageById("home"));
		const violations: string[] = [];

		const globalPulseSlots = document.querySelectorAll('[data-contract-slot="global-pulse"]');
		if (globalPulseSlots.length !== 1) {
			violations.push(`home:global-pulse:${globalPulseSlots.length}`);
		}
		if (document.querySelector('[data-contract-slot="today-pulse"]')) {
			violations.push("home:legacy-today-pulse");
		}

		const decisionCards = document.querySelectorAll(
			'[data-contract-slot="decision-card"][data-primary-answer]',
		);
		if (decisionCards.length !== 1) {
			violations.push(`home:decision-card:${decisionCards.length}`);
		}
		if (document.querySelector('[data-contract-slot="decision-banner"]')) {
			violations.push("home:legacy-decision-banner");
		}

		const priorityQueue = document.querySelector('[data-contract-slot="pending-actions"]');
		const priorityQueueCount = firstNumberFromText(
			priorityQueue?.querySelector(".panel-count")?.textContent,
		);
		const visibleQueueItems = [...(priorityQueue?.querySelectorAll(".queue-item") ?? [])].filter(
			isDefaultVisibleElement,
		);
		const visiblePriorities = visibleQueueItems.map((item) =>
			item.querySelector(".queue-item-tag.priority")?.textContent?.trim() ?? "unprioritized",
		);
		const priorityCounts = visiblePriorities.reduce<Record<string, number>>((counts, priority) => {
			counts[priority] = (counts[priority] ?? 0) + 1;
			return counts;
		}, {});
		const unsupportedPriority = visiblePriorities.find((priority) => !["P1", "P2"].includes(priority));
		if (unsupportedPriority) {
			violations.push(`home:visible-priority:${unsupportedPriority}`);
		}
		if (!visiblePriorities.includes("P2")) {
			violations.push("home:visible-priority-missing-p2");
		}

		const pendingPulse = [...document.querySelectorAll(".global-pulse-item")].find((item) =>
			item.querySelector(".global-pulse-label")?.textContent?.trim() === "待处理",
		);
		const pendingPulseCount = firstNumberFromText(
			pendingPulse?.querySelector(".global-pulse-value")?.textContent,
		);
		const pendingPulseNote = pendingPulse?.querySelector(".global-pulse-note")?.textContent ?? "";
		const pulseP1Count = /P1\s*(\d+)/.exec(pendingPulseNote)?.[1];
		const pulseP2Count = /P2\s*(\d+)/.exec(pendingPulseNote)?.[1];
		if (priorityQueueCount !== undefined && pendingPulseCount !== priorityQueueCount) {
			violations.push(`home:pending-count:${pendingPulseCount ?? "missing"}:${priorityQueueCount}`);
		}
		if (pulseP1Count !== String(priorityCounts.P1 ?? 0)) {
			violations.push(`home:pending-p1:${pulseP1Count ?? "missing"}:${priorityCounts.P1 ?? 0}`);
		}
		if (pulseP2Count !== String(priorityCounts.P2 ?? 0)) {
			violations.push(`home:pending-p2:${pulseP2Count ?? "missing"}:${priorityCounts.P2 ?? 0}`);
		}

		const activityStream = document.querySelector('[data-contract-slot="recent-signals"]');
		const [decisionCard] = decisionCards;
		const nodeApi = document.defaultView?.Node;
		if (
			activityStream &&
			decisionCard &&
			nodeApi &&
			activityStream.compareDocumentPosition(decisionCard) & nodeApi.DOCUMENT_POSITION_FOLLOWING
		) {
			violations.push("home:activity-before-decision");
		}

		const dataHealth = document.querySelector('[data-contract-slot="data-health"]');
		const normalHealthItems = [
			...(dataHealth?.querySelectorAll(".health-item") ?? []),
		].filter((item) => item.querySelector(".health-dot.healthy, .health-status.ok"));
		if (normalHealthItems.length > 0) {
			violations.push(`home:data-health-normal-items:${normalHealthItems.length}`);
		}

		expect(violations).toEqual([]);
	});

	it("binds primary answer validation to visible text and marked actionable controls", () => {
		const getRegion = (html: string): Element => {
			const region = new JSDOM(html).window.document.querySelector("[data-primary-answer]");
			expect(region).not.toBeNull();
			if (!region) throw new Error("Primary answer fixture did not include a region");
			return region;
		};

		const hiddenTextRegion = getRegion(`
			<section data-primary-answer aria-label="影响范围：测试页面">
				<span data-answer-judgment aria-hidden="true">隐藏判断</span>
				<span data-answer-metric aria-hidden="true">99</span>
				<span data-answer-evidence>可见证据</span>
				<span data-answer-evidence aria-hidden="true">隐藏证据</span>
				<button type="button" data-answer-action>查看</button>
			</section>
		`);

		expect(hasPrimaryAnswerJudgment(hiddenTextRegion)).toBe(false);
		expect(hasPrimaryAnswerMetric(hiddenTextRegion)).toBe(false);
		expect(getPrimaryAnswerEvidenceCount(hiddenTextRegion)).toBe(1);

		const unmarkedActionRegion = getRegion(`
			<section data-primary-answer aria-label="影响范围：测试页面">
				<button type="button">普通按钮</button>
				<label for="overlay-detail" data-answer-action>打开详情</label>
			</section>
		`);

		expect(hasPrimaryAnswerAction(unmarkedActionRegion)).toBe(false);

		const untargetedRoleActionRegion = getRegion(`
			<section data-primary-answer aria-label="影响范围：测试页面">
				<div role="button" tabindex="0" data-answer-action>打开详情</div>
			</section>
		`);

		expect(hasPrimaryAnswerAction(untargetedRoleActionRegion)).toBe(false);

		const unfocusableRoleActionRegion = getRegion(`
			<section data-primary-answer aria-label="影响范围：测试页面">
				<div id="detail-panel">详情</div>
				<div role="button" tabindex="-1" aria-controls="detail-panel" data-answer-action>打开详情</div>
			</section>
		`);

		expect(hasPrimaryAnswerAction(unfocusableRoleActionRegion)).toBe(false);

		const targetedRoleActionRegion = getRegion(`
			<section data-primary-answer aria-label="影响范围：测试页面">
				<div id="detail-panel">详情</div>
				<div role="button" tabindex="0" aria-controls="detail-panel" data-answer-action>打开详情</div>
			</section>
		`);

		expect(hasPrimaryAnswerAction(targetedRoleActionRegion)).toBe(true);

		const hiddenControlsOnlyRegion = getRegion(`
			<section data-primary-answer aria-label="影响范围：测试页面">
				<div id="detail-panel" aria-hidden="true">详情</div>
				<div role="button" tabindex="0" aria-controls="detail-panel" data-answer-action>打开详情</div>
			</section>
		`);

		expect(hasPrimaryAnswerAction(hiddenControlsOnlyRegion)).toBe(false);

		const missingDataTargetRegion = getRegion(`
			<section data-primary-answer aria-label="影响范围：测试页面">
				<div role="button" tabindex="0" data-tab-target="missing-panel" data-answer-action>打开详情</div>
			</section>
		`);

		expect(hasPrimaryAnswerAction(missingDataTargetRegion)).toBe(false);

		const targetedDataTargetRegion = getRegion(`
			<section data-primary-answer aria-label="影响范围：测试页面">
				<div data-tab-panel="detail-panel">详情</div>
				<div role="button" tabindex="0" data-tab-target="detail-panel" data-answer-action>打开详情</div>
			</section>
		`);

		expect(hasPrimaryAnswerAction(targetedDataTargetRegion)).toBe(true);

		const markedActionRegion = getRegion(`
			<section data-primary-answer aria-label="影响范围：测试页面">
				<input id="overlay-detail" type="checkbox">
				<label for="overlay-detail" role="button" tabindex="0" data-answer-action>打开详情</label>
			</section>
		`);

		expect(hasPrimaryAnswerAction(markedActionRegion)).toBe(true);
	});

	it("keeps the Pro Max shared CSS and accessibility baseline machine-checkable", () => {
		const css = readAllLayoutCss();
		const orphanDeclaration = /}\s*\n\s*(appearance|cursor|transition)\s*:/m.exec(css);
		const tokenDefinitions = extractCustomPropertyDefinitions(readTokenCssBundle());
		const tokenReferences = extractCustomPropertyReferences(css);
		const missingTokens = [...tokenReferences]
			.filter((token) => !tokenDefinitions.has(token))
			.sort();
		const violations: string[] = [];

		if (orphanDeclaration) {
			violations.push(`shared-layout:orphan:${orphanDeclaration[1]}`);
		}

		for (const token of missingTokens) {
			violations.push(`shared-layout:missing-token:${token}`);
		}

		if (css.includes("oklch(from")) {
			violations.push("shared-layout:oklch-from");
		}

		if (!css.includes("@media (prefers-reduced-motion: reduce)")) {
			violations.push("shared-layout:reduced-motion");
		}

		for (const page of activePages()) {
			const html = readPrototypeHtml(page);
			const document = readPrototypeDocument(page);

			if (!document.querySelector("title")?.textContent?.trim()) {
				violations.push(`${page.id}:title`);
			}
			if (!document.querySelector('meta[name="viewport"]')) {
				violations.push(`${page.id}:viewport`);
			}
			if (!document.querySelector(".skip-link")) {
				violations.push(`${page.id}:skip-link`);
			}
			if (!document.querySelector("h1, h2, h3, [role='heading'], .header-title")) {
				violations.push(`${page.id}:heading`);
			}
			for (const selector of [".proto-nav", "#default-view", "#states-gallery", "#overlays-gallery"]) {
				if (!document.querySelector(selector)) {
					violations.push(`${page.id}:${selector}`);
				}
			}
			for (const button of document.querySelectorAll('[role="button"]')) {
				const hasAccessibleName =
					Boolean(button.getAttribute("aria-label")?.trim()) ||
					Boolean(button.getAttribute("aria-labelledby")?.trim()) ||
					Boolean(button.textContent?.trim());
				if (!hasAccessibleName) {
					violations.push(`${page.id}:role-button-name`);
				}
			}
			if (html.includes("oklch(from")) {
				violations.push(`${page.id}:oklch-from`);
			}
		}

		expect(violations).toEqual([]);
	});

	it("keeps Home custom controls on explicit token focus rings", () => {
		const home = activePageById("home");
		const css = [
			readAllLayoutCss(),
			getStyleBlocks(readPrototypeHtml(home)),
		].join("\n");
		const missingSelectors = homeTokenFocusSelectors.filter(
			(selector) => !hasTokenFocusRule(css, selector),
		);

		expect(missingSelectors).toEqual([]);
	});

	it("keeps shared common controls on the canonical focus outline", () => {
		const css = readAllLayoutCss();
		const missingSelectors = sharedCanonicalFocusSelectors.filter(
			(selector) => !hasCanonicalFocusOutlineRule(css, selector),
		);

		expect(missingSelectors).toEqual([]);
	});

	it("keeps page-local focus-visible colors on the interaction focus ring token", () => {
		const violations = activePages().flatMap((page) => {
			const css = getStyleBlocks(readPrototypeHtml(page));

			return getPrototypeCssRules(page)
				.filter((rule) => /:focus-visible\b/.test(rule.selector))
				.filter((rule) => usesNonCanonicalFocusColor(rule.body))
				.filter((rule) => !/--interaction-focus-ring/.test(rule.body))
				.map((rule) => `${page.id}:${getLineNumber(css, rule.start)}:${rule.selector}`);
		});

		expect(violations).toEqual([]);
	});

	it("keeps task-scoped prototype animations covered by targeted reduced motion", () => {
		const violations: string[] = [];
		const alphaCss = getStyleBlocks(readPrototypeHtml(activePageById("alpha-explorer")));
		const alphaReducedMotionCss = getMediaBlocksMatching(
			alphaCss,
			/prefers-reduced-motion\s*:\s*reduce/i,
		).join("\n");
		const signalsCss = getStyleBlocks(readPrototypeHtml(activePageById("signals-inbox")));
		const signalsReducedMotionCss = getMediaBlocksMatching(
			signalsCss,
			/prefers-reduced-motion\s*:\s*reduce/i,
		).join("\n");

		if (/\*\s*\{[^}]*transition-duration/i.test(alphaReducedMotionCss)) {
			violations.push("alpha-explorer:global-reduced-motion-wildcard");
		}

		for (const family of signalsInboxReducedMotionFamilies) {
			if (!signalsReducedMotionCss.includes(family)) {
				violations.push(`signals-inbox:reduced-motion:${family}`);
			}
		}

		expect(violations).toEqual([]);
	});

	it("keeps task-scoped motion declarations on duration and easing tokens", () => {
		const hardcodedDuration = /\b(?:100ms|150ms|180ms|200ms|300ms|600ms|0\.12s|0\.2s|0\.25s|0\.3s|0\.4s|0\.6s)\b/;
		const rawEasing = /\b(?:ease|ease-in-out|ease-out)\b|cubic-bezier\(\s*0\.4\s*,\s*0\s*,\s*0\.2\s*,\s*1\s*\)/;
		const violations = motionRemediationPageIds.flatMap((pageId) => {
			const page = activePageById(pageId);
			const css = getStyleBlocks(readPrototypeHtml(page));

			return getMotionDeclarations(css).flatMap(({ line, property, value }) => {
				const declarationViolations: string[] = [];
				if (hardcodedDuration.test(value)) {
					declarationViolations.push(`${page.id}:${line}:${property}:duration:${value}`);
				}
				if (rawEasing.test(value)) {
					declarationViolations.push(`${page.id}:${line}:${property}:easing:${value}`);
				}

				return declarationViolations;
			});
		});

		expect(violations).toEqual([]);
	});

	it("keeps layout property transitions categorized and tokenized", () => {
		const violations: string[] = [];

		for (const page of activePages()) {
			const css = getStyleBlocks(readPrototypeHtml(page));
			for (const { line, value } of getMotionDeclarations(css).filter(
				(declaration) => declaration.property === "transition",
			)) {
				for (const item of getTransitionItems(value)) {
					if (/^(?:height|max-height)\b/i.test(item)) {
						violations.push(`${page.id}:${line}:layout-height:${item}`);
					}
					if (/^width\b/i.test(item) && !/^width\s+var\(--motion-duration-[a-z-]+\)/i.test(item)) {
						violations.push(`${page.id}:${line}:layout-width-duration:${item}`);
					}
				}
			}
		}

		expect(violations).toEqual([]);
	});

	it("makes the global command entry discoverable without masquerading as local search", () => {
		const violations: string[] = [];

		for (const page of activePages()) {
			const document = readPrototypeDocument(page);
			const command = document.querySelector('.shell-header [data-shell-utility="command"]');

			if (!command) {
				violations.push(`${page.id}:missing-command`);
				continue;
			}
			if (command.getAttribute("data-command-scope") !== "global") {
				violations.push(`${page.id}:command-scope`);
			}

			const commandLabel = `${command.getAttribute("title") ?? ""} ${
				command.getAttribute("aria-label") ?? ""
			}`;
			if (!/ctrl\s*\+\s*k/i.test(commandLabel)) {
				violations.push(`${page.id}:command-shortcut`);
			}
			if (!command.classList.contains("header-command-trigger")) {
				violations.push(`${page.id}:command-trigger-class`);
			}
			if (!command.querySelector(".command-prompt, .command-caret")) {
				violations.push(`${page.id}:command-prompt`);
			}
			if (!command.querySelector(".command-query")) {
				violations.push(`${page.id}:command-query`);
			}
			if (!command.querySelector("kbd")) {
				violations.push(`${page.id}:command-kbd`);
			}

			for (const input of document.querySelectorAll("input.filter-search, input[type='search']")) {
				if (!input.getAttribute("data-local-search")) {
					violations.push(`${page.id}:local-search-scope`);
				}
				if (input.closest(".shell-header")) {
					violations.push(`${page.id}:header-search`);
				}
			}
		}

		expect(violations).toEqual([]);
	});

	it("does not leave empty legacy header action wrappers", () => {
		const violations: string[] = [];

		for (const page of readManifest().pages.filter(isActiveRoutePrototype)) {
			const document = readPrototypeDocument(page);
			for (const wrapper of document.querySelectorAll(
				[
					".shell-header .header-actions",
					".shell-header .header-utility-bar",
					".shell-header .header-btn-group",
					".shell-header .header-btn-group-left",
					".shell-header .header-btn-group-right",
				].join(", "),
			)) {
				if (wrapper.hasAttribute("data-header-utility-bar")) continue;
				if (wrapper.textContent?.trim()) continue;
				if (wrapper.querySelectorAll("*").length > 0) continue;

				violations.push(`${page.id}:${wrapper.getAttribute("class") ?? "unknown"}`);
			}
		}

		expect(violations).toEqual([]);
	});

	it("keeps theme and density as direct header icon toggles without popovers", () => {
		const violations: string[] = [];

		for (const page of readManifest().pages.filter(isActiveRoutePrototype)) {
			const document = readPrototypeDocument(page);

			if (document.querySelector("[data-view-preferences-menu], [data-view-preferences-trigger]")) {
				violations.push(`${page.id}:popover`);
			}
			if (!document.querySelector('.shell-header #theme-toggle[data-shell-utility="theme"]')) {
				violations.push(`${page.id}:theme-toggle`);
			}
			if (!document.querySelector('.shell-header #density-toggle[data-shell-utility="density"]')) {
				violations.push(`${page.id}:density-toggle`);
			}
			if (document.querySelector(".shell-rail #density-toggle, .shell-rail #theme-toggle")) {
				violations.push(`${page.id}:rail-toggle`);
			}
		}

		expect(violations).toEqual([]);
	});

	it("keeps header titles language-consistent and undecorated", () => {
		const violations: string[] = [];

		for (const page of readManifest().pages.filter(isActiveRoutePrototype)) {
			const document = readPrototypeDocument(page);

			for (const title of document.querySelectorAll(".shell-header .header-title")) {
				const text = title.textContent?.trim() ?? "";
				if (/[A-Za-z]{2,}/.test(removeApprovedHeaderTitleTerms(text))) {
					violations.push(`${page.id}:title:${text}`);
				}
			}
		}

		expect(violations).toEqual([]);
	});

	it("keeps density and theme affordances out of loose header controls", () => {
		const violations: string[] = [];

		for (const page of readManifest().pages.filter(isActiveRoutePrototype)) {
			const document = readPrototypeDocument(page);
			for (const element of document.querySelectorAll(".shell-header [title], .shell-header [aria-label]")) {
				if (element.matches("#theme-toggle, #density-toggle")) continue;

				const label = `${element.getAttribute("title") ?? ""} ${
					element.getAttribute("aria-label") ?? ""
				}`;
				if (/\bDensity\b|密度|\bTheme\b|主题/i.test(label)) {
					violations.push(`${page.id}:${label.trim()}`);
				}
			}
		}

		expect(violations).toEqual([]);
	});

	it("marks prototype list search inputs as data-table search controls", () => {
		const violations: string[] = [];

		for (const page of readManifest().pages.filter(isActiveRoutePrototype)) {
			const document = readPrototypeDocument(page);
			for (const input of document.querySelectorAll("input.filter-search")) {
				if (input.getAttribute("data-table-toolbar") !== "search") {
					violations.push(`${page.id}:scope`);
				}

				if (!input.getAttribute("aria-label")) {
					violations.push(`${page.id}:label`);
				}
			}
		}

		expect(violations).toEqual([]);
	});

	it("does not mark pages with overlay ids as overlayStatus none", () => {
		const offenders = readManifest()
			.pages.filter(isActiveRoutePrototype)
			.filter((page) => {
				const html = readPrototypeHtml(page);

				return /id="overlay-[^"]+"/.test(html) && page.landing?.overlayStatus === "none";
			})
			.map((page) => page.id);

		expect(offenders).toEqual([]);
	});

	it("registers every active prototype overlay in page contracts", () => {
		const contractByPrototype = new Map<string, Set<string>>();
		for (const contract of readContracts()) {
			const overlaySelectors = new Set(
				contract.overlays?.map((overlay) => overlay.prototypeSelector) ?? [],
			);
			contractByPrototype.set(contract.prototypeRef, overlaySelectors);

			if (contract.nextPrototypeRef) {
				const nextOverlaySelectors = new Set(
					(contract.nextOverlays ?? contract.overlays)?.map((overlay) => overlay.prototypeSelector) ?? [],
				);
				contractByPrototype.set(contract.nextPrototypeRef, nextOverlaySelectors);
			}
		}

		const missing: string[] = [];
		for (const page of readManifest().pages) {
			if (!isActiveRoutePrototype(page)) continue;

			const selectors =
				contractByPrototype.get(`docs/designs/specs/prototypes/${page.file}`) ?? new Set();

			for (const id of getOverlayIds(readPrototypeHtml(page))) {
				if (![...selectors].some((selector) => selectorReferencesOverlayId(selector, id))) {
					missing.push(`${page.id}:${id}`);
				}
			}
		}

		expect(missing).toEqual([]);
	});

	it("resolves every active prototype contract overlay selector in the canonical prototype DOM", () => {
		const activePrototypeRefs = new Set(
			readManifest()
				.pages.filter(isActiveRoutePrototype)
				.map((page) => `docs/designs/specs/prototypes/${page.file}`),
		);
		const failures: string[] = [];

		for (const contract of readContracts()) {
			if (!activePrototypeRefs.has(contract.prototypeRef)) continue;

			const page = readManifest().pages.find(
				(manifestPage) => `docs/designs/specs/prototypes/${manifestPage.file}` === contract.prototypeRef,
			);
			if (!page) continue;

			for (const overlay of contract.overlays ?? []) {
				if (!readPrototypeDocument(page).querySelector(overlay.prototypeSelector)) {
					failures.push(`${contract.id}:${overlay.id}:${overlay.prototypeSelector}`);
				}
			}
		}

		expect(failures).toEqual([]);
	});

	it("matches known shell family decisions from blueprints", () => {
		const expectedShellFamilies = new Map([
			["cross-market", "radar"],
			["agent-console", "studio"],
			["experiment-list", "catalog"],
		]);
		const manifest = readManifest();
		const contractById = new Map(readContracts().map((contract) => [contract.id, contract.shellFamily]));

		for (const [id, shellFamily] of expectedShellFamilies) {
			expect(manifest.pages.find((page) => page.id === id)?.shellFamily).toBe(shellFamily);
			expect(contractById.get(id)).toBe(shellFamily);
		}
	});

	it("marks overlay gallery specimens with data-overlay-ref", () => {
		const missing: string[] = [];

		for (const page of readManifest().pages) {
			if (!isActiveRoutePrototype(page)) continue;

			const html = readPrototypeHtml(page);
			const refs = new Set(
				[...html.matchAll(/data-overlay-ref="([^"]+)"/g)].map((match) => match[1]),
			);

			for (const id of getOverlayIds(html)) {
				if (!refs.has(id)) missing.push(`${page.id}:${id}`);
			}
		}

		expect(missing).toEqual([]);
	});

	it("does not introduce legacy overlay surface class names in active prototypes", () => {
		const legacyHits: string[] = [];

		for (const page of readManifest().pages) {
			if (!isActiveRoutePrototype(page)) continue;

			const html = readPrototypeHtml(page);
			for (const legacy of ["drawer-sheet", "modal-sheet", "overlay-sheet", "overlay-drawer"]) {
				if (html.includes(legacy)) legacyHits.push(`${page.id}:${legacy}`);
			}
		}

		expect(legacyHits).toEqual([]);
	});

	it("keeps prototype zones separated and singular", () => {
		const violations: string[] = [];

		for (const page of activePages()) {

			const html = readPrototypeHtml(page);
			for (const zoneId of ["default-view", "states-gallery", "overlays-gallery"]) {
				const count = countMatches(html, new RegExp(`id="${zoneId}"`, "g"));
				if (count !== 1) violations.push(`${page.id}:${zoneId}:${count}`);
			}

			const defaultView = getElementBodyById(html, "default-view");
			const statesGallery = getElementBodyById(html, "states-gallery");
			const overlaysGallery = getElementBodyById(html, "overlays-gallery");
			if (defaultView.includes("gallery-card")) violations.push(`${page.id}:default-gallery-card`);
			if (statesGallery.includes("overlay-surface")) violations.push(`${page.id}:states-overlay-surface`);
			if (overlaysGallery.includes("data-contract-slot")) {
				violations.push(`${page.id}:overlays-contract-slot`);
			}
		}

		expect(violations).toEqual([]);
	});

	it("exposes the bottom tray contract on studio and operational prototypes", () => {
		const violations: string[] = [];

		for (const page of activePages().filter((prototype) => bottomTrayPages.includes(prototype.id))) {
			const document = readPrototypeDocument(page);
			const tray = document.querySelector("[data-bottom-tray]");

			if (!tray) {
				violations.push(`${page.id}:missing-tray`);
				continue;
			}

			const state = tray.getAttribute("data-bottom-tray-state");
			if (!state || !["collapsed", "peek", "expanded"].includes(state)) {
				violations.push(`${page.id}:state:${state ?? "missing"}`);
			}

			const toggle = tray.querySelector("[data-bottom-tray-toggle]");
			const content = tray.querySelector("[data-bottom-tray-content]");
			if (!toggle?.getAttribute("aria-controls")) {
				violations.push(`${page.id}:toggle-controls`);
			}
			if (!content?.id) {
				violations.push(`${page.id}:content-id`);
			}
			if (toggle?.getAttribute("aria-controls") !== content?.id) {
				violations.push(`${page.id}:toggle-target`);
			}
		}

		expect(violations).toEqual([]);
	});

	it("requires non-color data visualization encoding on analytical heatmaps and matrices", () => {
		const violations: string[] = [];

		for (const page of activePages().filter((prototype) => dataVizContractPages.includes(prototype.id))) {
			const document = readPrototypeDocument(page);
			const defaultView = document.querySelector("#default-view");
			if (!defaultView) {
				violations.push(`${page.id}:missing-default-view`);
				continue;
			}

			if (!defaultView.querySelector("[data-viz-legend]")) {
				violations.push(`${page.id}:legend`);
			}
			if (!defaultView.querySelector('[data-viz-sign="positive"], [data-viz-sign="negative"], [data-viz-sign="neutral"]')) {
				violations.push(`${page.id}:sign`);
			}
			if (!defaultView.querySelector("[data-viz-threshold-label]")) {
				violations.push(`${page.id}:threshold`);
			}
			if (!defaultView.querySelector(".viz-cell-strong, .viz-cell-selected, [data-viz-cell-strength='strong'], [data-viz-cell-selected]")) {
				violations.push(`${page.id}:cell-affordance`);
			}
		}

		expect(violations).toEqual([]);
	});

	it("keeps A Shares stock heatmap labels readable and out of tiny-text escape hatches", () => {
		const page = activePageById("a-shares");
		const rules = getPrototypeCssRules(page);
		const violations: string[] = [];
		const dataLabelRules = rules.filter((rule) =>
			rule.selectors.some((selector) =>
				/\.map-view-heatmap|\.heatmap-cell|\.hm-(?:name|change|vol|sign)/.test(selector),
			),
		);
		const hmNameRules = dataLabelRules.filter((rule) =>
			rule.selectors.some((selector) => selector.includes(".hm-name")),
		);

		if (hmNameRules.length === 0) {
			violations.push("a-shares:heatmap-name-font-size:missing");
		}

		for (const rule of dataLabelRules) {
			for (const fontSize of getCssFontSizeValues(rule.body)) {
				const minimumPx = parseFontSizeMinimumPx(fontSize);
				if (minimumPx !== undefined && minimumPx < 10) {
					violations.push(`a-shares:${rule.selector}:font-size:${fontSize}`);
				}
			}
		}

		for (const rule of hmNameRules) {
			const fontSizes = getCssFontSizeValues(rule.body);
			if (fontSizes.length === 0) continue;

			for (const fontSize of fontSizes) {
				const minimumPx = parseFontSizeMinimumPx(fontSize);
				if (minimumPx === undefined || minimumPx < 10) {
					violations.push(`a-shares:${rule.selector}:hm-name-min:${fontSize}`);
				}
			}
		}

		expect(violations).toEqual([]);
	});

	it("requires A Shares heatmap cells to encode direction beyond color", () => {
		const page = activePageById("a-shares");
		const document = readPrototypeDocument(page);
		const violations: string[] = [];
		const cells = [
			...document.querySelectorAll<HTMLElement>(
				'.map-view-heatmap .heatmap-cell[data-direction="up"], .map-view-heatmap .heatmap-cell[data-direction="down"]',
			),
		];

		if (cells.length === 0) {
			violations.push("a-shares:heatmap-cells:missing");
		}

		for (const [index, cell] of cells.entries()) {
			const direction = cell.getAttribute("data-direction");
			const expectedSign = direction === "up" ? "▲" : "▼";
			const expectedAria = direction === "up" ? "涨幅" : "跌幅";
			const sign = cell.querySelector<HTMLElement>(':scope > .hm-sign[aria-hidden="true"]');
			const label = cell.getAttribute("aria-label") ?? "";

			if (sign?.textContent?.trim() !== expectedSign) {
				violations.push(`a-shares:heatmap-cell:${index + 1}:sign:${direction ?? "missing"}`);
			}
			if (!label.includes(expectedAria)) {
				violations.push(`a-shares:heatmap-cell:${index + 1}:aria:${direction ?? "missing"}`);
			}
		}

		expect(violations).toEqual([]);
	});

	it("keeps important market, risk, and stale states readable without relying on color alone", () => {
		const violations: string[] = [];
		const crossMarket = readPrototypeDocument(activePageById("cross-market"));
		const riskCenter = readPrototypeDocument(activePageById("risk-center"));
		const marketsIntelligence = readPrototypeDocument(activePageById("markets-intelligence"));
		const correlationCells = [
			...crossMarket.querySelectorAll<HTMLElement>("#default-view .corr-cell[data-corr]"),
		];
		const riskWarnings = [
			...riskCenter.querySelectorAll<HTMLElement>("#default-view .risk-strip-value.warn, #default-view .stress-tag.fail"),
		];
		const staleStates = [
			...marketsIntelligence.querySelectorAll<HTMLElement>(".state-variant-content[data-state='stale']"),
		];
		const riskMarkerPattern = /!|突破|接近|critical|warn|severity|P[0-3]/i;
		const staleMarkerPattern = /stale|降级|延迟|过期|不是最新|非最新|可能|最后更新|更新于\s*\d+\s*分钟前|基于\s*\d+\s*分钟前/i;

		if (correlationCells.length === 0) {
			violations.push("cross-market:correlation-cells:missing");
		}
		for (const [index, cell] of correlationCells.entries()) {
			const text = cell.textContent?.replace(/\s+/g, " ").trim() ?? "";
			if (!/^[+-]/.test(text)) {
				violations.push(`cross-market:correlation-cell:${index + 1}:missing-sign`);
			}
		}

		if (riskWarnings.length === 0) {
			violations.push("risk-center:warning-states:missing");
		}
		for (const [index, warning] of riskWarnings.entries()) {
			const text = warning.textContent?.replace(/\s+/g, " ").trim() ?? "";
			if (!riskMarkerPattern.test(text)) {
				violations.push(`risk-center:warning-state:${index + 1}:missing-marker`);
			}
		}

		if (staleStates.length === 0) {
			violations.push("markets-intelligence:stale-states:missing");
		}
		for (const [index, state] of staleStates.entries()) {
			const text = state.textContent?.replace(/\s+/g, " ").trim() ?? "";
			if (!staleMarkerPattern.test(text)) {
				violations.push(`markets-intelligence:stale-state:${index + 1}:missing-marker`);
			}
		}

		expect(violations).toEqual([]);
	});

	it("uses a page-local light map scale for A Shares instead of reusing the dark heatmap scale", () => {
		const page = activePageById("a-shares");
		const css = stripCssComments(getStyleBlocks(readPrototypeHtml(page)));
		const rules = readTopLevelCssRules(css);
		const lightMapRule = rules.find((rule) =>
			rule.selectors.some((selector) =>
				/\[data-theme=["']light["']\]\s+\.map-container/.test(selector),
			),
		);
		const violations: string[] = [];

		if (!lightMapRule) {
			violations.push("a-shares:light-map-scale:missing");
		} else {
			for (const token of [
				"--heat-up-1",
				"--heat-up-2",
				"--heat-up-3",
				"--heat-up-4",
				"--heat-down-1",
				"--heat-down-2",
				"--heat-down-3",
				"--heat-down-4",
				"--heat-up-line-1",
				"--heat-up-line-2",
				"--heat-up-line-3",
				"--heat-up-line-4",
				"--heat-down-line-1",
				"--heat-down-line-2",
				"--heat-down-line-3",
				"--heat-down-line-4",
			]) {
				if (!hasDeclaration(lightMapRule.body, token, /var\(\s*--map-light-(?:up|down)-(?:edge-)?[1-4]\s*\)/)) {
					violations.push(`a-shares:light-map-scale:${token}`);
				}
			}
		}

		for (const token of [
			"--map-light-up-1",
			"--map-light-up-2",
			"--map-light-up-3",
			"--map-light-up-4",
			"--map-light-down-1",
			"--map-light-down-2",
			"--map-light-down-3",
			"--map-light-down-4",
			"--map-light-up-edge-1",
			"--map-light-up-edge-2",
			"--map-light-up-edge-3",
			"--map-light-up-edge-4",
			"--map-light-down-edge-1",
			"--map-light-down-edge-2",
			"--map-light-down-edge-3",
			"--map-light-down-edge-4",
		]) {
			if (!css.includes(`${token}:`)) {
				violations.push(`a-shares:light-token:${token}`);
			}
		}

		expect(violations).toEqual([]);
	});

	it("keeps catalog selected feedback, batch actions, and sticky summaries explicit", () => {
		const violations: string[] = [];

		for (const page of activePages().filter((prototype) => catalogContractPages.includes(prototype.id))) {
			const document = readPrototypeDocument(page);
			const defaultView = document.querySelector("#default-view");
			if (!defaultView) {
				violations.push(`${page.id}:missing-default-view`);
				continue;
			}

			if (!defaultView.querySelector(".row-selection-marker, .selection-mark, [data-row-selection-marker]")) {
				violations.push(`${page.id}:selection-marker`);
			}
			if (
				defaultView.querySelector('input[type="checkbox"]') &&
				!defaultView.querySelector("[data-bulk-action-bar], [data-batch-action-bar]")
			) {
				violations.push(`${page.id}:batch-action-bar`);
			}
			if (!defaultView.querySelector("[data-detail-sticky-summary]")) {
				violations.push(`${page.id}:sticky-summary`);
			}
			if (/delete|删除|撤销|danger/i.test(defaultView.textContent ?? "") && !defaultView.querySelector("[data-danger-confirmation]")) {
				violations.push(`${page.id}:danger-confirmation`);
			}
		}

		expect(violations).toEqual([]);
	});

	it("keeps catalog subtype summary strips task-specific", () => {
		const violations: string[] = [];

		for (const [pageId, requirements] of Object.entries(catalogSubtypeSummaryRequirements)) {
			const document = readPrototypeDocument(activePageById(pageId));
			const defaultView = document.querySelector("#default-view");
			const summary = defaultView?.querySelector("[data-primary-answer], [data-primary-answer-equivalent]");
			if (!summary) {
				violations.push(`${pageId}:summary:missing`);
				continue;
			}

			const summaryText = getReadablePrimaryText(summary);
			for (const requirement of requirements) {
				if (!requirement.pattern.test(summaryText)) {
					violations.push(`${pageId}:summary-label:${requirement.label}`);
				}
			}
		}

		expect(violations).toEqual([]);
	});

	it("keeps catalog subtype task actions semantically aligned", () => {
		const violations: string[] = [];
		const watchlistDocument = readPrototypeDocument(activePageById("watchlist"));
		const watchlistView = watchlistDocument.querySelector("#default-view");
		const watchlistSummary = watchlistView?.querySelector(".watchlist-summary");
		const watchlistTrigger = watchlistSummary?.querySelector(".watchlist-summary-item");
		const selectedWatchlistRow = watchlistView?.querySelector(".data-table tr.row.selected");
		const selectedSignal = selectedWatchlistRow?.querySelector(".signal-pill")?.textContent ?? "";
		const selectedDirection = /(买入|卖出|观望)/.exec(selectedSignal)?.[1];
		const detailDirection = watchlistView?.querySelector(".detail-direction")?.textContent ?? "";
		const actionLabel =
			watchlistSummary?.querySelector("[data-answer-action]")?.getAttribute("aria-label") ?? "";

		if (!selectedDirection) {
			violations.push("watchlist:selected-direction");
		} else {
			const triggerText = getReadablePrimaryText(watchlistTrigger ?? null);
			if (!triggerText.includes(selectedDirection)) {
				violations.push("watchlist:summary-direction");
			}
			if (!detailDirection.includes(selectedDirection)) {
				violations.push("watchlist:detail-direction");
			}
		}
		if (!/下一步|发送到研究|研究/.test(actionLabel) || /最强标的/.test(actionLabel)) {
			violations.push("watchlist:action-aria-label");
		}

		const backtestDocument = readPrototypeDocument(activePageById("backtest-list"));
		const blockedBacktestRows = [...backtestDocument.querySelectorAll(".data-table tr.row")].filter((row) =>
			/运行中|失败|排队中/.test(row.querySelector(".bt-status")?.textContent ?? ""),
		);
		for (const row of blockedBacktestRows) {
			const rowName = row.querySelector(".cell-ticker")?.textContent?.trim() ?? "unknown";
			const rowActions = row.querySelector(".row-actions");
			const hasCompareAction =
				Boolean(rowActions?.querySelector('label[for="overlay-backtest-compare"]')) ||
				/对比/.test(rowActions?.textContent ?? "");
			if (hasCompareAction) {
				violations.push(`backtest-list:blocked-compare:${rowName}`);
			}
		}
		const backtestHtml = readPrototypeHtml(activePageById("backtest-list"));
		if (!/\.row-action\[aria-disabled="true"\]\s*\{[^}]*cursor:\s*default;[^}]*pointer-events:\s*none;/s.test(backtestHtml)) {
			violations.push("backtest-list:disabled-action-style");
		}

		const pagePatternLibrary = readFileSync(pagePatternLibrarySpec, "utf8");
		if (!/\| Backtest Comparison Ledger \| `\/research\/backtest` \|/.test(pagePatternLibrary)) {
			violations.push("pattern-library:backtest-route");
		}
		if (pagePatternLibrary.includes("`/research/backtests`")) {
			violations.push("pattern-library:backtest-route-plural");
		}

		expect(violations).toEqual([]);
	});

	it("documents high-risk actions with impact, confirmation, cancel, recovery, and non-color danger cues", () => {
		const violations: string[] = [];

		for (const page of activePages().filter((prototype) => highRiskActionPages.includes(prototype.id))) {
			const document = readPrototypeDocument(page);
			const defaultView = document.querySelector("#default-view");
			const action = defaultView?.querySelector("[data-danger-action], [data-high-risk-action]");

			if (!defaultView || !action) {
				violations.push(`${page.id}:danger-action`);
				continue;
			}

			const container = action.closest("[data-danger-confirmation], [data-high-risk-confirmation]");
			if (!container) {
				violations.push(`${page.id}:confirmation-container`);
				continue;
			}
			for (const selector of [
				"[data-impact-summary]",
				"[data-confirm-control]",
				"[data-cancel-control]",
				"[data-recovery-hint]",
				"[data-danger-marker]",
			]) {
				if (!container.querySelector(selector)) {
					violations.push(`${page.id}:${selector}`);
				}
			}
		}

		expect(violations).toEqual([]);
	});

	it("keeps page pattern library section numbering unique", () => {
		const headings = readFileSync(pagePatternLibrarySpec, "utf8")
			.split("\n")
			.map((line) => /^###\s+(\d+\.\d+)\s+/.exec(line)?.[1])
			.filter((section): section is string => Boolean(section));
		const seen = new Set<string>();
		const duplicates = headings.filter((section) => {
			if (seen.has(section)) return true;
			seen.add(section);
			return false;
		});

		expect(duplicates).toEqual([]);
	});

	it("documents the Edition v1 9-step typography scale as current token truth", () => {
		const spec = readFileSync(tokenStabilizationSpec, "utf8");
		const deprecatedTokenClaims = [
			/--font-size-11[^。\n]*(?:deprecated|forbidden|禁止|废弃)/i,
			/--font-size-18[^。\n]*(?:deprecated|forbidden|禁止|废弃)/i,
			/--font-size-20[^。\n]*(?:deprecated|forbidden|禁止|废弃)/i,
		];

		for (const claim of deprecatedTokenClaims) {
			expect(spec).not.toMatch(claim);
		}

		for (const token of [
			"--font-size-10",
			"--font-size-11",
			"--font-size-12",
			"--font-size-13",
			"--font-size-14",
			"--font-size-16",
			"--font-size-18",
			"--font-size-20",
			"--font-size-24",
		]) {
			expect(spec).toContain(token);
		}
	});

	it("keeps DESIGN approval for the 11px tight-context token", () => {
		const spec = readFileSync(designSpec, "utf8");

		expect(spec).toContain("--font-size-11");
		expect(spec).toMatch(/--font-size-11[\s\S]*?Tight contexts/);
	});

	it("flags 11px descendants inside interactive target ancestors", () => {
		const document = new JSDOM(`
			<button type="button"><span class="dense-caption">执行</span></button>
			<div role="tab"><span class="sort-caption">排序</span></div>
		`).window.document;
		const rule: CssRule = {
			selector: ".dense-caption, .sort-caption",
			selectors: [".dense-caption", ".sort-caption"],
			body: "font-size: var(--font-size-11);",
			start: 0,
			end: 0,
		};

		const violations = rule.selectors.filter((selector) =>
			hasOperationalElevenPxUsage(document, rule, selector, []),
		);

		expect(violations).toEqual([".dense-caption", ".sort-caption"]);
	});

	it("flags 11px descendants inside header-like class ancestors", () => {
		const document = new JSDOM(`
			<div class="activity-header"><span class="subtitle">最近运行</span></div>
		`).window.document;
		const rule: CssRule = {
			selector: ".subtitle",
			selectors: [".subtitle"],
			body: "font-size: var(--font-size-11);",
			start: 0,
			end: 0,
		};

		expect(hasOperationalElevenPxUsage(document, rule, ".subtitle", [])).toBe(true);
	});

	it("flags 11px descendants of pointer selectors even without DOM matches", () => {
		const document = new JSDOM("").window.document;
		const rule: CssRule = {
			selector: ".pointer-summary .summary-count",
			selectors: [".pointer-summary .summary-count"],
			body: "font-size: var(--font-size-11);",
			start: 0,
			end: 0,
		};

		expect(
			hasOperationalElevenPxUsage(document, rule, ".pointer-summary .summary-count", [
				".pointer-summary",
			]),
		).toBe(true);
	});

	it("keeps 11px typography out of operational selectors", () => {
		const pageViolations = readManifest()
			.pages.filter(isActiveRoutePrototype)
			.flatMap((page) => {
				const document = readPrototypeDocument(page);
				const rules = getPrototypeCssRules(page);
				const pointerSelectors = rules
					.filter((rule) => hasCursorPointer(rule.body))
					.flatMap((rule) => rule.selectors);

				return rules
					.filter((rule) => usesFontSizeToken(rule.body, "--font-size-11"))
					.flatMap((rule) =>
						rule.selectors
							.filter((selector) =>
								hasOperationalElevenPxUsage(document, rule, selector, pointerSelectors),
							)
							.map(
								(selector) =>
									`${page.file}:${getLineNumber(readPrototypeHtml(page), rule.start)}:${selector}`,
							),
					);
			});

		expect(pageViolations).toEqual([]);
	});

	it("keeps active route prototypes free of negative letter spacing", () => {
		const hasNegativeLetterSpacingValue = (html: string) =>
			[...html.matchAll(/letter-spacing\s*:[^;]+/g)].some((match) =>
				/(^|[\s,(])-\.?\d/.test(match[0]),
			);
		const hits = readManifest()
			.pages.filter(isActiveRoutePrototype)
			.filter((page) => hasNegativeLetterSpacingValue(readPrototypeHtml(page)))
			.map((page) => page.id);

		expect(hits).toEqual([]);
	});

	it("keeps shell family layout definitions in shared prototype CSS", () => {
		const layoutCss = readFileSync(prototypeLayoutCss, "utf8");
		const violations: string[] = [];

		if (!/\.shell-hub\b/.test(layoutCss)) violations.push("layout-shell.css:shell-hub");
		if (!/\.shell-agent\b/.test(layoutCss)) violations.push("layout-shell.css:shell-agent");

		for (const page of activePages()) {
			const style = getStyleBlocks(readPrototypeHtml(page));
			for (const selector of [
				/\.shell-hub\b[^,{]*[,{]/,
				/\.shell-agent\b[^,{]*[,{]/,
			]) {
				if (selector.test(style)) {
					violations.push(`${page.id}:inline-shell-layout`);
					break;
				}
			}
		}

		expect(violations).toEqual([]);
	});

	it("defines responsive viewport hardening rules in shared shell CSS", () => {
		const layoutCss = stripCssComments(readAllLayoutCss());
		const violations: string[] = [];
		const lockedShellSelectors = [".shell", ".shell-v2", ".shell-catalog", ".shell-agent"];
		const media1200 = getMediaBlock(layoutCss, 1200);
		const media1024 = getMediaBlock(layoutCss, 1024);
		const media768 = getMediaBlock(layoutCss, 768);

		for (const selector of lockedShellSelectors) {
			const shellRule = new RegExp(`(?:^|\\n)${selector.replace(".", "\\.")}\\s*\\{([^{}]*)\\}`, "m")
				.exec(layoutCss)?.[1];
			if (!shellRule || !/\b(?:height|min-height)\s*:\s*(?:calc\()?100dvh\b/.test(shellRule)) {
				violations.push(`shared-layout:${selector}:100dvh`);
			}
		}

		if (!hasDeclaration(getSelectorRuleBody(media1200 ?? "", ".shell-catalog"), "--prototype-detail-width", /^min\(300px,\s*28vw\)$/)) {
			violations.push("shared-layout:breakpoint-1200-catalog-detail");
		}
		if (!hasDeclaration(getSelectorRuleBody(media1024 ?? "", ".shell-header [data-header-utility-bar]"), "max-width", /^44vw$/)) {
			violations.push("shared-layout:breakpoint-1024-header-utilities");
		}
		for (const selector of [".shell-catalog", ".shell-studio", ".shell-agent", ".shell-radar"]) {
			if (!hasDeclaration(getSelectorRuleBody(media768 ?? "", selector), "overflow-x", /^auto$/)) {
				violations.push(`shared-layout:breakpoint-768-shell-overflow:${selector}`);
			}
		}

		expect(violations).toEqual([]);
	});

	it("builds prototype gates across professional desktop viewports", () => {
		const defaultViewports = defaultViewportArgs();
		const fullLoopArgs = buildDefaultPrototypeGateArgs("docs/designs/specs/prototypes/page-home.html", "test-results/home");
		const passthroughArgs = buildPassthroughGateArgs(["--prototype", "docs/designs/specs/prototypes/page-home.html"]);
		const equalsPrototypeArgs = buildPassthroughGateArgs(["--prototype=docs/designs/specs/prototypes/page-home.html"]);
		const explicitViewportArgs = buildPassthroughGateArgs([
			"--prototype",
			"docs/designs/specs/prototypes/page-home.html",
			"--viewport",
			"VP-CUSTOM=1440x900",
		]);
		const equalsViewportArgs = buildPassthroughGateArgs([
			"--prototype=docs/designs/specs/prototypes/page-home.html",
			"--viewport=VP-CUSTOM=1440x900",
		]);

		expect(defaultViewports).toEqual([
			"--viewport",
			"VP-STANDARD=1536x1080",
			"--viewport",
			"VP-COMPACT=1366x768",
			"--viewport",
			"VP-NARROW=1200x800",
		]);
		expect(fullLoopArgs).toEqual([
			"--prototype",
			"docs/designs/specs/prototypes/page-home.html",
			...defaultViewports,
			"--out-dir",
			"test-results/home",
		]);
		expect(passthroughArgs).toEqual([
			"--prototype",
			"docs/designs/specs/prototypes/page-home.html",
			...defaultViewports,
		]);
		expect(equalsPrototypeArgs).toEqual([
			"--prototype",
			"docs/designs/specs/prototypes/page-home.html",
			...defaultViewports,
		]);
		expect(explicitViewportArgs).toContain("VP-CUSTOM=1440x900");
		expect(explicitViewportArgs).not.toContain("VP-STANDARD=1536x1080");
		expect(explicitViewportArgs).not.toContain("VP-COMPACT=1366x768");
		expect(explicitViewportArgs).not.toContain("VP-NARROW=1200x800");
		expect(equalsViewportArgs).toEqual([
			"--prototype",
			"docs/designs/specs/prototypes/page-home.html",
			"--viewport",
			"VP-CUSTOM=1440x900",
		]);
	});

	it("keeps page-local shell overflow from overriding 768px responsive overflow", () => {
		const shellSelectorByPage = new Map([
			["a-shares", ".shell-radar"],
			["cross-market", ".shell-radar"],
			["strategy-studio", ".shell-studio"],
		]);
		const violations: string[] = [];

		for (const page of activePages().filter((item) => shellSelectorByPage.has(item.id))) {
			const selector = shellSelectorByPage.get(page.id);
			if (!selector) continue;

			const css = stripCssComments(getStyleBlocks(readPrototypeHtml(page)));
			const selectorRules = readTopLevelCssRules(css)
				.filter((rule) => rule.selectors.includes(selector))
				.filter((rule) => rule.mediaMaxWidth === undefined || rule.mediaMaxWidth === 768);
			const baseRules = selectorRules.filter((rule) => rule.mediaMaxWidth === undefined);
			const lastOverflowRule = selectorRules
				.filter((rule) => /overflow(?:-x)?\s*:/.test(rule.body))
				.at(-1);

			if (!baseRules.some((rule) => hasDeclaration(rule.body, "overflow", /^hidden$/))) {
				violations.push(`${page.id}:${selector}:base-overflow-hidden`);
				continue;
			}
			if (
				lastOverflowRule?.mediaMaxWidth !== 768 ||
				!hasDeclaration(lastOverflowRule.body, "overflow-x", /^auto(?:\s*!important)?$/)
			) {
				violations.push(`${page.id}:${selector}:last-768-overflow-x-auto`);
			}
		}

		expect(violations).toEqual([]);
	});

	it("keeps overlay component grammar in shared prototype CSS", () => {
		const togglesCss = readFileSync(prototypeTogglesCss, "utf8");
		const requiredSharedSelectors = [
			".overlay-header",
			".overlay-title",
			".overlay-body",
			".overlay-actions",
			".overlay-btn",
			".overlay-field",
			".overlay-confirm-box",
			".toast-card",
		];
		const violations: string[] = [];

		for (const selector of requiredSharedSelectors) {
			if (!togglesCss.includes(selector)) {
				violations.push(`prototype-toggles.css:${selector}`);
			}
		}

		for (const page of activePages()) {
			const html = readPrototypeHtml(page);
			const style = getStyleBlocks(html);

			if (/\boverlay-modal\b/.test(html)) {
				violations.push(`${page.id}:overlay-modal`);
			}
			if (/\bmodal-(?:header|title|close|body|actions|btn)\b/.test(html)) {
				violations.push(`${page.id}:modal-grammar`);
			}
			if (
				/\.overlay-(?:header|title|body|actions|btn|field|confirm-box)\b[^,{]*[,{]/.test(
					style,
				)
			) {
				violations.push(`${page.id}:inline-overlay-grammar`);
			}
		}

		expect(violations).toEqual([]);
	});

	it("keeps foundational table and panel styles density-aware in shared CSS", () => {
		const violations: string[] = [];

		for (const page of activePages()) {
			const style = getStyleBlocks(readPrototypeHtml(page));

			if (/(^|\n)\s*\.panel\s*\{/.test(style)) {
				violations.push(`${page.id}:inline-panel-base`);
			}
			if (/(^|\n)\s*\.data-table\s*\{/.test(style)) {
				violations.push(`${page.id}:inline-data-table-base`);
			}
			if (/(^|\n)\s*\.data-table\s+(?:th|td)\b[^,{]*\{[^}]*padding:/s.test(style)) {
				violations.push(`${page.id}:inline-data-table-padding`);
			}
		}

		expect(violations).toEqual([]);
	});

	it("keeps skeleton primitives and modifiers in shared layout CSS only", () => {
		const layoutCss = readAllLayoutCss();
		const togglesCss = readFileSync(prototypeTogglesCss, "utf8");
		const requiredSharedSelectors = [
			".skeleton",
			".skeleton-row",
			".skeleton-text",
			".skeleton-text-sm",
			".skeleton-heading",
			".skeleton-badge",
			".skeleton-chart",
			".skeleton-bar",
			".skeleton-bar-md",
			".skeleton--block",
			".skeleton--card",
			".skeleton--w60",
			".skeleton--w64",
			".skeleton--w72",
			".skeleton--w86",
			".skeleton--w94",
			".skeleton--width-60",
		];
		const violations = requiredSharedSelectors
			.filter((selector) => !getSelectorRuleBody(layoutCss, selector))
			.map((selector) => `shared-layout-missing:${selector}`);
		const canonicalPrimitiveSelectors = [
			".skeleton",
			".skeleton-row",
			".skeleton-text",
			".skeleton-text-sm",
			".skeleton-heading",
			".skeleton-badge",
			".skeleton-chart",
			".skeleton-bar",
		];
		for (const selector of canonicalPrimitiveSelectors) {
			if (getSelectorRuleBody(togglesCss, selector)) {
				violations.push(`prototype-toggles-duplicates:${selector}`);
			}
		}

		for (const selector of requiredSharedSelectors) {
			const owners = readLayoutCssSources().flatMap((source) =>
				readTopLevelCssRules(stripCssComments(source.css))
					.filter((rule) => rule.selectors.includes(selector))
					.map((rule) => `${source.label}:${getLineNumber(source.css, rule.start)}`),
			);
			if (owners.length > 1) {
				violations.push(`shared-layout-duplicates:${selector}:${owners.join(",")}`);
			}
		}

		for (const page of activePages()) {
			const style = getStyleBlocks(readPrototypeHtml(page));
			const css = stripCssComments(style);

			for (const rule of readTopLevelCssRules(css)) {
				const hasPageLocalSkeletonDefinition = rule.selectors.some((selector) =>
					/^\.skeleton(?:\b|[-_a-z0-9])/i.test(selector),
				);
				if (hasPageLocalSkeletonDefinition) {
					violations.push(`${page.id}:${getLineNumber(css, rule.start)}:${rule.selector}`);
				}
			}
		}

		expect(violations).toEqual([]);
	});

	it("keeps page-local skeleton dimension helpers in shared CSS", () => {
		const violations: string[] = [];
		const dimensionDeclarationPattern =
			/(?:^|;)\s*(?:width|height|border-radius|--(?:iv-)?sk-[a-z0-9-]+)\s*:/i;
		const dimensionHelperSelectorPattern =
			/(?:^|[\s>+~,(])\.(?:skeleton(?:\b|[-_a-z0-9])|iv-sk(?:eleton)?[-_a-z0-9]*|sk-\d|sk-(?:text|w)-|skel-(?:badge|text|heading|page-btn|error-icon|w-|h-|h\d))/i;
		const fixtureCss = stripCssComments(`
			.scope .skeleton-bar { height: 32px; }
			.gallery-card .skeleton-text { width: 80px; }
			@media (prefers-reduced-motion: reduce) {
				.skeleton, .task-item.running { animation: none !important; }
			}
		`);
		const fixtureViolations: string[] = [];

		for (const rule of readTopLevelCssRules(fixtureCss)) {
			if (!dimensionDeclarationPattern.test(rule.body)) continue;
			const hasPageLocalDimensionHelper = rule.selectors.some((selector) =>
				dimensionHelperSelectorPattern.test(selector),
			);
			if (hasPageLocalDimensionHelper) {
				fixtureViolations.push(`fixture:${rule.selector}`);
			}
		}

		expect(fixtureViolations).toEqual([
			"fixture:.scope .skeleton-bar",
			"fixture:.gallery-card .skeleton-text",
		]);

		for (const page of activePages()) {
			const style = getStyleBlocks(readPrototypeHtml(page));
			const css = stripCssComments(style);

			for (const rule of readTopLevelCssRules(css)) {
				if (!dimensionDeclarationPattern.test(rule.body)) continue;
				const hasPageLocalDimensionHelper = rule.selectors.some((selector) =>
					dimensionHelperSelectorPattern.test(selector),
				);
				if (hasPageLocalDimensionHelper) {
					violations.push(`${page.id}:${getLineNumber(css, rule.start)}:${rule.selector}`);
				}
			}
		}

		expect(violations).toEqual([]);
	});

	it("preserves skeleton loading rhythm through shared modifiers", () => {
		const violations: string[] = [];
		const marketsPages = ["markets-calendar", "markets-screener"];

		for (const pageId of marketsPages) {
			const html = readPrototypeHtml(activePageById(pageId));
			for (const classMatch of html.matchAll(/class="([^"]*\bskeleton\b[^"]*)"/g)) {
				const classes = classMatch[1].split(/\s+/);
				if (classes.includes("skeleton-bar") && !classes.includes("skeleton-bar-md")) {
					violations.push(`${pageId}:bare-skeleton-bar`);
				}
			}
		}

		const strategyListHtml = readPrototypeHtml(activePageById("strategy-list"));
		const expectedWidths = ["skeleton--w86", "skeleton--w72", "skeleton--w94", "skeleton--w64"];
		for (const widthClass of expectedWidths) {
			if (!strategyListHtml.includes(widthClass)) {
				violations.push(`strategy-list:missing-${widthClass}`);
			}
		}

		expect(violations).toEqual([]);
	});

	it("uses one token and shared CSS import order across active prototypes", () => {
		const expectedOrder = [
			"tokens-base.css",
			"tokens-semantic.css",
			"tokens-atmosphere.css",
			"tokens-domain.css",
			"tokens-interaction.css",
			"tokens-density.css",
			"tokens-component.css",
			"tokens-shell.css",
			"tokens-data-viz.css",
			"tokens-style.css",
			"layout-shell.css",
			"layout-gallery.css",
			"layout-components.css",
			"layout-overlay.css",
			"layout-state.css",
			"theme-switcher.css",
			"prototype-toggles.css",
		];
		const violations: string[] = [];

		for (const page of activePages()) {
			const html = readPrototypeHtml(page);
			const imports = [
				...html.matchAll(
					/href="([^"]*(?:tokens-[^"]+\.css|layout-[^"]+\.css|theme-switcher\.css|prototype-toggles\.css))"/g,
				),
			].map((match) => match[1].split("/").at(-1));

			if (imports.join(">") !== expectedOrder.join(">")) {
				violations.push(`${page.id}:${imports.join(">")}`);
			}
		}

		expect(violations).toEqual([]);
	});

	it("uses default prototype density without shrinking typography", () => {
		const densityCss = readFileSync(join(prototypesDir, "tokens-style.css"), "utf8");
		const switcherJs = readFileSync(join(prototypesDir, "shared/theme-switcher.js"), "utf8");
		const violations: string[] = [];

		if (!densityCss.includes('[data-density="default"]')) {
			violations.push("tokens-style.css:default-density");
		}
		if (/--density-font-delta:\s*-/.test(densityCss)) {
			violations.push("tokens-style.css:negative-font-delta");
		}
		if (!switcherJs.includes("'default'")) {
			violations.push("theme-switcher.js:default-density");
		}
		if (/var DENSITIES = \[[^\]]*'dense'/.test(switcherJs)) {
			violations.push("theme-switcher.js:dense-primary-density");
		}

		for (const page of activePages()) {
			const html = readPrototypeHtml(page);
			const density = /<html\b[^>]*data-density="([^"]+)"/.exec(html)?.[1];
			if (density !== "default") {
				violations.push(`${page.id}:html-density:${density ?? "missing"}`);
			}
			if (/data-density="dense"/.test(html)) {
				violations.push(`${page.id}:dense-html-density`);
			}
		}

		expect(violations).toEqual([]);
	});

	it("keeps comfortable density and resize suppression explicit", () => {
		const densityCss = readFileSync(join(prototypesDir, "tokens-style.css"), "utf8");
		const layoutCss = stripCssComments(readAllLayoutCss());
		const comfortableBlock = /\[data-density="comfortable"\]\s*\{([^}]*)\}/.exec(densityCss)?.[1] ?? "";
		const requiredComfortableVars = [
			"--density-panel-padding",
			"--density-section-gap",
			"--density-gutter",
			"--density-strip-height",
			"--density-toolbar-height",
			"--density-row-height",
			"--density-cell-padding-x",
			"--density-cell-padding-y",
			"--density-header-height",
			"--density-input-height",
			"--density-action-height",
			"--density-chart-header",
			"--density-chart-padding",
			"--density-font-delta",
		];
		const expectedComfortableDeclarations = [
			["--density-panel-padding", "var(--space-16)"],
			["--density-section-gap", "var(--space-16)"],
			["--density-gutter", "var(--space-20)"],
			["--density-strip-height", "2.5rem"],
			["--density-toolbar-height", "2.5rem"],
			["--density-row-height", "2.625rem"],
			["--density-cell-padding-x", "var(--space-16)"],
			["--density-cell-padding-y", "var(--space-8)"],
			["--density-header-height", "2.25rem"],
			["--density-input-height", "2.25rem"],
			["--density-action-height", "2.25rem"],
			["--density-chart-header", "2.25rem"],
			["--density-chart-padding", "var(--space-16)"],
		] as const;
		const violations = requiredComfortableVars
			.filter((token) => !new RegExp(`${token}\\s*:`).test(comfortableBlock))
			.map((token) => `tokens-style.css:comfortable:${token}`);
		for (const [token, value] of expectedComfortableDeclarations) {
			if (!new RegExp(`${token}\\s*:\\s*${value.replace(/[()]/g, "\\$&")}`).test(comfortableBlock)) {
				violations.push(`tokens-style.css:comfortable-value:${token}`);
			}
		}

		if (/html\[data-resizing-panel="true"\]\s+\*/.test(layoutCss)) {
			violations.push("shared-layout:global-resize-transition-suppression");
		}
		if (!/html\[data-resizing-panel="true"\]\s+(?::is\(\.shell|\.shell)/.test(layoutCss)) {
			violations.push("shared-layout:shell-scoped-resize-transition-suppression");
		}

		expect(violations).toEqual([]);
	});

	it("documents and uses approved prototype structural dimension tokens", () => {
		const tokenCss = readFileSync(prototypeTokensStyleCss, "utf8");
		const tokenDeclarations = new Map(
			[...tokenCss.matchAll(/(--[a-z0-9-]+)\s*:\s*([^;]+);/gi)].map((match) => [
				match[1],
				match[2].trim(),
			]),
		);
		const tokenSpecs = [
			readFileSync(tokenNamingLayeringSpec, "utf8"),
			readFileSync(tokenStabilizationSpec, "utf8"),
		];
		const alphaCss = getStyleBlocks(readPrototypeHtml(activePageById("alpha-explorer")));
		const consoleCss = getStyleBlocks(readPrototypeHtml(activePageById("agent-console-v2")));
		const pageCssById = new Map([
			["alpha-explorer", alphaCss],
			["agent-console-v2", consoleCss],
		]);
		const violations: string[] = [];

		for (const [token, expectedValue] of Object.entries(prototypeStructuralDimensionTokens)) {
			if (tokenDeclarations.get(token) !== expectedValue) {
				violations.push(`tokens-style.css:${token}:${tokenDeclarations.get(token) ?? "missing"}`);
			}
			tokenSpecs.forEach((spec, index) => {
				if (!spec.includes(token)) {
					violations.push(`spec-${index === 0 ? "14" : "15"}:${token}`);
				}
			});
		}

		for (const [pageId, css] of pageCssById) {
			if (/var\(\s*--status-bar-height\s*,\s*24px\s*\)/.test(css)) {
				violations.push(`${pageId}:status-bar-height-fallback`);
			}
			if (!hasDeclaration(getSelectorRuleBody(css, ".panel-header"), "height", /var\(\s*--panel-header-height\s*\)/)) {
				violations.push(`${pageId}:panel-header-height`);
			}
			const noiseSelector = pageId === "alpha-explorer" ? ".alpha-shell::before" : ".agent-shell::before";
			if (!hasDeclaration(getSelectorRuleBody(css, noiseSelector), "opacity", /var\(\s*--surface-noise-opacity\s*\)/)) {
				violations.push(`${pageId}:surface-noise-opacity`);
			}
		}

		if (!hasDeclaration(getSelectorRuleBody(alphaCss, ".track"), "height", /var\(\s*--progress-bar-height\s*\)/)) {
			violations.push("alpha-explorer:progress-bar-height");
		}
		if (!hasDeclaration(getSelectorRuleBody(consoleCss, ".progress"), "height", /var\(\s*--progress-bar-height\s*\)/)) {
			violations.push("agent-console-v2:progress-bar-height");
		}
		if (
			!/grid-template-rows\s*:\s*var\(\s*--shell-header-height\s*\)\s+var\(\s*--tab-bar-height\s*\)\s+minmax\(0,\s*1fr\)/i.test(
				getSelectorRuleBody(consoleCss, ".agent-shell") ?? "",
			)
		) {
			violations.push("agent-console-v2:tab-bar-height");
		}

		expect(violations).toEqual([]);
	});

	it("defines one shared visual order for global header utilities", () => {
		const css = readFileSync(prototypeLayoutCss, "utf8");
		const expectedOrder = [
			["command", "1"],
			["copilot", "2"],
			["notifications", "3"],
			["help", "4"],
			["theme", "5"],
			["density", "6"],
			["account", "7"],
		] as const;

		for (const [utility, order] of expectedOrder) {
			expect(css).toContain(`[data-shell-utility="${utility}"]`);
			expect(css).toContain(`order: ${order};`);
		}

		expect(css).toContain("[data-header-utility-bar]");
		expect(css).toContain("flex: 0 0 auto;");
	});

	it("normalizes header controls and terminal command trigger styling", () => {
		const layoutCss = readFileSync(prototypeLayoutCss, "utf8");
		const switcherCss = readFileSync(prototypeThemeSwitcherCss, "utf8");

		expect(layoutCss).toContain("--header-command-width");
		expect(layoutCss).toContain(".header-command-trigger");
		expect(layoutCss).toContain("font-family: var(--font-family-code);");
		expect(layoutCss).toContain(".command-prompt");
		expect(layoutCss).toContain(".command-query");
		expect(layoutCss).toContain(".command-shortcut");
		expect(layoutCss).toContain(".shell-header :is(.header-utility-btn");
		expect(layoutCss).toContain(".shell-header .header-actions :is(.btn");
		expect(layoutCss).toContain("height: var(--header-btn-size);");
		expect(layoutCss).toContain("font-size: var(--font-size-12);");
		expect(switcherCss).not.toContain("box-shadow: inset 0 0 0 1px");
	});

	it("styles direct preference icon toggles without menu chrome", () => {
		const css = readFileSync(prototypeThemeSwitcherCss, "utf8");

		expect(css).toContain(".preference-icon-btn");
		expect(css).toContain("[data-preference-active=\"true\"]");
		expect(css).not.toContain(".view-preferences-menu");
	});

	it("normalizes shell headers and overlay surfaces through shared chrome", () => {
		const layoutCss = readFileSync(prototypeLayoutCss, "utf8");
		const togglesCss = readFileSync(prototypeTogglesCss, "utf8");

		expect(layoutCss).toContain("padding: 0 var(--density-gutter);");
		expect(layoutCss).toContain("gap: var(--space-8);");
		expect(layoutCss).toContain("background: var(--surface-app);");
		expect(layoutCss).toContain("backdrop-filter: none;");
		expect(layoutCss).toContain(".shell-header.shell-header::after");
		expect(layoutCss).toContain("display: none;");
		expect(layoutCss).toContain(".shell-header .header-title.header-title::after");
		expect(layoutCss).toContain("content: none;");

		expect(togglesCss).toContain("background: color-mix(in oklch, var(--surface-app) 72%, transparent);");
		expect(togglesCss).toContain("background: var(--surface-modal) !important;");
		expect(togglesCss).toContain("box-shadow: 0 0 0 1px var(--border-subtle) !important;");
	});

	it("keeps prototype overlay, tray, and semantic feedback motion shared", () => {
		const layoutCss = readAllLayoutCss();
		const togglesCss = readFileSync(prototypeTogglesCss, "utf8");
		const requiredSharedMotion = [
			"@keyframes overlay-drawer-enter",
			"@keyframes overlay-sheet-enter",
			"@keyframes overlay-modal-enter",
			"animation: overlay-drawer-enter",
			"animation: overlay-sheet-enter",
			"animation: overlay-modal-enter",
			".bottom-tray",
			"transition: max-height",
			".semantic-value-flash",
			".semantic-status-transition",
			".threshold-crossed",
			".linked-region-pulse",
			".resize-separator::after",
		];

		const combinedCss = `${layoutCss}\n${togglesCss}`;
		const missing = requiredSharedMotion.filter((snippet) => !combinedCss.includes(snippet));

		expect(missing).toEqual([]);
	});

	it("keeps active prototype and shared CSS free of viewport, transition, focus, and tiny-text regressions", () => {
		const violations: string[] = [];

		for (const source of readPrototypeCssSources()) {
			const rawCss = source.css;
			const css = stripCssComments(rawCss);

			for (const match of css.matchAll(/(^|[^a-z0-9-])100vh\b/gi)) {
				const index = match.index + match[1].length;
				if (!hasFixedCanvasException(rawCss, index)) {
					violations.push(`${source.label}:${getLineNumber(css, index)}:100vh`);
				}
			}

			for (const match of css.matchAll(/transition\s*:\s*([^;}]+)/gi)) {
				const transitionValue = match[1];
				if (transitionValue.split(",").some((item) => /^all(?:\s|$)/i.test(item.trim()))) {
					violations.push(`${source.label}:${getLineNumber(css, match.index)}:transition-all`);
				}
			}

			for (const match of css.matchAll(/font-size\s*:\s*9px\b/gi)) {
				violations.push(`${source.label}:${getLineNumber(css, match.index)}:font-size-9px`);
			}

			for (const rule of css.matchAll(/([^{}]+)\{([^{}]*)\}/g)) {
				const selector = rule[1].replace(/\s+/g, " ").trim();
				const body = rule[2];
				if (!/outline\s*:\s*none\b/i.test(body)) continue;

				const bodyWithoutOutlineNone = body.replace(/outline\s*:\s*none(?:\s*!important)?\s*;?/gi, "");
				const hasReplacementFocusCue =
					declarationHasNonNoneValue(bodyWithoutOutlineNone, "outline") ||
					(hasFocusSelector(selector) && hasFocusRingBoxShadow(body));
				if (!hasReplacementFocusCue) {
					violations.push(`${source.label}:${getLineNumber(css, rule.index)}:outline-none:${selector}`);
				}
			}
		}

		expect(violations).toEqual([]);
	});

	it("keeps bare rgba and direct oklch colors out of active prototype declarations", () => {
		const hits: string[] = [];

		for (const page of readManifest().pages) {
			if (!isActiveRoutePrototype(page)) continue;

			for (const color of findHardcodedColors(readPrototypeHtml(page))) {
				hits.push(`${page.id}:${color}`);
			}
		}

		expect(hits).toEqual([]);
	});

	it("keeps hardcoded color scanner scoped to real CSS color declarations", () => {
		expect(findHardcodedColors('fill="url(#dd2-g)"')).toEqual([]);
		expect(findHardcodedColors("content: '&#10005;'")).toEqual([]);
		expect(findHardcodedColors('href="#fff" data-fragment="#123456"')).toEqual([]);
		expect(findHardcodedColors("color: #fff")).toEqual(["#fff"]);
		expect(findHardcodedColors("background: rgba(0,0,0,.2)")).toEqual(["rgba("]);
	});
});
