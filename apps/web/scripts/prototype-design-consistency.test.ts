import { existsSync, readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { JSDOM } from "jsdom";
import { describe, expect, it } from "vitest";
import {
	buildDefaultPrototypeGateArgs,
	buildPassthroughGateArgs,
	defaultViewportArgs,
} from "./run-prototype-gates";

const root = process.cwd();
const prototypesDir = join(root, "docs/designs/specs/prototypes");
const contractsDir = join(root, "docs/contracts/pages");
const prototypeFontsCss = join(prototypesDir, "shared/fonts.css");
const prototypeLayoutCss = join(prototypesDir, "shared/layout-base.css");
const prototypeThemeSwitcherCss = join(prototypesDir, "shared/theme-switcher.css");
const prototypeTogglesCss = join(prototypesDir, "shared/prototype-toggles.css");
const prototypeTokensStyleCss = join(prototypesDir, "tokens-style.css");
const tokenStabilizationSpec = join(
	root,
	"docs/designs/specs/15_ditto_token_stabilization_spec.md",
);
const archivedPrototypeIds = new Set(["ai-overview", "ai-copilot"]);

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
	shellFamily: string;
	overlays?: Array<{ prototypeSelector: string }>;
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
	return readTopLevelCssRules(css).find((rule) => rule.selectors.includes(selector))?.body;
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
		{ label: "shared/layout-base.css", css: readFileSync(prototypeLayoutCss, "utf8") },
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
		readFileSync(prototypeLayoutCss, "utf8"),
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

describe("prototype design consistency", () => {
	it("keeps exactly 27 active route prototypes", () => {
		const activePages = readManifest().pages.filter(isActiveRoutePrototype);

		expect(activePages).toHaveLength(27);
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

	it("keeps the Pro Max shared CSS and accessibility baseline machine-checkable", () => {
		const css = readFileSync(prototypeLayoutCss, "utf8");
		const orphanDeclaration = /}\s*\n\s*(appearance|cursor|transition)\s*:/m.exec(css);
		const tokenDefinitions = extractCustomPropertyDefinitions(readTokenCssBundle());
		const tokenReferences = extractCustomPropertyReferences(css);
		const missingTokens = [...tokenReferences]
			.filter((token) => !tokenDefinitions.has(token))
			.sort();
		const violations: string[] = [];

		if (orphanDeclaration) {
			violations.push(`layout-base.css:orphan:${orphanDeclaration[1]}`);
		}

		for (const token of missingTokens) {
			violations.push(`layout-base.css:missing-token:${token}`);
		}

		if (css.includes("oklch(from")) {
			violations.push("layout-base.css:oklch-from");
		}

		if (!css.includes("@media (prefers-reduced-motion: reduce)")) {
			violations.push("layout-base.css:reduced-motion");
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
				if (/[A-Za-z]{2,}/.test(text)) {
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
		}

		const missing: string[] = [];
		for (const page of readManifest().pages) {
			if (!isActiveRoutePrototype(page)) continue;

			const selectors =
				contractByPrototype.get(`docs/designs/specs/prototypes/${page.file}`) ?? new Set();

			for (const id of getOverlayIds(readPrototypeHtml(page))) {
				if (!selectors.has(`[data-overlay='${id}']`) && !selectors.has(`[data-overlay="${id}"]`)) {
					missing.push(`${page.id}:${id}`);
				}
			}
		}

		expect(missing).toEqual([]);
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
			if (defaultView.querySelector('input[type="checkbox"]') && !defaultView.querySelector("[data-batch-action-bar]")) {
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

		if (!/\.shell-hub\b/.test(layoutCss)) violations.push("layout-base.css:shell-hub");
		if (!/\.shell-agent\b/.test(layoutCss)) violations.push("layout-base.css:shell-agent");

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
		const layoutCss = stripCssComments(readFileSync(prototypeLayoutCss, "utf8"));
		const violations: string[] = [];
		const lockedShellSelectors = [".shell", ".shell-v2", ".shell-catalog", ".shell-agent"];
		const media1200 = getMediaBlock(layoutCss, 1200);
		const media1024 = getMediaBlock(layoutCss, 1024);
		const media768 = getMediaBlock(layoutCss, 768);

		for (const selector of lockedShellSelectors) {
			const shellRule = new RegExp(`(?:^|\\n)${selector.replace(".", "\\.")}\\s*\\{([^{}]*)\\}`, "m")
				.exec(layoutCss)?.[1];
			if (!shellRule || !/\b(?:height|min-height)\s*:\s*(?:calc\()?100dvh\b/.test(shellRule)) {
				violations.push(`layout-base.css:${selector}:100dvh`);
			}
		}

		if (!hasDeclaration(getSelectorRuleBody(media1200 ?? "", ".shell-catalog"), "--prototype-detail-width", /^min\(300px,\s*28vw\)$/)) {
			violations.push("layout-base.css:breakpoint-1200-catalog-detail");
		}
		if (!hasDeclaration(getSelectorRuleBody(media1024 ?? "", ".shell-header [data-header-utility-bar]"), "max-width", /^44vw$/)) {
			violations.push("layout-base.css:breakpoint-1024-header-utilities");
		}
		for (const selector of [".shell-catalog", ".shell-studio", ".shell-agent", ".shell-radar"]) {
			if (!hasDeclaration(getSelectorRuleBody(media768 ?? "", selector), "overflow-x", /^auto$/)) {
				violations.push(`layout-base.css:breakpoint-768-shell-overflow:${selector}`);
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
			"layout-base.css",
			"theme-switcher.css",
			"prototype-toggles.css",
		];
		const violations: string[] = [];

		for (const page of activePages()) {
			const html = readPrototypeHtml(page);
			const imports = [
				...html.matchAll(
					/href="([^"]*(?:tokens-[^"]+\.css|layout-base\.css|theme-switcher\.css|prototype-toggles\.css))"/g,
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
		expect(layoutCss).toContain(".shell-header :is(.header-utility-btn, .header-action-btn, .header-btn-badge)");
		expect(layoutCss).toContain(".shell-header .header-actions :is(.btn, .btn-sm)");
		expect(layoutCss).toContain("height: var(--header-btn-size) !important;");
		expect(layoutCss).toContain("font-size: var(--font-size-12) !important;");
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
		expect(layoutCss).toContain("background: var(--surface-app) !important;");
		expect(layoutCss).toContain("backdrop-filter: none !important;");
		expect(layoutCss).toContain(".shell-header::after");
		expect(layoutCss).toContain("display: none !important;");
		expect(layoutCss).toContain(".shell-header .header-title::after");
		expect(layoutCss).toContain("content: none !important;");

		expect(togglesCss).toContain("background: color-mix(in oklch, var(--surface-app) 72%, transparent);");
		expect(togglesCss).toContain("background: var(--surface-modal) !important;");
		expect(togglesCss).toContain("box-shadow: none !important;");
	});

	it("keeps prototype overlay, tray, and semantic feedback motion shared", () => {
		const layoutCss = readFileSync(prototypeLayoutCss, "utf8");
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

			const lines = readPrototypeHtml(page).split("\n");
			lines.forEach((line, index) => {
				if (line.includes("rgba(")) hits.push(`${page.id}:${index + 1}:rgba`);
				if (
					line.includes("oklch(") &&
					!line.includes("oklch(from var(") &&
					!/--[a-z0-9-]+\s*:/i.test(line)
				) {
					hits.push(`${page.id}:${index + 1}:oklch`);
				}
			});
		}

		expect(hits).toEqual([]);
	});
});
