import { existsSync, readFileSync, readdirSync } from "node:fs";
import { dirname, join, relative } from "node:path";
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
const chartInteractionContractPath = join(root, "docs/contracts/prototype-chart-interactions.md");
const prototypeFontsCss = join(prototypesDir, "shared/fonts.css");
const prototypeLayoutCss = join(prototypesDir, "shared/layout-shell.css");
const prototypeLayoutModulePaths = [
	"shared/layout-shell.css",
	"shared/layout-gallery.css",
	"shared/layout-components.css",
	"shared/layout-overlay.css",
	"shared/layout-state.css",
] as const;
const glowBudgetSharedTextResourcePaths = [
	"shared/prototype-interactions.js",
	"shared/theme-switcher.js",
	"shared/mock-data.js",
	"shared/screener-workflow.js",
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
const retiredRoutePrototypeIds = new Set([
	"alpha-explorer",
	"trading-overview",
	"regime-monitor",
	"markets-intelligence",
	"markets-calendar",
]);
const currentContractIdByPrototypeId = new Map([
	["platform", "system"],
	["portfolio", "portfolio-overview"],
	["agent-console-v2", "research-agent-lab"],
	["orders-ledger", "portfolio-transactions"],
	["risk-center", "portfolio-risk"],
	["platform-settings", "system-settings"],
]);
const landingSyncFields = [
	"reactRouteStatus",
	"featureModule",
	"contractStatus",
	"overlayStatus",
	"prototypeVerified",
	"reactParityVerified",
] as const;
const prototypeStructuralDimensionTokens = {
	"--panel-header-height": "38px",
	"--tab-bar-height": "42px",
	"--progress-bar-height": "6px",
	"--surface-noise-opacity": "0.018",
} as const;

type LandingStatus = {
	reactRouteStatus?: string;
	featureModule?: string;
	contractStatus?: string;
	overlayStatus?: string;
	prototypeVerified?: boolean;
	reactParityVerified?: boolean;
};

type ManifestPage = {
	id: string;
	file: string;
	shellFamily?: string;
	status?: string;
	landing?: LandingStatus;
};

type EditionManifest = {
	pages: ManifestPage[];
};

type PageContract = {
	id: string;
	prototypeRef: string;
	nextPrototypeRef?: string;
	shellFamily: string;
	landing?: LandingStatus;
	overlays?: Array<{ id: string; prototypeSelector: string }>;
	nextOverlays?: Array<{ prototypeSelector: string }>;
	nextSlots?: unknown[];
};

type CssSource = {
	label: string;
	css: string;
};

type HtmlSource = {
	label: string;
	html: string;
};

type TextSource = {
	label: string;
	text: string;
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
	atRuleContext?: string[];
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
	return [
		...new Set(
			[...html.matchAll(/id="(overlay-[^"]+)"/g)].flatMap((match) =>
				match[1] === undefined ? [] : [match[1]],
			),
		),
	];
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

function findPrimaryContract(page: ManifestPage): PageContract | undefined {
	const prototypeRef = `docs/designs/specs/prototypes/${page.file}`;
	const contractId = currentContractIdByPrototypeId.get(page.id) ?? page.id;
	return readContracts().find(
		(contract) => contract.id === contractId && contract.prototypeRef === prototypeRef,
	);
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

function getMediaMaxWidth(selector: string): number | undefined {
	const maxWidthMatch = /\(\s*max-width\s*:\s*(\d+)px\s*\)/i.exec(selector);
	const capturedWidth = maxWidthMatch?.[1];
	return capturedWidth === undefined ? undefined : Number.parseInt(capturedWidth, 10);
}

function canContainStyleRulesAtRule(selector: string): boolean {
	return /^@(?:media|supports|container|layer|scope|document|starting-style)\b/i.test(selector);
}

function readTopLevelCssRules(
	css: string,
	offset = 0,
	mediaMaxWidth?: number,
	atRuleContext: string[] = [],
): CssRule[] {
	const rules: CssRule[] = [];
	let index = 0;

	while (index < css.length) {
		const openBraceIndex = css.indexOf("{", index);
		if (openBraceIndex === -1) break;

		const selector = css.slice(index, openBraceIndex).trim();
		const block = getBalancedCssBlock(css, openBraceIndex);
		if (!block) break;

		if (/^@(?:-[a-z]+-)?keyframes\b/i.test(selector)) {
			const keyframeName = /^@(?:-[a-z]+-)?keyframes\s+([a-z0-9_-]+)/i.exec(selector)?.[1] ?? "unknown";
			rules.push(
				...readTopLevelCssRules(block.body, offset + block.start, mediaMaxWidth, atRuleContext).map((rule) => ({
					...rule,
					selector: `@keyframes ${keyframeName} ${rule.selector}`,
					selectors: rule.selectors.map((stepSelector) => `@keyframes ${keyframeName} ${stepSelector}`),
				})),
			);
		} else if (selector.startsWith("@") && canContainStyleRulesAtRule(selector)) {
			rules.push(
				...readTopLevelCssRules(
					block.body,
					offset + block.start,
					getMediaMaxWidth(selector) ?? mediaMaxWidth,
					[...atRuleContext, selector],
				),
			);
		} else if (!selector.startsWith("@")) {
			rules.push({
				selector,
				selectors: selector.split(",").map((item) => item.trim()),
				body: block.body,
				start: offset + index,
				end: offset + block.end,
				...(mediaMaxWidth === undefined ? {} : { mediaMaxWidth }),
				atRuleContext,
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

function getSelectorRuleBodies(css: string, selector: string): string[] {
	return readTopLevelCssRules(stripCssComments(css))
		.filter((rule) => rule.selectors.includes(selector))
		.map((rule) => rule.body);
}

function hasDeclaration(body: string | undefined, property: string, valuePattern: RegExp): boolean {
	if (!body) return false;

	return [...body.matchAll(new RegExp(`${property}\\s*:\\s*([^;]+)`, "gi"))].some((match) => {
		const value = match[1];
		return value !== undefined && valuePattern.test(value.trim());
	});
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
		const value = match[1]?.trim();
		if (value === undefined) return false;
		return !/^none(?:\s*!important)?$/i.test(value);
	});
}

function hasFocusSelector(selector: string): boolean {
	return /:focus(?:-visible|-within)?\b/.test(selector);
}

function hasFocusRingBoxShadow(body: string): boolean {
	return [...body.matchAll(/box-shadow\s*:\s*([^;]+)/gi)].some((match) => {
		const value = match[1]?.trim();
		if (value === undefined) return false;
		if (/^none(?:\s*!important)?$/i.test(value)) return false;

		return (
			/var\(\s*--(?:interaction-focus-ring|interaction-focus-border|focus-ring|brand-accent)\b/.test(value) ||
			/\b0\s+0\s+0\b/.test(value)
		);
	});
}

function isFocusRingShadowLayer(value: string): boolean {
	return (
		/^0\s+0\s+0\s+(?:1(?:\.5)?|2|3|4)px\s+(?:var\(\s*--(?:interaction-focus-ring|interaction-focus-border|focus-ring|brand-accent)\s*\)|color-mix\(in oklch,\s*var\(\s*--(?:interaction-focus-ring|interaction-focus-border|focus-ring|brand-accent)\s*\)[^)]+\))(?:\s*!important)?$/i.test(
			value,
		)
	);
}

function readPrototypeCssSources(): CssSource[] {
	return [
		{ label: "shared/fonts.css", css: readFileSync(prototypeFontsCss, "utf8") },
		{ label: "shared/layout-shell.css", css: readFileSync(prototypeLayoutCss, "utf8") },
		{ label: "shared/layout-gallery.css", css: readFileSync(join(prototypesDir, "shared/layout-gallery.css"), "utf8") },
		{ label: "shared/layout-components.css", css: readFileSync(join(prototypesDir, "shared/layout-components.css"), "utf8") },
		{ label: "shared/layout-overlay.css", css: readFileSync(join(prototypesDir, "shared/layout-overlay.css"), "utf8") },
		{ label: "shared/layout-state.css", css: readFileSync(join(prototypesDir, "shared/layout-state.css"), "utf8") },
		{
			label: "shared/prototype-interactions.css",
			css: readFileSync(join(prototypesDir, "shared/prototype-interactions.css"), "utf8"),
		},
		{ label: "shared/theme-switcher.css", css: readFileSync(prototypeThemeSwitcherCss, "utf8") },
		{ label: "shared/prototype-toggles.css", css: readFileSync(prototypeTogglesCss, "utf8") },
		{ label: "tokens-style.css", css: readFileSync(prototypeTokensStyleCss, "utf8") },
		...activePages().map((page) => ({
			label: `${page.id}:inline-css`,
			css: getStyleBlocks(readPrototypeHtml(page)),
		})),
	];
}

function readPrototypeHtmlFilesRecursive(dir = prototypesDir): HtmlSource[] {
	return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
		const fullPath = join(dir, entry.name);
		if (entry.isDirectory()) return readPrototypeHtmlFilesRecursive(fullPath);
		if (!entry.isFile() || !entry.name.endsWith(".html")) return [];

		return [
			{
				label: relative(root, fullPath),
				html: readFileSync(fullPath, "utf8"),
			},
		];
	});
}

function readFullPrototypeCssSources(): CssSource[] {
	const inlineSources = readPrototypeHtmlFilesRecursive().map((source) => ({
		label: `${source.label}:inline-css`,
		css: getStyleBlocks(source.html),
	}));

	return [...readPrototypeCssSources(), ...inlineSources];
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
	"signals-inbox",
	"orders-ledger",
	"universe-list",
	"strategies-detail",
	"strategy-list",
] as const;
const lightReadabilityPages = [
	"home",
	"a-shares",
	"strategy-studio",
	"platform-settings",
] as const;
const requiredChartAffordances = [
	"crosshair",
	"tooltip",
	"zoom-pan",
	"linked-time-range",
	"selection-to-command",
] as const;
const requiredChartDataAttributes = [
	"data-chart-interaction-contract",
	"data-chart-affordances",
	"data-chart-linked-time-range",
	"data-chart-selection-command",
] as const;
const requiredChartSelectionCommandSchemaTerms = [
	"chartId",
	"rangeId",
	"commandId",
	"selection",
	"kind",
	"point",
	"range",
	"bar",
	"series",
	"timeRange",
	"from",
	"to",
	"timestamp",
	"seriesId",
	"value",
	"prototype:chart-selection-command",
] as const;
const requiredChartTestingExpectationTerms = [
	"DOM contract",
	"Interaction",
	"Keyboard/a11y",
	"Reduced motion",
	"Linked range sync",
	"Selection command payload",
] as const;
const chartInteractionPrototypeRequirements = [
	{
		pageId: "instrument-hub",
		contracts: ["instrument-price-primary"],
	},
	{
		pageId: "risk-center",
		contracts: ["risk-var-trend", "risk-drawdown-trend", "risk-exposure-breakdown"],
	},
	{
		pageId: "backtest-result",
		contracts: ["backtest-nav-drawdown"],
	},
	{
		pageId: "trading-overview",
		contracts: ["trading-equity-pnl"],
	},
] as const;
const requiredChartContractSectionHeadings = [
	"## Required Affordances",
	"## Required data-* Attributes",
	"## Selection Command Schema",
	"## Testing Expectations",
] as const;
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
const dataCriticalInstantMotionExemptions = {
	// Data-critical instantaneous state change: short, one-shot value flash preserves update feedback without decorative travel.
	"value-flash": "data-critical-instant",
	// Data-critical instantaneous state change: short, one-shot semantic value flash preserves update feedback without decorative travel.
	"semantic-value-flash": "data-critical-instant",
} as const;
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

function collectChartInteractionContractViolations(
	document: Document,
	pageId: string,
	contractIds: readonly string[],
): string[] {
	const violations: string[] = [];
	const expectedContractIds = new Set(contractIds);

	for (const contractId of contractIds) {
		const markers = document.querySelectorAll(
			`[data-chart-interaction-contract="${contractId}"]`,
		);
		if (markers.length === 0) {
			violations.push(`${pageId}:${contractId}:missing-marker`);
		}
		if (markers.length > 1) {
			violations.push(`${pageId}:${contractId}:duplicate-marker:${markers.length}`);
		}
	}

	for (const marker of document.querySelectorAll("[data-chart-interaction-contract]")) {
		const contractId = marker.getAttribute("data-chart-interaction-contract")?.trim() ?? "";
		if (!expectedContractIds.has(contractId)) {
			violations.push(`${pageId}:unexpected-marker:${contractId || "empty"}`);
		}
	}

	return violations;
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
	return new Set(
		[...css.matchAll(/(--[a-z0-9-]+)\s*:/gi)].flatMap((match) =>
			match[1] === undefined ? [] : [match[1]],
		),
	);
}

function extractCustomPropertyReferences(css: string): Set<string> {
	return new Set(
		[...css.matchAll(/var\(\s*(--[a-z0-9-]+)/gi)].flatMap((match) =>
			match[1] === undefined ? [] : [match[1]],
		),
	);
}

function getCssFontSizeValues(body: string): string[] {
	return [...body.matchAll(/font-size\s*:\s*([^;]+)/gi)].flatMap((match) => {
		const value = match[1];
		return value === undefined ? [] : [value.trim()];
	});
}

function getPrototypeCssRules(page: ManifestPage): CssRule[] {
	return readTopLevelCssRules(stripCssComments(getStyleBlocks(readPrototypeHtml(page))));
}

function getPrototypeAndSharedCssRules(page: ManifestPage): CssRule[] {
	return [
		...readTopLevelCssRules(stripCssComments(readAllLayoutCss())),
		...getPrototypeCssRules(page),
	];
}

function parseFontSizeMinimumPx(value: string): number | undefined {
	const tokenMatch = /var\(\s*--font-size-(\d+)\s*\)/i.exec(value);
	if (tokenMatch?.[1] !== undefined) return Number.parseInt(tokenMatch[1], 10);

	const pxMatch = /(\d+(?:\.\d+)?)px\b/i.exec(value);
	if (pxMatch?.[1] !== undefined) return Number.parseFloat(pxMatch[1]);

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

function hasReadableAriaLabelledbyTarget(element: Element): boolean {
	const value = element.getAttribute("aria-labelledby")?.trim();
	if (!value) return false;

	return value.split(/\s+/).every((id) => hasReadableText(element.ownerDocument.getElementById(id)));
}

function hasPrototypeAccessibleName(element: Element): boolean {
	if (element.getAttribute("aria-label")?.trim()) return true;
	if (hasReadableAriaLabelledbyTarget(element)) return true;
	if (element.querySelector("title")?.textContent?.trim()) return true;

	return false;
}

function hasOverlaySurfaceAccessibleName(surface: Element): boolean {
	return Boolean(surface.getAttribute("aria-label")?.trim()) || hasReadableAriaLabelledbyTarget(surface);
}

function isApprovedOverlaySurfaceRole(surface: Element): boolean {
	const role = surface.getAttribute("role")?.trim();
	if (!role) return false;
	if (["dialog", "alertdialog"].includes(role)) {
		return hasOverlaySurfaceAccessibleName(surface);
	}

	return ["region", "alert", "status"].includes(role) && hasOverlaySurfaceAccessibleName(surface);
}

function getOverlaySurfaceLikeElements(document: Document): Element[] {
	const surfaces = [
		...document.querySelectorAll(
			[
				"[data-overlay] .overlay-surface",
				"[data-overlay] [class*='overlay-surface--']",
				"[data-overlay].overlay-toast",
				".gallery-card__preview--overlay .overlay-surface",
				".gallery-card__preview--overlay [class*='overlay-surface--']",
			].join(", "),
		),
	];

	return [...new Set(surfaces)];
}

function isSvgInMeaningfulVisualizationContext(svg: Element): boolean {
	const ownTokens = [
		svg.getAttribute("class") ?? "",
		svg.getAttribute("id") ?? "",
		svg.getAttribute("name") ?? "",
		svg.getAttribute("aria-label") ?? "",
		svg.hasAttribute("data-sparkline") ? "sparkline" : "",
		svg.hasAttribute("data-donut") ? "chart" : "",
		svg.hasAttribute("data-heatgrid") ? "heatmap" : "",
	].join(" ");
	if (/\b(?:sparkline|chart|heatmap|matrix|trend)\b/i.test(ownTokens)) return true;

	const context = svg.closest(
		[
			"[data-chart-interaction-contract]",
			"[data-viz-legend]",
			".metric-card",
			".kpi-card",
			".summary-card",
			".chart-panel",
			".chart-body",
			".chart-placeholder",
			".pnl-chart",
			".api-mini-chart",
			".correlation-matrix",
		].join(", "),
	);

	return Boolean(context);
}

function svgHasValidAccessibilitySemantics(svg: Element): boolean {
	if (svg.getAttribute("aria-hidden") === "true") return true;
	if (svg.getAttribute("role") === "img" && hasPrototypeAccessibleName(svg)) return true;

	return false;
}

function isInteractiveDataVizCell(cell: Element): boolean {
	return (
		isInteractivePrototypeElement(cell) ||
		cell.hasAttribute("onclick") ||
		cell.hasAttribute("tabindex") ||
		Boolean(cell.closest("[role='grid'], [role='table']"))
	);
}

function isDataVizCellCandidate(cell: Element): boolean {
	if (cell.tagName.toLowerCase() === "svg") return false;

	const className = cell.getAttribute("class") ?? "";
	const isCellLike = /\b(?:cell|heatmap|matrix|corr|treemap|stat-item|numeric)\b/i.test(className);
	if (!isCellLike && !["td", "th"].includes(cell.tagName.toLowerCase())) return false;

	if (cell.matches("[data-direction], [data-corr], [data-viz-cell-strength], [data-viz-cell-selected]")) {
		return true;
	}

	return (
		/\b(?:heatmap|matrix|corr-cell|viz-cell)\b/i.test(className) &&
		isInteractiveDataVizCell(cell)
	);
}

function hasDataVizCellRole(cell: Element): boolean {
	const role = cell.getAttribute("role")?.trim();
	if (role && ["cell", "gridcell", "button", "rowheader", "columnheader"].includes(role)) return true;

	return ["td", "th"].includes(cell.tagName.toLowerCase());
}

function hasDataVizCellAccessibleLabel(cell: Element): boolean {
	return hasPrototypeAccessibleName(cell);
}

function isSymbolOnlyControl(element: Element): boolean {
	if (element.closest("[aria-hidden='true']")) return false;

	const text = (element.textContent ?? "").replace(/\s+/g, "").trim();
	if (!/^(?:×|✕|x|X|—|←|→|↗|↘|▾|▸|⌄|»|«|!|\+|-)$/.test(text)) return false;

	const className = element.getAttribute("class") ?? "";
	return (
		isInteractivePrototypeElement(element) ||
		element.hasAttribute("tabindex") ||
		/\b(?:close|dismiss|toggle|expand|collapse|danger|tag-close|drawer-close|overlay-close|toast-close)\b/i.test(
			className,
		)
	);
}

function hasSymbolOnlyControlAccessibleSemantics(element: Element): boolean {
	if (element.getAttribute("aria-hidden") === "true") return true;
	if (hasPrototypeAccessibleName(element)) return true;
	if (!isInteractivePrototypeElement(element) && !element.hasAttribute("tabindex")) {
		return Boolean(element.closest("[aria-label], [aria-labelledby]"));
	}

	return false;
}

function hasReadableTextMatch(element: Element, pattern: RegExp): boolean {
	return pattern.test(getReadablePrimaryText(element));
}

function getCssContentMarkers(body: string): string[] {
	return [...body.matchAll(/content\s*:\s*(["'])(.*?)\1/gi)].flatMap((match) => {
		const content = match[2];
		return content === undefined ? [] : [content.replace(/\\[a-f0-9]{1,6}\s?/gi, " ").trim()];
	});
}

function elementHasPseudoSemanticMarker(
	document: Document,
	element: Element,
	rules: CssRule[],
	markerPattern: RegExp,
): boolean {
	for (const rule of rules) {
		if (!/::(?:before|after)\b/i.test(rule.selector)) continue;
		if (!getCssContentMarkers(rule.body).some((marker) => markerPattern.test(marker))) continue;

		for (const selector of rule.selectors) {
			if (!/::(?:before|after)\b/i.test(selector)) continue;
			if (querySelectorAllSafe(document, selector).includes(element)) return true;
		}
	}

	return false;
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
		const property = match[1];
		const capturedValue = match[2];
		if (property === undefined || capturedValue === undefined) return [];
		const value = capturedValue.trim();
		if (property.toLowerCase() === "animation" && /^none(?:\s*!important)?$/i.test(value)) {
			return [];
		}

		return [
			{
				line: getLineNumber(css, match.index ?? 0),
				property: property.toLowerCase(),
				value,
			},
		];
	});
}

function getKeyframeNames(css: string): Set<string> {
	return new Set(
		readTopLevelCssRules(stripCssComments(css))
			.map((rule) => /^@keyframes\s+([a-z0-9_-]+)\b/i.exec(rule.selector)?.[1])
			.filter((name): name is string => Boolean(name)),
	);
}

function getAnimationFamilyUsages(
	css: string,
	family: string,
): Array<{ line: number; selector: string; selectors: string[] }> {
	const rules = readTopLevelCssRules(stripCssComments(css));
	const familyPattern = new RegExp(`\\b${family}\\b`, "i");

	return rules
		.filter((rule) => !/^@keyframes\b/i.test(rule.selector))
		.filter((rule) => familyPattern.test(rule.body))
		.filter((rule) => /\banimation(?:-name)?\s*:/i.test(rule.body))
		.map((rule) => ({
			line: getLineNumber(css, rule.start),
			selector: rule.selector,
			selectors: rule.selectors,
		}));
}

function hasAnimationReducedMotionDeclaration(body: string): boolean {
	return (
		/\banimation\s*:\s*none(?:\s*!important)?\s*;/i.test(body) ||
		/\banimation-name\s*:\s*none(?:\s*!important)?\s*;/i.test(body) ||
		/\banimation-duration\s*:\s*0\.01ms(?:\s*!important)?\s*;/i.test(body)
	);
}

function normalizeSelectorForMotionCoverage(selector: string): string {
	return selector
		.replace(/\s+/g, " ")
		.trim();
}

function getTerminalSelectorCompound(selector: string): string {
	const normalized = normalizeSelectorForMotionCoverage(selector);
	const parts = normalized
		.split(/\s*[>+~]\s*|\s+/)
		.map((part) => part.trim())
		.filter(Boolean);

	return parts.at(-1) ?? "";
}

type SelectorAttribute = {
	name: string;
	operator?: string;
	value?: string;
};

type SelectorCompound = {
	attributes: SelectorAttribute[];
	classes: string[];
	hasFunctionalPseudo: boolean;
	negatedClasses: string[];
	pseudoElement?: string;
	raw: string;
};

function stripFunctionalPseudos(selector: string): string {
	return selector.replace(/:(?:not|has|is|where)\([^)]*\)/gi, "");
}

function getSelectorPseudoElement(selector: string): string | undefined {
	return /::(before|after)\b/i.exec(selector)?.[1]?.toLowerCase();
}

function getNegatedSelectorClasses(selector: string): string[] {
	return [...selector.matchAll(/:not\(([^)]*)\)/gi)].flatMap((match) => {
		const contents = match[1];
		return contents === undefined ? [] : getSelectorClasses(contents);
	});
}

function getSelectorClasses(selector: string): string[] {
	return [...stripFunctionalPseudos(selector).matchAll(/\.([a-z0-9_-]+)/gi)].flatMap((match) =>
		match[1] === undefined ? [] : [match[1]],
	);
}

function getSelectorAttributes(selector: string): SelectorAttribute[] {
	return [
		...stripFunctionalPseudos(selector).matchAll(
			/\[([a-z0-9_-]+)(?:\s*([*^$|~]?=)\s*["']?([a-z0-9_-]+)["']?)?\]/gi,
		),
	].flatMap((match) => {
		const name = match[1];
		if (name === undefined) return [];
		const operator = match[2];
		const value = match[3];
		return [
			{
				name,
				...(operator === undefined ? {} : { operator }),
				...(value === undefined ? {} : { value }),
			},
		];
	});
}

function parseSelectorCompound(selector: string): SelectorCompound {
	const pseudoElement = getSelectorPseudoElement(selector);
	return {
		attributes: getSelectorAttributes(selector),
		classes: getSelectorClasses(selector),
		hasFunctionalPseudo: /:(?:not|has|is|where)\(/i.test(selector),
		negatedClasses: getNegatedSelectorClasses(selector),
		...(pseudoElement === undefined ? {} : { pseudoElement }),
		raw: selector,
	};
}

function terminalCompoundCoversUsage(reducedTerminal: string, usageTerminal: string): boolean {
	if (!reducedTerminal || !usageTerminal) return false;
	if (reducedTerminal === usageTerminal) return true;

	const reduced = parseSelectorCompound(reducedTerminal);
	const usage = parseSelectorCompound(usageTerminal);
	if (reduced.hasFunctionalPseudo) return false;
	if (reduced.pseudoElement !== usage.pseudoElement) return false;
	if (reduced.negatedClasses.some((className) => usage.classes.includes(className))) return false;

	const reducedClasses = reduced.classes;
	const usageClasses = usage.classes;
	const reducedAttributes = reduced.attributes;
	const usageAttributes = usage.attributes;
	if (
		reduced.pseudoElement &&
		/^\*?::(?:before|after)$/i.test(reduced.raw) &&
		reducedClasses.length === 0 &&
		reducedAttributes.length === 0
	) {
		return true;
	}
	if (reducedClasses.length === 0 && reducedAttributes.length === 0) return false;

	const classesCovered = reducedClasses.every((className) => usageClasses.includes(className));
	const attributesCovered = reducedAttributes.every((attribute) => {
		if (attribute.name === "class" && attribute.operator === "*=" && attribute.value) {
			return usageClasses.some((className) => className.includes(attribute.value ?? ""));
		}

		return usageAttributes.some((usageAttribute) => {
			if (usageAttribute.name !== attribute.name) return false;
			if (!attribute.operator || !attribute.value) return true;
			if (!usageAttribute.value) return false;

			if (attribute.operator === "=") return usageAttribute.value === attribute.value;
			if (attribute.operator === "*=") return usageAttribute.value.includes(attribute.value);
			if (attribute.operator === "^=") return usageAttribute.value.startsWith(attribute.value);
			if (attribute.operator === "$=") return usageAttribute.value.endsWith(attribute.value);
			return usageAttribute.value === attribute.value;
		});
	});

	return classesCovered && attributesCovered;
}

function reducedMotionSelectorCoversUsage(reducedSelector: string, usageSelector: string): boolean {
	return terminalCompoundCoversUsage(
		getTerminalSelectorCompound(reducedSelector),
		getTerminalSelectorCompound(usageSelector),
	);
}

function reducedMotionCssCoversUsage(
	reducedMotionCss: string,
	usage: { selectors: string[] },
): boolean {
	return readTopLevelCssRules(stripCssComments(reducedMotionCss)).some(
		(rule) =>
			hasAnimationReducedMotionDeclaration(rule.body) &&
			rule.selectors.some((reducedSelector) =>
				usage.selectors.some((usageSelector) =>
					reducedMotionSelectorCoversUsage(reducedSelector, usageSelector),
				),
			),
	);
}

function getTransitionItems(value: string): string[] {
	return value
		.split(",")
		.map((item) => item.trim())
		.filter(Boolean);
}

function splitCssList(value: string): string[] {
	const items: string[] = [];
	let itemStart = 0;
	let parenthesesDepth = 0;

	for (let index = 0; index < value.length; index += 1) {
		const char = value[index];
		if (char === "(") parenthesesDepth += 1;
		if (char === ")") parenthesesDepth = Math.max(0, parenthesesDepth - 1);
		if (char === "," && parenthesesDepth === 0) {
			items.push(value.slice(itemStart, index).trim());
			itemStart = index + 1;
		}
	}

	items.push(value.slice(itemStart).trim());

	return items.filter(Boolean);
}

function readCssFunctionArguments(value: string, functionName: string): string[] {
	const items: string[] = [];
	const pattern = new RegExp(`${functionName}\\s*\\(`, "gi");

	for (const match of value.matchAll(pattern)) {
		let parenthesesDepth = 1;
		const argumentStart = (match.index ?? 0) + match[0].length;

		for (let index = argumentStart; index < value.length; index += 1) {
			const char = value[index];
			if (char === "(") parenthesesDepth += 1;
			if (char === ")") parenthesesDepth -= 1;
			if (parenthesesDepth === 0) {
				items.push(value.slice(argumentStart, index).trim());
				break;
			}
		}
	}

	return items;
}

function toPosixPath(path: string): string {
	return path.replaceAll("\\", "/");
}

function getCssSourceLabel(path: string): string {
	const prototypeRelativePath = toPosixPath(relative(prototypesDir, path));
	if (prototypeRelativePath !== ".." && !prototypeRelativePath.startsWith("../")) {
		return prototypeRelativePath;
	}

	return toPosixPath(relative(root, path));
}

function normalizeStylesheetHref(href: string): string | undefined {
	const normalizedHref = href.trim();
	if (!normalizedHref || /^(?:[a-z][a-z0-9+.-]*:|\/\/|#)/i.test(normalizedHref)) return undefined;

	const resourcePath = normalizedHref.split(/[?#]/, 1)[0];
	return resourcePath?.endsWith(".css") ? resourcePath : undefined;
}

function readActiveLinkedCssSources(): CssSource[] {
	const sources: CssSource[] = [];
	const seenPaths = new Set<string>();

	for (const page of activePages()) {
		const pageDir = dirname(join(prototypesDir, page.file));
		const links = [...readPrototypeDocument(page).querySelectorAll("link[href]")].filter((link) =>
			link
				.getAttribute("rel")
				?.toLowerCase()
				.split(/\s+/)
				.includes("stylesheet"),
		);

		for (const link of links) {
			const href = normalizeStylesheetHref(link.getAttribute("href") ?? "");
			if (!href) continue;

			const path = join(pageDir, href);
			if (seenPaths.has(path)) continue;

			seenPaths.add(path);
			sources.push({
				label: getCssSourceLabel(path),
				css: readFileSync(path, "utf8"),
			});
		}
	}

	return sources;
}

function readGlowBudgetCssSources(): CssSource[] {
	return [
		...readActiveLinkedCssSources(),
		...activePages().map((page) => ({
			label: page.file,
			css: getStyleBlocks(readPrototypeHtml(page)),
		})),
	];
}

function readGlowBudgetSharedTextSources(): TextSource[] {
	return glowBudgetSharedTextResourcePaths.map((path) => ({
		label: path,
		text: readFileSync(join(prototypesDir, path), "utf8"),
	}));
}

function readGlowBudgetHtmlSources(): HtmlSource[] {
	return activePages().map((page) => ({
		label: page.file,
		html: readPrototypeHtml(page),
	}));
}

const approvedStructuralShadowTokens = new Set([
	"--shadow-xs",
	"--shadow-sm",
	"--shadow",
	"--shadow-md",
	"--shadow-lg",
	"--shadow-xl",
	"--shadow-2xl",
	"--shadow-inner",
	"--shadow-none",
	"--shadow-subtle",
]);

type ShadowTokenReference = {
	name: string;
	fallback?: string;
};

function extractShadowCustomPropertyValues(css: string): Map<string, string> {
	return new Map(
		[...css.matchAll(/(--shadow-[a-z0-9-]+)\s*:\s*([^;]+);/gi)].flatMap((match) => {
			const name = match[1];
			const value = match[2];
			return name === undefined || value === undefined ? [] : [[name, value.trim()] as const];
		}),
	);
}

function readShadowTokenReference(value: string): ShadowTokenReference | undefined {
	const match = /^var\(\s*(--shadow-[a-z0-9-]+)\s*(?:,\s*([\s\S]+))?\)$/i.exec(value.trim());
	if (match?.[1] === undefined) return undefined;
	const fallback = match[2]?.trim();

	return {
		name: match[1],
		...(fallback === undefined ? {} : { fallback }),
	};
}

function resolveShadowTokenLayer(
	layer: string,
	customProperties: Map<string, string>,
	seen = new Set<string>(),
): string | undefined {
	const reference = readShadowTokenReference(layer);
	if (!reference || seen.has(reference.name)) return undefined;

	const value = customProperties.get(reference.name);
	if (value) {
		seen.add(reference.name);
		return resolveShadowTokenLayer(value, customProperties, seen) ?? value;
	}

	return reference.fallback;
}

function isApprovedStructuralShadowToken(layer: string, customProperties: Map<string, string>): boolean {
	const reference = readShadowTokenReference(layer);
	return Boolean(
		reference &&
			!customProperties.has(reference.name) &&
			!reference.fallback &&
			approvedStructuralShadowTokens.has(reference.name),
	);
}

function formatCssRuleSelector(rule: CssRule): string {
	return [...(rule.atRuleContext ?? []), rule.selector].join(" ");
}

function isGlowBudgetAllowedBoxShadowLayer(
	selector: string,
	layer: string,
	customProperties: Map<string, string>,
): boolean {
	const normalizedSelector = selector.replace(/\s+/g, " ").trim();
	const normalizedValue = layer.replace(/\s+/g, " ").trim();

	if (/var\(\s*--interaction-dragging-shadow\s*\)/i.test(normalizedValue)) return true;
	const resolvedShadowToken = resolveShadowTokenLayer(normalizedValue, customProperties);
	if (resolvedShadowToken) {
		return isGlowBudgetAllowedBoxShadow(selector, resolvedShadowToken, customProperties);
	}
	if (isApprovedStructuralShadowToken(normalizedValue, customProperties)) return true;
	if (hasFocusSelector(normalizedSelector) && isFocusRingShadowLayer(normalizedValue)) {
		return true;
	}
	if (isAllowedRailActiveGlowLayer(normalizedSelector, normalizedValue)) {
		return true;
	}
	if (isAllowedStatusDotGlowLayer(normalizedSelector, normalizedValue)) {
		return true;
	}
	if (isAllowedPrimaryCtaHoverLayer(normalizedSelector, normalizedValue)) {
		return true;
	}
	if (hasDecorativeRadialGlow(normalizedValue)) {
		return false;
	}
	if (isInsetBorderShadowLayer(normalizedValue)) {
		return true;
	}
	if (isStructuralSpreadRingShadowLayer(normalizedSelector, normalizedValue)) {
		return true;
	}
	if (isStructuralSingleEdgeShadowLayer(normalizedSelector, normalizedValue)) {
		return true;
	}
	if (isNeutralStructuralElevationShadowLayer(normalizedValue)) {
		return true;
	}

	return false;
}

function hasDecorativeSemanticShadowColor(value: string): boolean {
	return (
		/color-mix\(in oklch,\s*(?:var\(\s*--(?:brand|market|risk|system|agent|execution)-|currentColor)/i.test(
			value,
		) ||
		/var\(\s*--(?:brand|market|risk|system|agent|execution)-[a-z0-9-]+\s*\)/i.test(value) ||
		/\bcurrentColor\b/i.test(value)
	);
}

function hasNeutralStructuralShadowColor(value: string): boolean {
	return (
		/var\(\s*--(?:neutral|text|surface|overlay|border)-[a-z0-9-]+\s*\)/i.test(value) ||
		/color-mix\(in oklch,\s*var\(\s*--(?:neutral|text|surface|overlay|border)-[a-z0-9-]+\s*\)/i.test(
			value,
		) ||
		/oklch\(\s*(?:0(?:\s+0)?|from\s+var\(\s*--(?:neutral|text|surface|overlay|border)-)/i.test(value)
	);
}

function isInsetBorderShadowLayer(value: string): boolean {
	const lengthPattern = "(-?(?:\\d+(?:\\.\\d+)?px|0))";
	const match = new RegExp(
		`^inset\\s+${lengthPattern}\\s+${lengthPattern}\\s+${lengthPattern}(?:\\s+${lengthPattern})?\\s+(.+?)(?:\\s*!important)?$`,
		"i",
	).exec(value);
	if (!match) return false;

	const [, offsetX, offsetY, blur, spread, color] = match;
	if (offsetX === undefined || offsetY === undefined || blur === undefined || color === undefined) return false;
	if (!isZeroShadowLength(blur) || !isStructuralInsetShadowColor(color)) return false;

	if (isZeroShadowLength(offsetX) && isZeroShadowLength(offsetY) && spread) {
		return /^(?:1(?:\.5)?|2|3|4)px$/i.test(spread);
	}

	return !spread && isSingleInsetEdgeOffset(offsetX, offsetY);
}

function isZeroShadowLength(value: string): boolean {
	return /^(?:0|0px)$/i.test(value);
}

function isSingleInsetEdgeOffset(offsetX: string, offsetY: string): boolean {
	const structuralEdgeLength = /^-?(?:1(?:\.5)?|2|3|4)px$/i;
	return (
		(structuralEdgeLength.test(offsetX) && isZeroShadowLength(offsetY)) ||
		(isZeroShadowLength(offsetX) && structuralEdgeLength.test(offsetY))
	);
}

function isStructuralInsetShadowColor(value: string): boolean {
	if (hasDecorativeSemanticShadowColor(value)) return false;

	return /(?:var\(\s*--(?:(?:interaction|border|surface|text|overlay|neutral)-[a-z0-9-]+|heat-(?:line|(?:up|down)-line-\d+))\s*\)|color-mix\(in oklch,\s*var\(\s*--(?:(?:interaction|border|surface|text|overlay|neutral)-[a-z0-9-]+|heat-(?:line|(?:up|down)-line-\d+))\s*\)[^)]+\))(?:\s*!important)?$/i.test(
		value,
	);
}

function isSpreadOnlyRingShadowLayer(value: string): boolean {
	return /^0\s+0\s+0\s+(?:1(?:\.5)?|2|3|4)px\s+/i.test(value);
}

function isSingleEdgeShadowLayer(value: string): boolean {
	return /^(?:0\s+1px\s+0|0\s+-1px\s+0|1px\s+0\s+0|-1px\s+0\s+0)\s+(?:var\(\s*--[a-z0-9-]+\s*\)|color-mix\(in oklch,\s*var\(\s*--[a-z0-9-]+\s*\)[^)]+\))(?:\s*!important)?$/i.test(
		value,
	);
}

function isStructuralRingSelector(selector: string): boolean {
	return (
		!/(?:^|\s)\.[a-z0-9-]*(?:decorative|ambient|wash|glow)[a-z0-9-]*(?:::before|::after)?\b/i.test(selector) &&
		!/\.dot(?:[.#:[\s]|$)/i.test(selector) &&
		!/\.point(?:[.#:[\s]|$)/i.test(selector) &&
		(/:(?:hover|active|focus-within)\b/i.test(selector) ||
			/\b(?:active|selected|current|checked|pressed|dragging|accepted|blocked|unread)\b/i.test(selector) ||
			/\.(?:is-|has-)?(?:active|selected|current|checked|pressed|dragging|accepted|blocked|unread)\b/i.test(
				selector,
			) ||
			/\[(?:aria|data)-(?:selected|current|checked|pressed|active|dragging|impact|corr)(?:=["']?[a-z0-9-]+["']?)?\]/i.test(
				selector,
			) ||
			/\b(?:border|outline|ring|separator|resize|handle|control|button|btn|tab|chip|filter|segment|option|input|switch|toggle|row|cell|item|panel|card|surface|tray|bar|rail)\b/i.test(
				selector,
			))
	);
}

function isStructuralRingColor(value: string): boolean {
	return /(?:var\(\s*--(?:(?:interaction-(?:focus-ring|focus-border|selected-border|dragging-border))|(?:(?:surface|border|text|overlay|brand|market|risk|system|agent|execution)-[a-z0-9-]+))\s*\)|color-mix\(in oklch,\s*var\(\s*--(?:(?:interaction-(?:focus-ring|focus-border|selected-border|dragging-border))|(?:(?:surface|border|text|overlay|brand|market|risk|system|agent|execution)-[a-z0-9-]+))\s*\)[^)]+\))(?:\s*!important)?$/i.test(
		value,
	);
}

function isStructuralSpreadRingShadowLayer(selector: string, value: string): boolean {
	return isSpreadOnlyRingShadowLayer(value) && isStructuralRingSelector(selector) && isStructuralRingColor(value);
}

function isStructuralSingleEdgeShadowLayer(selector: string, value: string): boolean {
	return isSingleEdgeShadowLayer(value) && isStructuralRingSelector(selector);
}

function isNeutralStructuralElevationShadowLayer(value: string): boolean {
	const match =
		/^0\s+(?:1|2|4|8|12)px\s+(?:0|3|4|6|8|12|16|24|32|40)px(?:\s+-?\d+(?:\.\d+)?px)?\s+(.+?)(?:\s*!important)?$/i.exec(
			value,
		);
	if (!match) return false;

	const color = match[1];
	if (color === undefined) return false;
	return !hasDecorativeSemanticShadowColor(color) && hasNeutralStructuralShadowColor(color);
}

function isAllowedRailActiveGlowLayer(selector: string, value: string): boolean {
	return (
		/\.rail-icon\.active::before\b/.test(selector) &&
		/^0\s+0\s+(?:4|6)px(?:\s+-?1px)?\s+(?:var\(\s*--brand-signature-indicator-shadow\s*\)|color-mix\(in oklch,\s*var\(\s*--(?:brand-accent|brand-signature-fg)\s*\)\s+\d+%,\s*transparent\))$/i.test(
			value,
		)
	);
}

function isStatusDotGlowSelector(selector: string): boolean {
	return (
		/\.live-dot\b/i.test(selector) ||
		/\.status-dot\.(?:live|is-live)\b/i.test(selector) ||
		/\.status-dot\b[^{,]*\[(?:data-state|data-status)=["']?live["']?\]/i.test(selector) ||
		/\.session-dot\.live\b/i.test(selector)
	);
}

function isAllowedStatusDotGlowLayer(selector: string, value: string): boolean {
	return (
		isStatusDotGlowSelector(selector) &&
		/^(?:0\s+0\s+(?:4|6)px(?:\s+-?\d+px)?|0\s+0\s+0\s+(?:1|2)px)\s+(?:var\(\s*--(?:system-healthy-fg|brand-accent)\s*\)|color-mix\(in oklch,\s*var\(\s*--(?:system-healthy-fg|brand-accent)\s*\)\s+\d+%,\s*transparent\))$/i.test(
			value,
		)
	);
}

function isAllowedPrimaryCtaHoverLayer(selector: string, value: string): boolean {
	return (
		/(?:\.decision-cta\.primary|\.btn-primary|\.primary-cta|\.detail-action\.primary|\.batch-btn\.primary|\.batch-action-btn\.accent)/i.test(
			selector,
		) &&
		/:(?:hover|active)\b/i.test(selector) &&
		/^(?:0\s+0\s+0\s+(?:1(?:\.5)?|2)px|0\s+2px\s+8px)\s+(?:var\(\s*--(?:brand-accent|interaction-focus-ring|interaction-selected-border)\s*\)|color-mix\(in oklch,\s*var\(\s*--brand-accent\s*\)\s+\d+%,\s*transparent\))$/i.test(
			value,
		)
	);
}

function isGlowBudgetAllowedBoxShadow(
	selector: string,
	value: string,
	customProperties = new Map<string, string>(),
): boolean {
	const normalizedValue = value.replace(/\s+/g, " ").trim();
	if (/^none(?:\s*!important)?$/i.test(normalizedValue)) return true;

	const layers = splitCssList(normalizedValue);
	return (
		layers.length > 0 &&
		layers.every((layer) => isGlowBudgetAllowedBoxShadowLayer(selector, layer, customProperties))
	);
}

function hasDecorativeGlowColor(value: string): boolean {
	return (
		/color-mix\(in oklch,\s*(?:var\(\s*--(?:brand|market|risk|system|agent|execution|text)-|currentColor)/i.test(value) ||
		/var\(\s*--(?:brand|market|risk|system|agent|execution|text)-[a-z0-9-]+\s*\)/i.test(value) ||
		/var\(\s*--brand-signature-glow\s*\)/i.test(value) ||
		/\bcurrentColor\b/i.test(value)
	);
}

function hasRadialGlowLayer(value: string): boolean {
	return /(?:^|,)\s*0\s+0\s+(?:[4-9]|\d{2,})px(?:\s+-?\d+(?:\.\d+)?px)?(?:\s|$)/i.test(value);
}

function hasDecorativeRadialGlow(value: string): boolean {
	return hasDecorativeGlowColor(value) && hasRadialGlowLayer(value);
}

function hasPositionEdgeDeclaration(value: string, edge: "top" | "right" | "bottom" | "left"): boolean {
	return new RegExp(`\\b${edge}\\s*:`, "i").test(value);
}

function hasDecorativeGradientBackground(value: string): boolean {
	return (
		/\bbackground(?:-image)?\s*:[^;]*\b(?:linear|radial)-gradient\(/i.test(value) &&
		/var\(\s*--(?:brand|market|risk|system|agent|execution)-[a-z0-9-]+\s*\)/i.test(value) &&
		/\btransparent\b/i.test(value)
	);
}

function isAllowedAmbientGradientRule(selector: string): boolean {
	return (
		/\.rail-icon\.active::before\b/i.test(selector) ||
		(isStatusDotGlowSelector(selector) && /::(?:before|after)\b/i.test(selector)) ||
		/(?:\.decision-cta\.primary|\.btn-primary|\.primary-cta)[^,{]*:(?:hover|active)\b/i.test(selector)
	);
}

function isPositionedEdgeAdjacentRule(value: string): boolean {
	const isPositioned = /\bposition\s*:\s*(?:absolute|fixed|sticky)\b/i.test(value);
	const usesInset = /\binset(?:-[a-z]+)?\s*:/i.test(value);
	const touchesHorizontalEdge = hasPositionEdgeDeclaration(value, "left") || hasPositionEdgeDeclaration(value, "right");
	const touchesVerticalEdge = hasPositionEdgeDeclaration(value, "top") || hasPositionEdgeDeclaration(value, "bottom");

	return isPositioned && (usesInset || (touchesHorizontalEdge && touchesVerticalEdge));
}

function hasDecorativeAmbientGradientRule(rule: CssRule): boolean {
	const normalizedSelector = rule.selector.replace(/\s+/g, " ").trim();
	const normalizedBody = rule.body.replace(/\s+/g, " ").trim();
	const hasPseudoSelector = /::(?:before|after)\b/i.test(normalizedSelector);
	const isDecorativeCandidate = hasPseudoSelector || isPositionedEdgeAdjacentRule(normalizedBody);

	return (
		isDecorativeCandidate &&
		hasDecorativeGradientBackground(normalizedBody) &&
		!isAllowedAmbientGradientRule(normalizedSelector)
	);
}

function isDecorativeRadialGlowLayer(
	selector: string,
	layer: string,
	customProperties: Map<string, string>,
): boolean {
	const resolvedShadowToken = resolveShadowTokenLayer(layer, customProperties);
	if (!resolvedShadowToken) return hasDecorativeRadialGlow(layer);
	if (isGlowBudgetAllowedBoxShadow(selector, resolvedShadowToken, customProperties)) return false;

	return splitCssList(resolvedShadowToken).some((resolvedLayer) => hasDecorativeRadialGlow(resolvedLayer));
}

function isDisallowedDecorativeSemanticShadowLayer(
	selector: string,
	layer: string,
	customProperties: Map<string, string>,
): boolean {
	const resolvedShadowToken = resolveShadowTokenLayer(layer, customProperties);
	const layers = resolvedShadowToken ? splitCssList(resolvedShadowToken) : [layer];

	return layers.some((candidate) => {
		if (isGlowBudgetAllowedBoxShadowLayer(selector, candidate, customProperties)) return false;
		return hasDecorativeSemanticShadowColor(candidate);
	});
}

function isExcessiveGlowBoxShadow(
	selector: string,
	value: string,
	customProperties = new Map<string, string>(),
): boolean {
	if (isGlowBudgetAllowedBoxShadow(selector, value, customProperties)) return false;

	const normalizedValue = value.replace(/\s+/g, " ").trim();
	if (/\[data-[a-z0-9-]*glow[a-z0-9-]*\]/i.test(selector)) return true;

	return splitCssList(normalizedValue).some((layer) =>
		isDecorativeRadialGlowLayer(selector, layer, customProperties) ||
		isDisallowedDecorativeSemanticShadowLayer(selector, layer, customProperties),
	);
}

function isExcessiveDropShadowFilter(selector: string, value: string): boolean {
	const dropShadowLayers = readCssFunctionArguments(value, "drop-shadow");
	if (dropShadowLayers.length === 0) return false;

	return dropShadowLayers.some((layer) => !isAllowedStatusDotGlowLayer(selector, layer.replace(/\s+/g, " ").trim()));
}

function hasForbiddenDataGlowReference(value: string): boolean {
	return /\bdata-[a-z0-9-]*glow[a-z0-9-]*\b/i.test(value);
}

function collectGlowBudgetCssViolations(source: CssSource): string[] {
	const violations: string[] = [];
	const css = stripCssComments(source.css);
	const shadowCustomProperties = extractShadowCustomPropertyValues(css);

	for (const match of css.matchAll(/\btext-shadow\s*:\s*([^;}]+)/gi)) {
		const value = match[1]?.trim();
		if (value === undefined) continue;
		if (!/^none(?:\s*!important)?$/i.test(value)) {
			violations.push(`${source.label}:${getLineNumber(css, match.index)}:text-shadow`);
		}
	}

	for (const match of css.matchAll(/\bambient-[a-z0-9-]+/gi)) {
		violations.push(`${source.label}:${getLineNumber(css, match.index)}:${match[0]}`);
	}

	for (const match of css.matchAll(/(--[a-z0-9-]*glow[a-z0-9-]*)\s*:/gi)) {
		violations.push(`${source.label}:${getLineNumber(css, match.index)}:prototype-glow-token:${match[1]}`);
	}

	for (const rule of readTopLevelCssRules(css)) {
		const selector = formatCssRuleSelector(rule);
		if (hasForbiddenDataGlowReference(selector)) {
			violations.push(`${source.label}:${getLineNumber(css, rule.start)}:data-glow-selector:${selector}`);
		}
		if (hasForbiddenDataGlowReference(rule.body)) {
			violations.push(`${source.label}:${getLineNumber(css, rule.start)}:data-glow-body:${selector}`);
		}
		if (hasDecorativeAmbientGradientRule(rule)) {
			violations.push(`${source.label}:${getLineNumber(css, rule.start)}:ambient-gradient:${selector}`);
		}

		for (const match of rule.body.matchAll(/box-shadow\s*:\s*([^;]+)/gi)) {
			const value = match[1]?.trim();
			if (value === undefined) continue;
			if (
				!/^none(?:\s*!important)?$/i.test(value) &&
				(/^@keyframes\b/i.test(rule.selector) ||
					isExcessiveGlowBoxShadow(rule.selector, value, shadowCustomProperties))
			) {
				violations.push(`${source.label}:${getLineNumber(css, rule.start)}:box-shadow:${selector}`);
			}
		}

		for (const match of rule.body.matchAll(/(?:^|[;\s])filter\s*:\s*([^;]+)/gi)) {
			const value = match[1]?.trim();
			if (value === undefined) continue;
			if (!/^none(?:\s*!important)?$/i.test(value) && isExcessiveDropShadowFilter(rule.selector, value)) {
				violations.push(`${source.label}:${getLineNumber(css, rule.start)}:filter-drop-shadow:${selector}`);
			}
		}
	}

	return violations;
}

function collectGlowBudgetHtmlViolations(source: HtmlSource): string[] {
	const violations: string[] = [];

	for (const match of source.html.matchAll(/\bambient-[a-z0-9-]+\b/gi)) {
		violations.push(`${source.label}:${getLineNumber(source.html, match.index)}:${match[0]}`);
	}

	for (const match of source.html.matchAll(/\s(data-[a-z0-9-]*glow[a-z0-9-]*)(?=\s|=|\/?>)/gi)) {
		violations.push(`${source.label}:${getLineNumber(source.html, match.index)}:data-glow-marker:${match[1]}`);
	}

	for (const match of source.html.matchAll(/<filter\b([^>]*)>([\s\S]*?)<\/filter>/gi)) {
		const attributes = match[1];
		const body = match[2];
		if (attributes === undefined || body === undefined) continue;
		const filterId = /\bid\s*=\s*(["'])([^"']+)\1/i.exec(attributes)?.[2] ?? "anonymous-filter";
		const line = getLineNumber(source.html, match.index);

		if (/\bglow\b|(?:^|[-_])glow(?:[-_]|$)/i.test(filterId)) {
			violations.push(`${source.label}:${line}:svg-filter-glow-id:${filterId}`);
		}
		if (/<feGaussianBlur\b/i.test(body)) {
			violations.push(`${source.label}:${line}:svg-feGaussianBlur:${filterId}`);
		}
	}

	for (const match of source.html.matchAll(/\bfilter\s*=\s*(["'])\s*url\(#([^"')]*glow[^"')]*)\)\s*\1/gi)) {
		violations.push(`${source.label}:${getLineNumber(source.html, match.index)}:svg-filter-url:${match[2]}`);
	}

	for (const match of source.html.matchAll(/url\(#([^"')]*glow[^"')]*)\)/gi)) {
		violations.push(`${source.label}:${getLineNumber(source.html, match.index)}:svg-url-glow:${match[1]}`);
	}

	return [...new Set(violations)];
}

function collectGlowBudgetSharedTextViolations(source: TextSource): string[] {
	const violations: string[] = [];
	const markerPatterns: Array<{ pattern: RegExp; reason: string }> = [
		{ pattern: /\bdata-[a-z0-9-]*glow[a-z0-9-]*\b/gi, reason: "data-glow-runtime" },
		{ pattern: /\bMouseGlow\b/g, reason: "mouse-glow-module" },
		{ pattern: /\b--_glow-[a-z0-9-]+\b/gi, reason: "mouse-glow-custom-property" },
		{ pattern: /radial-gradient\s*\([\s\S]{0,320}?\bglow\b/gi, reason: "radial-gradient-glow-runtime" },
		{ pattern: /\bfeGaussianBlur\b/gi, reason: "svg-feGaussianBlur-runtime" },
		{ pattern: /\b(?:filter|url)\s*\([^)]*\bglow\b[^)]*\)/gi, reason: "glow-filter-runtime" },
	];

	for (const { pattern, reason } of markerPatterns) {
		for (const match of source.text.matchAll(pattern)) {
			violations.push(`${source.label}:${getLineNumber(source.text, match.index)}:${reason}:${match[0]}`);
		}
	}

	return [...new Set(violations)];
}

describe("prototype design consistency", () => {
	it("classifies glow budget box-shadow edge cases without allowing decorative ambient glow", () => {
		expect(isExcessiveGlowBoxShadow(".panel", "var(--shadow-lg)")).toBe(false);
		expect(
			isExcessiveGlowBoxShadow(
				".panel",
				"var(--shadow-lg), 0 0 32px color-mix(in oklch, var(--brand-accent) 30%, transparent)",
			),
		).toBe(true);
		expect(
			isExcessiveGlowBoxShadow(
				".resize-separator:focus-visible",
				"0 0 0 2px var(--interaction-focus-ring)",
			),
		).toBe(false);
		expect(
			isExcessiveGlowBoxShadow(
				".metric-card:hover",
				"0 0 14px color-mix(in oklch, var(--brand-accent) 12%, transparent)",
			),
		).toBe(true);
		expect(isExcessiveGlowBoxShadow(".metric-card:hover", "0 0 12px var(--brand-accent-subtle)")).toBe(true);
		expect(
			isExcessiveGlowBoxShadow(
				".metric-card:hover",
				"0 2px 8px color-mix(in oklch, var(--neutral-0) 16%, transparent)",
			),
		).toBe(false);
		expect(isExcessiveGlowBoxShadow(".decorative-card::after", "0 0 0 4px var(--brand-accent)")).toBe(true);
		expect(
			isExcessiveGlowBoxShadow(
				".hero-wash",
				"0 12px 40px color-mix(in oklch, var(--brand-accent) 20%, transparent)",
			),
		).toBe(true);
		expect(isExcessiveGlowBoxShadow(".resize-separator", "inset 0 0 0 1px var(--border-subtle)")).toBe(false);
		expect(isExcessiveGlowBoxShadow(".resize-separator", "inset 0 0 0 2px var(--border-default)")).toBe(false);
		expect(isExcessiveGlowBoxShadow(".selected-row", "inset 2px 0 0 var(--interaction-selected-border)")).toBe(
			false,
		);
		expect(isExcessiveGlowBoxShadow(".decorative-card", "inset 0 0 24px 6px var(--brand-accent)")).toBe(
			true,
		);
		expect(isExcessiveGlowBoxShadow(".status-card", "inset 0 0 12px var(--system-healthy-fg)")).toBe(true);
		expect(
			isExcessiveGlowBoxShadow(
				".resize-separator:focus-visible",
				"0 0 0 2px var(--interaction-focus-ring), 0 0 8px color-mix(in oklch, var(--brand-accent) 30%, transparent)",
			),
		).toBe(true);
		expect(
			isExcessiveGlowBoxShadow(
				".rail-icon.active::before",
				"0 0 4px color-mix(in oklch, var(--brand-accent) 30%, transparent)",
			),
		).toBe(false);
		expect(
			isExcessiveGlowBoxShadow(
				".rail-icon.active::before",
				"0 0 4px color-mix(in oklch, var(--brand-accent) 30%, transparent), 0 0 20px color-mix(in oklch, var(--brand-accent) 14%, transparent)",
			),
		).toBe(true);
		expect(isExcessiveGlowBoxShadow(".rail-icon.active::before", "0 0 4px var(--brand-signature-glow)")).toBe(
			true,
		);
		expect(
			isExcessiveGlowBoxShadow(
				".status-dot.live",
				"0 0 6px color-mix(in oklch, var(--system-healthy-fg) 30%, transparent)",
			),
		).toBe(false);
		expect(
			isExcessiveGlowBoxShadow(
				".status-dot.live",
				"0 0 6px color-mix(in oklch, var(--system-healthy-fg) 30%, transparent), 0 0 18px color-mix(in oklch, var(--system-healthy-fg) 16%, transparent)",
			),
		).toBe(true);
		expect(isExcessiveGlowBoxShadow(".health-metric-dot.healthy", "0 0 6px var(--system-healthy-fg)")).toBe(
			true,
		);
		expect(isExcessiveGlowBoxShadow(".rule-dot.warn", "0 0 6px var(--risk-near-limit-fg)")).toBe(true);
		expect(isExcessiveGlowBoxShadow(".decorative .dot", "0 0 6px var(--brand-accent)")).toBe(true);
		expect(isExcessiveGlowBoxShadow(".decorative .dot", "0 0 12px var(--brand-accent)")).toBe(true);
		expect(
			isExcessiveGlowBoxShadow(
				".trace-item:hover .dot",
				"0 0 0 3px color-mix(in oklch, var(--brand-accent) 15%, transparent)",
			),
		).toBe(true);
		expect(
			isExcessiveGlowBoxShadow(
				".point.accepted",
				"0 0 0 4px color-mix(in oklch, var(--system-healthy-fg) 18%, transparent)",
			),
		).toBe(true);
		expect(
			isExcessiveGlowBoxShadow(
				".topo-node",
				"0 0 4px -1px color-mix(in oklch, var(--system-healthy-fg) 40%, transparent)",
			),
		).toBe(true);
		expect(
			isExcessiveGlowBoxShadow(
				".topo-node.topo-ok",
				"0 0 4px -1px color-mix(in oklch, var(--system-healthy-fg) 40%, transparent)",
			),
		).toBe(true);
		expect(
			isExcessiveGlowBoxShadow(
				".decision-cta.primary:hover",
				"0 0 0 1px color-mix(in oklch, var(--brand-accent) 30%, transparent)",
			),
		).toBe(false);
		expect(
			isExcessiveGlowBoxShadow(
				".decision-cta.primary:hover",
				"0 0 0 1px color-mix(in oklch, var(--brand-accent) 30%, transparent), 0 0 12px color-mix(in oklch, var(--brand-accent) 12%, transparent)",
			),
		).toBe(true);
	});

	it("collects glow budget violations from css selectors and declaration bodies", () => {
		const violations = collectGlowBudgetCssViolations({
			label: "fixture.css",
			css: `
				.metric[data-mouse-glow-color] { color: var(--text-primary); }
				.metric-body { content: "data-mouse-glow-size"; }
				.metric-ambient { box-shadow: 0 0 12px var(--brand-accent-subtle); }
				.decorative .dot { box-shadow: 0 0 12px var(--brand-accent); }
				.health-metric-dot.healthy { box-shadow: 0 0 6px var(--system-healthy-fg); }
				.rule-dot.warn { box-shadow: 0 0 6px var(--risk-near-limit-fg); }
				.topo-node.topo-ok { box-shadow: 0 0 4px -1px color-mix(in oklch, var(--system-healthy-fg) 40%, transparent); }
				.status-dot.live { box-shadow: 0 0 6px var(--system-healthy-fg); }
				.health-metric-dot.degraded { filter: drop-shadow(0 0 6px var(--system-healthy-fg)); }
				.status-dot.live[data-state="live"] { filter: drop-shadow(0 0 6px var(--system-healthy-fg)); }
				.decorative-card::after { box-shadow: 0 0 0 4px var(--brand-accent); }
				.hero-wash { box-shadow: 0 12px 40px color-mix(in oklch, var(--brand-accent) 20%, transparent); }
				.shell-custom::after {
					content: "";
					position: absolute;
					top: 0;
					left: 0;
					right: 0;
					height: 4px;
					background: linear-gradient(
						90deg,
						transparent 0%,
						color-mix(in oklch, var(--brand-accent) 20%, transparent) 50%,
						transparent 100%
					);
				}
				.shell-wash::before {
					content: "";
					position: absolute;
					top: 0;
					left: 0;
					right: 0;
					height: 32px;
					background: linear-gradient(
						180deg,
						color-mix(in oklch, var(--brand-accent) 6%, transparent) 0%,
						transparent 100%
					);
				}
				.shell-bottom::after {
					content: "";
					position: absolute;
					left: 0;
					right: 0;
					bottom: -1px;
					height: 1px;
					background: linear-gradient(
						90deg,
						transparent 0%,
						color-mix(in oklch, var(--brand-signature-line) 25%, transparent) 50%,
						transparent 100%
					);
				}
				.shell-left::before {
					content: "";
					position: absolute;
					left: 0;
					top: 0;
					bottom: 0;
					width: 8px;
					background: linear-gradient(
						180deg,
						color-mix(in oklch, var(--brand-accent) 12%, transparent) 0%,
						transparent 100%
					);
				}
				.shell-right::after {
					content: "";
					position: absolute;
					right: 0;
					top: 0;
					bottom: 0;
					width: 12px;
					background: linear-gradient(
						180deg,
						color-mix(in oklch, var(--execution-filled-fg) 12%, transparent) 0%,
						transparent 100%
					);
				}
				.shell-full-wash::before {
					content: "";
					position: absolute;
					inset: 0;
					background: linear-gradient(
						180deg,
						color-mix(in oklch, var(--brand-accent) 6%, transparent) 0%,
						transparent 140px
					);
				}
				.shell-offset-radial-top::before {
					content: "";
					position: absolute;
					top: -40px;
					left: 20%;
					right: 20%;
					height: 80px;
					background: radial-gradient(
						ellipse at center,
						color-mix(in oklch, var(--brand-signature-fg) 4%, transparent) 0%,
						transparent 70%
					);
				}
				.shell-offset-radial-bottom::after {
					content: "";
					position: absolute;
					bottom: 0;
					left: 10%;
					right: 10%;
					height: 60px;
					background: radial-gradient(
						ellipse at center bottom,
						color-mix(in oklch, var(--brand-signature-fg) 3%, transparent) 0%,
						transparent 70%
					);
				}
				.shell-offset-left-wash::before {
					content: "";
					position: absolute;
					top: 0;
					left: -20px;
					bottom: 0;
					width: 40px;
					background: linear-gradient(
						to right,
						transparent,
						color-mix(in oklch, var(--brand-signature-fg) 2%, transparent) 50%,
						transparent
					);
				}
				.header-title::after {
					content: "";
					position: absolute;
					bottom: -4px;
					left: 0;
					width: 200%;
					height: 2px;
					background: linear-gradient(
						90deg,
						color-mix(in oklch, var(--brand-accent) 70%, transparent) 0%,
						var(--brand-accent) 15%,
						transparent 100%
					);
				}
				:root:has(#trading-mode:checked) label[for="trading-mode"]::after {
					content: "";
					position: absolute;
					bottom: -1px;
					left: 20%;
					right: 20%;
					height: 2px;
					background: linear-gradient(
						90deg,
						transparent,
						color-mix(in oklch, var(--brand-accent) 60%, transparent),
						var(--brand-accent),
						transparent
					);
				}
				@keyframes decorative-pulse {
					50% { box-shadow: 0 0 12px color-mix(in oklch, var(--brand-accent) 30%, transparent); }
				}
				@media (prefers-reduced-motion: reduce) {
					.motion-ambient { box-shadow: 0 0 16px color-mix(in oklch, var(--brand-accent) 18%, transparent); }
				}
				@media (max-height: 800px) {
					.height-ambient { box-shadow: 0 0 18px var(--brand-accent-subtle); }
				}
				@supports (container-type: inline-size) {
					.supports-ambient { box-shadow: 0 0 20px color-mix(in oklch, var(--brand-accent) 18%, transparent); }
				}
				@container shell (min-width: 720px) {
					.container-ambient { box-shadow: 0 0 22px var(--brand-accent-subtle); }
				}
			`,
		});

		expect(violations).toEqual(
			expect.arrayContaining([
				expect.stringContaining("data-glow-selector"),
				expect.stringContaining("data-glow-body"),
				expect.stringContaining("box-shadow"),
				expect.stringContaining("box-shadow:.decorative-card::after"),
				expect.stringContaining("box-shadow:.hero-wash"),
				expect.stringContaining("box-shadow:.health-metric-dot.healthy"),
				expect.stringContaining("box-shadow:.rule-dot.warn"),
				expect.stringContaining("box-shadow:.topo-node.topo-ok"),
				expect.stringContaining("filter-drop-shadow:.health-metric-dot.degraded"),
				expect.stringContaining("ambient-gradient"),
				expect.stringContaining("@keyframes decorative-pulse"),
				expect.stringContaining("ambient-gradient:.shell-offset-radial-top::before"),
				expect.stringContaining("ambient-gradient:.shell-offset-radial-bottom::after"),
				expect.stringContaining("ambient-gradient:.shell-offset-left-wash::before"),
				expect.stringContaining("ambient-gradient:.header-title::after"),
				expect.stringContaining('ambient-gradient::root:has(#trading-mode:checked) label[for="trading-mode"]::after'),
				expect.stringContaining("box-shadow:@media (prefers-reduced-motion: reduce) .motion-ambient"),
				expect.stringContaining("box-shadow:@media (max-height: 800px) .height-ambient"),
				expect.stringContaining("box-shadow:@supports (container-type: inline-size) .supports-ambient"),
				expect.stringContaining("box-shadow:@container shell (min-width: 720px) .container-ambient"),
			]),
		);
		expect(violations.filter((violation) => violation.includes(":ambient-gradient:"))).toHaveLength(11);
	});

	it("resolves page-local shadow tokens before applying the glow budget allowlist", () => {
		expect(
			collectGlowBudgetCssViolations({
				label: "fixture.css",
				css: `
					:root {
						--shadow-ambient: 0 0 32px var(--brand-accent);
						--shadow-structural: 0 2px 8px color-mix(in oklch, var(--neutral-0) 16%, transparent);
					}
					.token-card { box-shadow: var(--shadow-ambient); }
					.structural-card { box-shadow: var(--shadow-structural); }
					.legacy-panel { box-shadow: var(--shadow-lg); }
				`,
			}),
		).toEqual(["fixture.css:5:box-shadow:.token-card"]);
	});

	it("collects prototype-only glow token definitions from shared css", () => {
		expect(
			collectGlowBudgetCssViolations({
				label: "tokens-style.css",
				css: `
					:root {
						--brand-signature-glow: oklch(from var(--brand-signature-fg) l c h / 0.60);
						--sidebar-glow-height: 4px;
					}
				`,
			}),
		).toEqual([
			"tokens-style.css:3:prototype-glow-token:--brand-signature-glow",
			"tokens-style.css:4:prototype-glow-token:--sidebar-glow-height",
		]);
	});

	it("collects glow budget violations from svg glow filters in raw html", () => {
		const violations = collectGlowBudgetHtmlViolations({
			label: "fixture.html",
			html: `
				<svg viewBox="0 0 100 20">
					<defs>
						<linearGradient id="safe-gradient">
							<stop offset="0%" stop-color="currentColor"/>
						</linearGradient>
						<filter id="line-glow">
							<feGaussianBlur in="SourceGraphic" stdDeviation="1.5" result="blur"/>
						</filter>
					</defs>
					<polyline points="0,8 100,10" filter="url(#line-glow)"/>
				</svg>
			`,
		});

		expect(violations).toEqual(
			expect.arrayContaining([
				expect.stringContaining("svg-filter-glow-id:line-glow"),
				expect.stringContaining("svg-feGaussianBlur:line-glow"),
				expect.stringContaining("svg-filter-url:line-glow"),
			]),
		);
	});

	it("collects glow budget violations from data attribute markers in raw html", () => {
		const violations = collectGlowBudgetHtmlViolations({
			label: "fixture.html",
			html: `
				<div data-glow></div>
				<div data-mouse-glow-size="160px"></div>
				<script>
					const inertFixture = "data-glow";
				</script>
			`,
		});

		expect(violations).toEqual([
			"fixture.html:2:data-glow-marker:data-glow",
			"fixture.html:3:data-glow-marker:data-mouse-glow-size",
		]);
	});

	it("does not flag ordinary non-glow svg definitions", () => {
		const violations = collectGlowBudgetHtmlViolations({
			label: "fixture.html",
			html: `
				<svg viewBox="0 0 100 20">
					<defs>
						<linearGradient id="area-gradient">
							<stop offset="0%" stop-color="currentColor"/>
						</linearGradient>
						<filter id="noise-filter">
							<feTurbulence type="fractalNoise" baseFrequency="0.8"/>
						</filter>
					</defs>
					<rect fill="url(#area-gradient)" filter="url(#noise-filter)"/>
				</svg>
			`,
		});

		expect(violations).toEqual([]);
	});

	it("keeps exactly 28 active route prototypes", () => {
		const activePages = readManifest().pages.filter(isActiveRoutePrototype);

		expect(activePages).toHaveLength(expectedActiveRoutePrototypeCount);
	});

	it("keeps audited prototype pages active in the manifest", () => {
		const manifestFiles = new Set(activePages().map((page) => page.file));
		const inactive = auditedPrototypeFiles.filter((file) => !manifestFiles.has(file));

		expect(inactive).toEqual([]);
	});

	it("keeps active prototype landing status in sync with page contracts", () => {
		const violations: string[] = [];

		for (const page of activePages()) {
			const contract = findPrimaryContract(page);

			if (!contract) {
				if (
					!retiredRoutePrototypeIds.has(page.id) ||
					page.landing?.reactRouteStatus !== "superseded" ||
					page.landing.contractStatus !== "retired" ||
					page.landing.reactParityVerified !== false
				) {
					violations.push(`${page.id}:missing-current-contract-without-retirement`);
				}
				continue;
			}

			if (typeof page.landing?.prototypeVerified !== "boolean") {
				violations.push(`${page.id}:invalid-prototype-verification`);
				continue;
			}

			if (typeof page.landing.reactParityVerified !== "boolean") {
				violations.push(`${page.id}:invalid-react-parity-verification`);
				continue;
			}

			for (const field of landingSyncFields) {
				const manifestValue = page.landing?.[field];
				const contractValue = contract.landing?.[field];

				if (manifestValue !== contractValue) {
					violations.push(
						`${page.id}:${field}:manifest-${manifestValue ?? "missing"}:contract-${
							contractValue ?? "missing"
						}`,
					);
				}
			}
		}

		expect(violations).toEqual([]);
	});

	it("records prototype status explicitly and limits parity claims to verified current contracts", () => {
		const violations: string[] = [];

		for (const page of activePages()) {
			const contract = findPrimaryContract(page);
			const manifestStatus = page.landing?.prototypeVerified;
			const manifestParity = page.landing?.reactParityVerified;

			if (typeof manifestStatus !== "boolean") {
				violations.push(`${page.id}:manifest:${manifestStatus ?? "missing"}`);
			}
			if (typeof manifestParity !== "boolean") {
				violations.push(`${page.id}:manifest-parity:${manifestParity ?? "missing"}`);
			}
			if (
				manifestParity === true &&
				(page.landing?.contractStatus !== "verified" ||
					contract?.landing?.prototypeVerified !== true ||
					contract.landing.reactParityVerified !== true ||
					contract.landing.contractStatus !== "verified")
			) {
				violations.push(`${page.id}:parity-without-verified-current-contract`);
			}
		}

		expect(violations).toEqual([]);
	});

	it("keeps Agent Console v2 as the only active canonical prototype", () => {
		const agentConsolePages = readManifest().pages.filter((page) =>
			page.id.startsWith("agent-console"),
		);
		const activeAgentConsolePages = agentConsolePages.filter(isActiveRoutePrototype);
		const canonicalContracts = readContracts().filter((contract) =>
			["agent-approvals", "research-agent-lab", "system-agent-ops"].includes(contract.id),
		);

		expect(activeAgentConsolePages.map((page) => page.file)).toEqual([
			"page-agent-console-v2.html",
		]);
		const legacyAgentConsole = agentConsolePages.find((page) => page.id === "agent-console");
		expect(legacyAgentConsole?.status).toBe("removed-specimen");
		expect(legacyAgentConsole?.file).toBe("");
		expect(existsSync(join(prototypesDir, "page-agent-console.html"))).toBe(false);
		expect(canonicalContracts.map((contract) => contract.id).sort()).toEqual([
			"agent-approvals",
			"research-agent-lab",
			"system-agent-ops",
		]);
		for (const contract of canonicalContracts) {
			expect(contract.prototypeRef).toBe(
				"docs/designs/specs/prototypes/page-agent-console-v2.html",
			);
			expect(contract.nextPrototypeRef).toBeUndefined();
			expect(contract.nextSlots).toBeUndefined();
			expect(contract.nextOverlays).toBeUndefined();
		}
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
			if (region === undefined) {
				violations.push(`${page.id}:primary-answer-missing-after-count-check`);
				continue;
			}
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

	it("keeps page-local keyframes covered by targeted reduced motion", () => {
		const sharedReducedMotionCss = getMediaBlocksMatching(
			readFileSync(join(prototypesDir, "shared/layout-state.css"), "utf8"),
			/prefers-reduced-motion\s*:\s*reduce/i,
		).join("\n");
		const violations: string[] = [];

		for (const page of activePages()) {
			const css = getStyleBlocks(readPrototypeHtml(page));
			const reducedMotionCss = getMediaBlocksMatching(css, /prefers-reduced-motion\s*:\s*reduce/i).join("\n");

			for (const family of getKeyframeNames(css)) {
				if (family in dataCriticalInstantMotionExemptions) continue;

				const usages = getAnimationFamilyUsages(css, family);
				if (usages.length === 0) continue;
				if (
					usages.every(
						(usage) =>
							reducedMotionCssCoversUsage(reducedMotionCss, usage) ||
							reducedMotionCssCoversUsage(sharedReducedMotionCss, usage),
					)
				) {
					continue;
				}

				for (const usage of usages) {
					violations.push(`${page.id}:${usage.line}:${family}:${usage.selector}`);
				}
			}
		}

		expect(violations).toEqual([]);
	});

	it("does not treat ancestor reduced-motion selectors as covering child element animations", () => {
		const reducedMotionCss = `
			.regime-state-badge {
				animation: none !important;
			}
		`;
		const childDotUsage = {
			selectors: [".regime-state-badge:hover .regime-state-badge__dot"],
		};

		expect(reducedMotionCssCoversUsage(reducedMotionCss, childDotUsage)).toBe(false);
	});

	it("does not treat transition-only reduced-motion declarations as keyframe coverage", () => {
		const reducedMotionCss = `
			.spinner {
				transition: none !important;
			}
		`;
		const spinnerUsage = {
			selectors: [".spinner"],
		};

		expect(reducedMotionCssCoversUsage(reducedMotionCss, spinnerUsage)).toBe(false);
	});

	it("does not treat iteration-only reduced-motion declarations as keyframe coverage", () => {
		const reducedMotionCss = `
			.spinner {
				animation-iteration-count: 1 !important;
			}
		`;
		const spinnerUsage = {
			selectors: [".spinner"],
		};

		expect(reducedMotionCssCoversUsage(reducedMotionCss, spinnerUsage)).toBe(false);
	});

	it("does not treat shared family name mentions as reduced-motion animation coverage", () => {
		const transitionOnlyCss = `
			/* dot-glow is handled by the page-local owner. */
			.status-dot {
				transition: none !important;
			}
		`;
		const durationCoverageCss = `
			.dot-glow {
				animation-duration: 0.01ms !important;
				animation-iteration-count: 1 !important;
			}
		`;
		const animationCoverageCss = `
			[class*="glow"] {
				animation: none !important;
			}
		`;
		const dotGlowUsage = {
			selectors: [".dot-glow"],
		};

		expect(reducedMotionCssCoversUsage(transitionOnlyCss, dotGlowUsage)).toBe(false);
		expect(reducedMotionCssCoversUsage(durationCoverageCss, dotGlowUsage)).toBe(true);
		expect(reducedMotionCssCoversUsage(animationCoverageCss, dotGlowUsage)).toBe(true);
	});

	it("does not let shared family token overlap bypass usage selector coverage", () => {
		const criticalPulseCss = `
			.dot-critical-pulse {
				animation: none !important;
			}
		`;
		const criticalRingUsage = {
			selectors: [".critical-card"],
		};

		expect(reducedMotionCssCoversUsage(criticalPulseCss, criticalRingUsage)).toBe(false);
	});

	it("does not treat element selectors as covering pseudo-element animations", () => {
		const reducedMotionCss = `
			.alert-dot.critical {
				animation: none !important;
			}
		`;
		const pseudoElementUsage = {
			selectors: [".alert-dot.critical::after"],
		};

		expect(reducedMotionCssCoversUsage(reducedMotionCss, pseudoElementUsage)).toBe(false);
	});

	it("does not treat negated state selectors as covering the opposite state", () => {
		const reducedMotionCss = `
			.task-item:not(.running) {
				animation: none !important;
			}
		`;
		const runningUsage = {
			selectors: [".task-item.running"],
		};

		expect(reducedMotionCssCoversUsage(reducedMotionCss, runningUsage)).toBe(false);
	});

	it("keeps secondary and tertiary context markers from dimming whole regions", () => {
		const css = readFileSync(join(prototypesDir, "shared/layout-components.css"), "utf8");
		const contextSelectors = ["[data-secondary-context]", "[data-tertiary-context]"] as const;
		const violations = contextSelectors.filter((selector) =>
			hasDeclaration(getSelectorRuleBody(css, selector), "opacity", /.+/),
		);

		expect(violations).toEqual([]);
	});

	it("keeps shared faded skeleton opacity out of reduced-motion resets", () => {
		const layoutStateCss = readFileSync(join(prototypesDir, "shared/layout-state.css"), "utf8");
		const reducedMotionCss = getMediaBlocksMatching(layoutStateCss, /prefers-reduced-motion\s*:\s*reduce/i).join(
			"\n",
		);
		const violations = readTopLevelCssRules(stripCssComments(reducedMotionCss))
			.filter((rule) => /opacity\s*:\s*1(?:\s*!important)?\s*;/i.test(rule.body))
			.filter((rule) => rule.selectors.some((selector) => reducedMotionSelectorCoversUsage(selector, ".skeleton.faded")))
			.map((rule) => rule.selector);

		expect(violations).toEqual([]);
	});

	it("keeps layout center helpers out of reduced-motion transform resets", () => {
		const layoutStateCss = readFileSync(join(prototypesDir, "shared/layout-state.css"), "utf8");
		const reducedMotionCss = getMediaBlocksMatching(layoutStateCss, /prefers-reduced-motion\s*:\s*reduce/i).join(
			"\n",
		);
		const centerLayoutSelectors = [".network-center", ".state-centered", ".flex-center"];
		const violations = readTopLevelCssRules(stripCssComments(reducedMotionCss))
			.filter((rule) => /(?:opacity\s*:\s*1|transform\s*:\s*none)(?:\s*!important)?\s*;/i.test(rule.body))
			.flatMap((rule) =>
				centerLayoutSelectors
					.filter((selector) =>
						rule.selectors.some((reducedSelector) => reducedMotionSelectorCoversUsage(reducedSelector, selector)),
					)
					.map((selector) => `${selector}:${rule.selector}`),
			);

		expect(violations).toEqual([]);
	});

	it("keeps the shared reduced-motion baseline centralized in layout-state", () => {
		const sharedCssSources = [
			...readLayoutCssSources(),
			{ label: "shared/prototype-interactions.css", css: readFileSync(join(prototypesDir, "shared/prototype-interactions.css"), "utf8") },
		];
		const violations: string[] = [];

		for (const source of sharedCssSources) {
			const reducedMotionBlocks = getMediaBlocksMatching(source.css, /prefers-reduced-motion\s*:\s*reduce/i);
			const hasGlobalWildcardBaseline = reducedMotionBlocks.some((block) =>
				/\*\s*,\s*\*::before\s*,\s*\*::after\s*\{[^}]*animation-duration\s*:\s*0\.01ms/i.test(
					stripCssComments(block),
				),
			);

			if (source.label === "shared/layout-state.css") {
				if (!hasGlobalWildcardBaseline) {
					violations.push(`${source.label}:missing-global-reduced-motion-baseline`);
				}
			} else if (hasGlobalWildcardBaseline) {
				violations.push(`${source.label}:duplicate-global-reduced-motion-baseline`);
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

	it("backs every triggerable prototype overlay status with overlay markup", () => {
		const offenders = readManifest()
			.pages.filter(isActiveRoutePrototype)
			.filter((page) => {
				const html = readPrototypeHtml(page);

				return (
					page.landing?.overlayStatus === "triggerable" &&
					!/id="overlay-[^"]+"/.test(html)
				);
			})
			.map((page) => page.id);

		expect(offenders).toEqual([]);
	});

	it("registers every parity-claimed triggerable prototype overlay in current contracts", () => {
		const missing: string[] = [];
		for (const page of readManifest().pages) {
			if (!isActiveRoutePrototype(page)) continue;
			const contract = findPrimaryContract(page);
			if (
				contract?.landing?.reactParityVerified !== true ||
				contract.landing.overlayStatus !== "triggerable"
			) {
				continue;
			}
			const prototypeRef = `docs/designs/specs/prototypes/${page.file}`;
			const selectors = new Set(
				readContracts()
					.filter(
						(candidate) =>
							candidate.prototypeRef === prototypeRef &&
							candidate.landing?.reactParityVerified === true &&
							candidate.landing.overlayStatus === "triggerable",
					)
					.flatMap((candidate) => candidate.overlays?.map((overlay) => overlay.prototypeSelector) ?? []),
			);

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
		const expectedShellFamilies = [
			{ prototypeId: "cross-market", contractId: "cross-market", shellFamily: "radar" },
			{ prototypeId: "agent-console-v2", contractId: "research-agent-lab", shellFamily: "studio" },
			{ prototypeId: "experiment-list", contractId: "experiment-list", shellFamily: "catalog" },
		] as const;
		const manifest = readManifest();
		const contractById = new Map(readContracts().map((contract) => [contract.id, contract.shellFamily]));

		for (const { prototypeId, contractId, shellFamily } of expectedShellFamilies) {
			expect(manifest.pages.find((page) => page.id === prototypeId)?.shellFamily).toBe(shellFamily);
			expect(contractById.get(contractId)).toBe(shellFamily);
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

	it("classifies generated donut and heatgrid SVGs as meaningful visualizations", () => {
		const document = new JSDOM(`
			<section>
				<svg data-donut='{"value":0.72}' aria-label="Risk-On 概率"></svg>
				<svg data-heatgrid='{"rows":2,"cols":2}' aria-label="市场状态矩阵"></svg>
				<svg aria-hidden="true"><path d="M0 0h1"/></svg>
			</section>
		`).window.document;

		const [donut, heatgrid, icon] = [...document.querySelectorAll("svg")];
		if (donut === undefined || heatgrid === undefined || icon === undefined) {
			throw new Error("Expected donut, heatgrid, and icon SVG fixtures");
		}

		expect(isSvgInMeaningfulVisualizationContext(donut)).toBe(true);
		expect(isSvgInMeaningfulVisualizationContext(heatgrid)).toBe(true);
		expect(isSvgInMeaningfulVisualizationContext(icon)).toBe(false);
	});

	it("requires dialog overlay surfaces to use explicit accessible names", () => {
		const document = new JSDOM(`
			<section data-overlay="detail-overlay">
				<div id="dialog-title">订单详情</div>
				<div class="overlay-surface" role="dialog" aria-labelledby="dialog-title"></div>
				<div class="overlay-surface" role="dialog" aria-label="筛选器"></div>
				<div class="overlay-surface" role="dialog">
					<h2 class="overlay-title">视觉标题不能命名 dialog</h2>
				</div>
			</section>
		`).window.document;

		const [labelledbyDialog, labelledDialog, visualTitleDialog] = [
			...document.querySelectorAll(".overlay-surface"),
		];
		if (labelledbyDialog === undefined || labelledDialog === undefined || visualTitleDialog === undefined) {
			throw new Error("Expected three overlay surface fixtures");
		}

		expect(isApprovedOverlaySurfaceRole(labelledbyDialog)).toBe(true);
		expect(isApprovedOverlaySurfaceRole(labelledDialog)).toBe(true);
		expect(isApprovedOverlaySurfaceRole(visualTitleDialog)).toBe(false);
	});

	it("requires aria-labelledby targets to exist, be visible, and expose readable text", () => {
		const document = new JSDOM(`
			<section>
				<div id="readable">可读标题</div>
				<div id="empty"></div>
				<div id="hidden" aria-hidden="true">隐藏标题</div>
				<button id="labelled" aria-labelledby="readable"></button>
				<button id="native-label" aria-label="显式名称"></button>
				<button id="missing-ref" aria-labelledby="missing"></button>
				<button id="empty-ref" aria-labelledby="empty"></button>
				<button id="hidden-ref" aria-labelledby="hidden"></button>
			</section>
		`).window.document;

		expect(hasPrototypeAccessibleName(document.querySelector("#labelled") as Element)).toBe(true);
		expect(hasPrototypeAccessibleName(document.querySelector("#native-label") as Element)).toBe(true);
		expect(hasPrototypeAccessibleName(document.querySelector("#missing-ref") as Element)).toBe(false);
		expect(hasPrototypeAccessibleName(document.querySelector("#empty-ref") as Element)).toBe(false);
		expect(hasPrototypeAccessibleName(document.querySelector("#hidden-ref") as Element)).toBe(false);
	});

	it("requires active prototype overlays, charts, matrix cells, and symbol controls to expose accessible semantics", () => {
		const violations: string[] = [];

		for (const page of activePages()) {
			const document = readPrototypeDocument(page);

			for (const [index, surface] of getOverlaySurfaceLikeElements(document).entries()) {
				if (!isApprovedOverlaySurfaceRole(surface)) {
					violations.push(
						`${page.id}:overlay-surface:${index + 1}:${surface.getAttribute("role") ?? "missing-role"}`,
					);
				}
			}

			for (const [index, svg] of [...document.querySelectorAll("svg")].entries()) {
				if (
					isSvgInMeaningfulVisualizationContext(svg) &&
					!svgHasValidAccessibilitySemantics(svg)
				) {
					violations.push(
						`${page.id}:svg:${index + 1}:${svg.getAttribute("class") ?? "unclassed"}`,
					);
				}
			}

			const dataVizCells = [
				...document.querySelectorAll<HTMLElement>(
					[
						"[data-viz]",
						"[data-viz-cell-strength]",
						"[data-viz-cell-selected]",
						"[data-direction]",
						"[data-corr]",
						".heatmap-cell",
						".matrix-cell",
						".corr-cell",
						".viz-cell-strong",
					].join(", "),
				),
			].filter(isDataVizCellCandidate);
			for (const [index, cell] of dataVizCells.entries()) {
				if (!hasDataVizCellRole(cell) || !hasDataVizCellAccessibleLabel(cell)) {
					violations.push(
						`${page.id}:viz-cell:${index + 1}:${cell.getAttribute("class") ?? cell.tagName.toLowerCase()}`,
					);
				}
			}

			const symbolOnlyControls = [
				...document.querySelectorAll<HTMLElement>(
					"button, label, [role='button'], [tabindex], .overlay-close, .drawer-close, .toast-close, .tag-close-icon, .collapse-toggle, .sidebar-toggle",
				),
			].filter(isSymbolOnlyControl);
			for (const [index, control] of symbolOnlyControls.entries()) {
				if (!hasSymbolOnlyControlAccessibleSemantics(control)) {
					violations.push(
						`${page.id}:symbol-control:${index + 1}:${control.getAttribute("class") ?? control.tagName.toLowerCase()}`,
					);
				}
			}
		}

		expect(violations).toEqual([]);
	}, 20_000);

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

	it("requires status pills and risk badges to expose semantic markers beyond color", () => {
		const violations: string[] = [];
		const badgeSelector = [
			".status-pill",
			".risk-badge",
			".cell-badge.risk-low",
			".cell-badge.risk-med",
			".cell-badge.risk-high",
			".health-status",
			".stress-tag",
			".risk-strip-value",
		].join(", ");
		const markerPattern =
			/▲|▼|✓|!|✕|●|◐|P[0-3]|运行|暂停|草稿|归档|健康|异常|风险|突破|接近|警告|阻断|通过|待(?:复核|处理|审批)|完成|确认|忽略|订单|提交|补测|追踪|流式|审批|选中|延迟|陈旧|过期|失效|有效|匹配|变更|稳定|中性|active|paused|draft|archived|running|pending|confirmed|ignored|ordered|valid|match|stale|breach|expired|ready|manual|paper|review|enabled|stable|warn|bad|live|blocked|pass|fail|critical|healthy|degraded/i;

		for (const page of activePages()) {
			const document = readPrototypeDocument(page);
			const rules = getPrototypeAndSharedCssRules(page);
			const badges = [...document.querySelectorAll<HTMLElement>(badgeSelector)].filter(
				isDefaultVisibleElement,
			);

			for (const [index, badge] of badges.entries()) {
				const readableText = [
					getReadablePrimaryText(badge),
					badge.getAttribute("aria-label") ?? "",
				].join(" ");
				const hasTextMarker = markerPattern.test(readableText);
				const hasPseudoMarker = elementHasPseudoSemanticMarker(
					document,
					badge,
					rules,
					markerPattern,
				);

				if (!hasTextMarker && !hasPseudoMarker) {
					violations.push(
						`${page.id}:semantic-badge:${index + 1}:${badge.className}:${readableText || "empty"}`,
					);
				}
			}
		}

		expect(violations).toEqual([]);
	});

	it("documents the prototype chart interaction contract for future lightweight-charts implementation", () => {
		expect(existsSync(chartInteractionContractPath)).toBe(true);

		const contract = readFileSync(chartInteractionContractPath, "utf8");
		const requiredText = [
			...requiredChartContractSectionHeadings,
			...requiredChartAffordances,
			...requiredChartDataAttributes,
			...requiredChartSelectionCommandSchemaTerms,
			...requiredChartTestingExpectationTerms,
			...chartInteractionPrototypeRequirements.flatMap((requirement) => requirement.contracts),
			"lightweight-charts",
			"prefers-reduced-motion",
			"aria-label",
			"keyboard",
			"Instrument Hub",
			"Risk Center",
			"Backtest Result",
			"Trading Overview",
		];
		const missing = requiredText.filter((text) => !contract.includes(text));

		expect(missing).toEqual([]);
	});

	it("detects duplicate and unexpected chart interaction contract markers", () => {
		const document = new JSDOM(`
			<section>
				<div data-chart-interaction-contract="expected-a"></div>
				<div data-chart-interaction-contract="expected-a"></div>
				<div data-chart-interaction-contract="unexpected-extra"></div>
			</section>
		`).window.document;

		expect(
			collectChartInteractionContractViolations(document, "fixture-page", ["expected-a"]),
		).toEqual([
			"fixture-page:expected-a:duplicate-marker:2",
			"fixture-page:unexpected-marker:unexpected-extra",
		]);
	});

	it("marks representative chart placeholders with the chart interaction contract", () => {
		const violations: string[] = [];
		const requiredAffordanceSet = new Set(requiredChartAffordances);

		for (const requirement of chartInteractionPrototypeRequirements) {
			const document = readPrototypeDocument(activePageById(requirement.pageId));
			violations.push(
				...collectChartInteractionContractViolations(
					document,
					requirement.pageId,
					requirement.contracts,
				),
			);

			for (const contractId of requirement.contracts) {
				const markers = document.querySelectorAll(
					`[data-chart-interaction-contract="${contractId}"]`,
				);
				const marker = markers[0];
				if (markers.length !== 1 || !marker) {
					continue;
				}

				const affordances = new Set(
					(marker.getAttribute("data-chart-affordances") ?? "")
						.split(/\s+/)
						.filter(Boolean),
				);
				for (const affordance of requiredAffordanceSet) {
					if (!affordances.has(affordance)) {
						violations.push(`${requirement.pageId}:${contractId}:affordance:${affordance}`);
					}
				}

				if (!marker.getAttribute("data-chart-linked-time-range")?.trim()) {
					violations.push(`${requirement.pageId}:${contractId}:linked-time-range`);
				}
				if (!marker.getAttribute("data-chart-selection-command")?.trim()) {
					violations.push(`${requirement.pageId}:${contractId}:selection-command`);
				}
				if (!marker.getAttribute("aria-label")?.trim()) {
					violations.push(`${requirement.pageId}:${contractId}:aria-label`);
				}
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

	it("keeps selected light-mode prototype weak text on readable semantic tokens", () => {
		const violations: string[] = [];

		for (const pageId of lightReadabilityPages) {
			const page = activePageById(pageId);
			const html = readPrototypeHtml(page);
			const hasLightOverride =
				/\[data-theme="light"\][^{]+\{[^}]*--text-(?:tertiary|quaternary):\s*color-mix\(in oklch,\s*var\(--neutral-(?:400|500|600)\)/s.test(
					html,
				) ||
				/\[data-theme="light"\][^{]+\{[^}]*--prototype-light-readable-text:\s*var\(--neutral-600\)/s.test(
					html,
				);

			if (!hasLightOverride) {
				violations.push(`${pageId}:light-readable-text`);
			}
			if (/color:\s*var\(--text-quaternary\)/.test(html) && !html.includes("--prototype-light-readable-text")) {
				violations.push(`${pageId}:quaternary-without-light-readable-token`);
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

	it("documents high-risk actions with object, impact, confirmation, cancel, recovery, and non-color danger cues", () => {
		const violations: string[] = [];

		for (const page of activePages().filter((prototype) =>
			highRiskActionPages.includes(prototype.id as (typeof highRiskActionPages)[number]),
		)) {
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
				"[data-risk-object]",
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

			const containerText = getReadablePrimaryText(container);
			if (!/(影响|后果|范围|订单|策略|标的池|信号|配置|交易|撤单|审批)/.test(containerText)) {
				violations.push(`${page.id}:impact-copy`);
			}
			if (!/(取消|保留|返回|不执行)/.test(containerText)) {
				violations.push(`${page.id}:cancel-copy`);
			}
			if (!/(恢复|回滚|可重新|保留记录|审计)/.test(containerText)) {
				violations.push(`${page.id}:recovery-copy`);
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
			<div class="activity-header"><span class="caption-copy">最近运行</span></div>
		`).window.document;
		const rule: CssRule = {
			selector: ".caption-copy",
			selectors: [".caption-copy"],
			body: "font-size: var(--font-size-11);",
			start: 0,
			end: 0,
		};

		expect(hasOperationalElevenPxUsage(document, rule, ".caption-copy", [])).toBe(true);
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
				const classNames = classMatch[1];
				if (classNames === undefined) continue;
				const classes = classNames.split(/\s+/);
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
			].flatMap((match) => {
				const href = match[1];
				const filename = href?.split("/").at(-1);
				return filename === undefined ? [] : [filename];
			});

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
			[...tokenCss.matchAll(/(--[a-z0-9-]+)\s*:\s*([^;]+);/gi)].flatMap((match) => {
				const name = match[1];
				const value = match[2];
				return name === undefined || value === undefined ? [] : [[name, value.trim()] as const];
			}),
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
			"transition: opacity",
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

	it("keeps every prototype HTML file free of detector-blocking motion and generic font samples", () => {
		const layoutDrivenTransitionProperties = new Set([
			"width",
			"height",
			"max-width",
			"max-height",
			"min-width",
			"min-height",
			"padding",
			"margin",
			"flex",
			"flex-grow",
			"flex-shrink",
			"flex-basis",
		]);
		const violations: string[] = [];

		for (const source of readFullPrototypeCssSources()) {
			const css = stripCssComments(source.css);

			for (const match of css.matchAll(/transition\s*:\s*([^;}]+)/gi)) {
				const transitionValue = match[1];
				if (transitionValue === undefined) continue;
				const animatedProperties = transitionValue
					.split(",")
					.map((item) => item.trim().split(/\s+/)[0]?.toLowerCase() ?? "");

				if (animatedProperties.some((property) => property === "all")) {
					violations.push(`${source.label}:${getLineNumber(css, match.index)}:transition-all`);
				}
				if (animatedProperties.some((property) => layoutDrivenTransitionProperties.has(property))) {
					violations.push(`${source.label}:${getLineNumber(css, match.index)}:layout-transition`);
				}
			}

			for (const match of css.matchAll(/animation\s*:\s*([^;}]+)/gi)) {
				const animationValue = match[1];
				if (animationValue !== undefined && /(?:bounce|elastic)/i.test(animationValue)) {
					violations.push(`${source.label}:${getLineNumber(css, match.index)}:bounce-animation`);
				}
			}

			if (source.label !== "shared/fonts.css") {
				for (const match of css.matchAll(/font-family\s*:\s*['"](?:Inter|Roboto|Open Sans|Lato|Montserrat|Arial)\b/gi)) {
					violations.push(`${source.label}:${getLineNumber(css, match.index)}:literal-generic-font-sample`);
				}
			}
		}

		expect(violations).toEqual([]);
	});

	it("keeps icon-only overlay triggers explicitly named beyond title attributes", () => {
		const violations: string[] = [];

		for (const source of readPrototypeHtmlFilesRecursive()) {
			const document = new JSDOM(source.html).window.document;

			for (const trigger of document.querySelectorAll("label[for], button, [role='button']")) {
				const visibleText = trigger.textContent?.replace(/\s+/g, " ").trim() ?? "";
				const hasIcon = Boolean(trigger.querySelector("svg"));
				const hasExplicitName =
					Boolean(trigger.getAttribute("aria-label")) ||
					Boolean(trigger.getAttribute("aria-labelledby")) ||
					visibleText.length > 0;

				if (hasIcon && !hasExplicitName) {
					const target = trigger.getAttribute("for") ?? trigger.getAttribute("aria-controls") ?? "unknown";
					violations.push(`${source.label}:${target}`);
				}
			}
		}

		expect(violations).toEqual([]);
	}, 20_000);

	it("documents compact geometry fixes for final full-directory review risks", () => {
		const checks = [
			{
				page: activePageById("cross-market"),
				expected: [
					/@media\s*\(max-width:\s*1366px\)[\s\S]*\.drivers-strip\s*\{[\s\S]*grid-template-columns:\s*repeat\(4,\s*minmax\(0,\s*1fr\)\)/,
					/@media\s*\(max-width:\s*1200px\)[\s\S]*\.drivers-strip\s*\{[\s\S]*grid-template-columns:\s*repeat\(3,\s*minmax\(0,\s*1fr\)\)/,
				],
			},
			{
				page: activePageById("regime-monitor"),
				expected: [
					/\.heatgrid-legend\s*\{[\s\S]*flex-wrap:\s*wrap;/,
					/\.heatgrid-legend\s*\{[\s\S]*max-width:\s*100%;/,
				],
			},
			{
				page: activePageById("signals-inbox"),
				expected: [
					/\.shell-signals\s+\.detail-panel\s*\{[\s\S]*min-width:\s*0;/,
					/\.detail-header,\s*\.detail-body\s*\{[\s\S]*max-width:\s*100%;/,
				],
			},
			{
				page: activePageById("trading-overview"),
				expected: [
					/#default-view\s*>\s*\.status-bar\s*\{[\s\S]*width:\s*auto\s*!important;/,
					/#default-view\s*>\s*\.status-bar\s*\{[\s\S]*max-width:\s*calc\(100vw - var\(--shell-rail-width\)\);/,
				],
			},
			{
				page: activePageById("backtest-list"),
				expected: [/\.filter-count\s*\{[\s\S]*max-width:\s*100%;[\s\S]*overflow:\s*hidden;[\s\S]*text-overflow:\s*ellipsis;/],
			},
			{
				page: activePageById("experiment-list"),
				expected: [/\.filter-count\s*\{[\s\S]*max-width:\s*100%;[\s\S]*overflow:\s*hidden;[\s\S]*text-overflow:\s*ellipsis;/],
			},
		];
		const violations: string[] = [];

		for (const check of checks) {
			const html = readPrototypeHtml(check.page);
			for (const pattern of check.expected) {
				if (!pattern.test(html)) {
					violations.push(`${check.page.id}:${pattern.source.slice(0, 80)}`);
				}
			}
		}

		expect(violations).toEqual([]);
	});

	it("keeps freeze-critical operational typography at 12px or above", () => {
		const checks = [
			{
				pageId: "home",
				selectors: [".global-pulse-label", ".global-pulse-note", ".impact-label"],
			},
			{
				pageId: "trading-overview",
				selectors: [
					".scope-metric-label",
					".decision-regime-tag",
					".decision-pipeline",
					".pipeline-arrow",
					".equity-chart-label",
					".order-tab",
				],
			},
			{
				pageId: "agent-console-v2",
				selectors: [".panel-kicker", ".event", ".trace-item", ".node-kind", ".card-label"],
			},
			{
				pageId: "a-shares",
				selectors: [
					".context-bar-label",
					".map-readout-item",
					".map-interaction-hint",
					".map-insight-strip",
					".map-legend-label",
					".treemap-cell-vol",
					".hm-vol",
				],
			},
			{
				pageId: "strategy-studio",
				selectors: [
					".distribution-legend",
					".equity-curve-legend",
					".strategy-status-tag",
					".perf-metric-label",
					".perf-metric-change",
				],
			},
		] as const;
		const violations: string[] = [];

		for (const check of checks) {
			const page = activePages().find((candidate) => candidate.id === check.pageId);
			expect(page, `${check.pageId}: expected active prototype`).toBeDefined();
			if (!page) continue;
				const css = getStyleBlocks(readPrototypeHtml(page));
				for (const selector of check.selectors) {
					if (
						!getSelectorRuleBodies(css, selector).some((body) =>
							hasDeclaration(body, "font-size", /var\(\s*--font-size-12\s*\)/),
						)
					) {
						violations.push(`${check.pageId}:${selector}`);
					}
				}
		}

		expect(violations).toEqual([]);
	});

	it("keeps active prototype heading outline navigable without skipped levels", () => {
		const violations: string[] = [];

		for (const page of activePages()) {
			const document = readPrototypeDocument(page);
			let previousLevel = 0;
			for (const heading of [...document.querySelectorAll("h1, h2, h3, h4, h5, h6")]) {
				const level = Number(heading.tagName.slice(1));
				if (previousLevel > 0 && level > previousLevel + 1) {
					violations.push(
						`${page.id}:h${previousLevel}->h${level}:${heading.textContent?.trim().slice(0, 30)}`,
					);
				}
				previousLevel = level;
			}
		}

		expect(violations).toEqual([]);
	});

	it("keeps active prototype and shared CSS free of viewport, transition, focus, and tiny-text regressions", () => {
		const violations: string[] = [];
		const layoutDrivenTransitionProperties = new Set([
			"width",
			"height",
			"max-width",
			"max-height",
			"min-width",
			"min-height",
			"padding",
			"margin",
			"flex",
			"flex-grow",
			"flex-shrink",
			"flex-basis",
		]);

		for (const source of readPrototypeCssSources()) {
			const rawCss = source.css;
			const css = stripCssComments(rawCss);

			for (const match of css.matchAll(/(^|[^a-z0-9-])100vh\b/gi)) {
				const index = match.index + (match[1]?.length ?? 0);
				if (!hasFixedCanvasException(rawCss, index)) {
					violations.push(`${source.label}:${getLineNumber(css, index)}:100vh`);
				}
			}

			for (const match of css.matchAll(/transition\s*:\s*([^;}]+)/gi)) {
					const transitionValue = match[1];
					if (transitionValue === undefined) continue;
					if (transitionValue.split(",").some((item) => /^all(?:\s|$)/i.test(item.trim()))) {
						violations.push(`${source.label}:${getLineNumber(css, match.index)}:transition-all`);
					}
					if (
						transitionValue
							.split(",")
							.some((item) =>
								layoutDrivenTransitionProperties.has(item.trim().split(/\s+/)[0]?.toLowerCase() ?? ""),
							)
					) {
						violations.push(`${source.label}:${getLineNumber(css, match.index)}:layout-transition`);
					}
				}

			for (const match of css.matchAll(/font-size\s*:\s*9px\b/gi)) {
				violations.push(`${source.label}:${getLineNumber(css, match.index)}:font-size-9px`);
			}

			for (const rule of css.matchAll(/([^{}]+)\{([^{}]*)\}/g)) {
				const rawSelector = rule[1];
				const body = rule[2];
				if (rawSelector === undefined || body === undefined) continue;
				const selector = rawSelector.replace(/\s+/g, " ").trim();
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

	it("keeps glow budgeted active prototypes free of decorative glow", () => {
		const violations: string[] = [];
		const cssSourceLabels = readGlowBudgetCssSources().map((source) => source.label);

		expect(cssSourceLabels).toEqual(
			expect.arrayContaining(["shared/fonts.css", "src/styles/design-tokens/tokens-base.css"]),
		);
		expect(readGlowBudgetSharedTextSources().map((source) => source.label)).toEqual([
			"shared/prototype-interactions.js",
			"shared/theme-switcher.js",
			"shared/mock-data.js",
			"shared/screener-workflow.js",
		]);

		for (const source of readGlowBudgetCssSources()) {
			violations.push(...collectGlowBudgetCssViolations(source));
		}

		for (const source of readGlowBudgetSharedTextSources()) {
			violations.push(...collectGlowBudgetSharedTextViolations(source));
		}

		for (const source of readGlowBudgetHtmlSources()) {
			violations.push(...collectGlowBudgetHtmlViolations(source));
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
