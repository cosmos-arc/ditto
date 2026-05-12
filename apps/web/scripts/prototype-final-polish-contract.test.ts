import { readFileSync, readdirSync } from "node:fs";
import { join, resolve } from "node:path";
import { describe, expect, it } from "vitest";

const prototypesDir = resolve(import.meta.dirname, "../docs/designs/specs/prototypes");
const sharedDir = join(prototypesDir, "shared");

type StaticFinding = {
	file: string;
	line: number;
	snippet: string;
};

type SideBorderDeclaration = {
	side: string;
	kind: "shorthand" | "width" | "color";
	value: string;
	index: number;
	snippet: string;
};

function readPrototypeFile(relativePath: string): string {
	return readFileSync(join(prototypesDir, relativePath), "utf8");
}

function lineNumberAt(source: string, index: number): number {
	return source.slice(0, index).split("\n").length;
}

function collectActiveRootHtmlFiles(): string[] {
	return readdirSync(prototypesDir)
		.filter((file) => file.startsWith("page-") && file.endsWith(".html"))
		.sort();
}

function collectActiveRootCssFiles(): string[] {
	return readdirSync(prototypesDir, { withFileTypes: true })
		.filter((entry) => entry.isFile() && entry.name.endsWith(".css"))
		.map((entry) => entry.name)
		.sort();
}

function collectActiveSharedCssFiles(): string[] {
	return readdirSync(sharedDir, { withFileTypes: true })
		.filter((entry) => entry.isFile() && entry.name.endsWith(".css"))
		.map((entry) => `shared/${entry.name}`)
		.sort();
}

function isThickBorderWidth(width: string): boolean {
	return Number.parseFloat(width) >= 2;
}

function widthValue(value: string): string | null {
	return value.match(/\b([0-9]*\.?[0-9]+)px\b/i)?.[1] ?? null;
}

function hasThickBorderWidth(value: string): boolean {
	const width = widthValue(value);
	return width !== null && isThickBorderWidth(width);
}

function hasSolidBorderStyle(value: string): boolean {
	return /\bsolid\b/i.test(value);
}

function isVisibleColor(color: string): boolean {
	return !/^(?:transparent|currentColor)\b/i.test(color.trim());
}

function shorthandBorderColor(value: string): string | null {
	const color = value
		.replace(/\b[0-9]*\.?[0-9]+px\b/i, "")
		.replace(/\bsolid\b/i, "")
		.trim();

	return color.length > 0 ? color : null;
}

function collectSideBorderDeclarations(source: string): SideBorderDeclaration[] {
	return [
		...source.matchAll(
			/border-(left|right|inline-start|inline-end)(?:-(width|color))?:\s*([^;]+)/g,
		),
	].map((match) => ({
		side: match[1] ?? "",
		kind:
			match[2] === "width" || match[2] === "color"
				? match[2]
				: "shorthand",
		value: match[3]?.trim() ?? "",
		index: match.index ?? 0,
		snippet: match[0].trim(),
	}));
}

function collectColoredSideBorderFindings(relativePath: string): StaticFinding[] {
	const source = readPrototypeFile(relativePath);
	const findings: StaticFinding[] = [];

	for (const declaration of collectSideBorderDeclarations(source).filter(
		(borderDeclaration) => borderDeclaration.kind === "shorthand",
	)) {
		const color = shorthandBorderColor(declaration.value);
		if (
			!hasThickBorderWidth(declaration.value) ||
			!hasSolidBorderStyle(declaration.value) ||
			!color ||
			!isVisibleColor(color)
		) {
			continue;
		}

		findings.push({
			file: relativePath,
			line: lineNumberAt(source, declaration.index),
			snippet: declaration.snippet,
		});
	}

	const declarationBlockPattern = /{(?<body>[^{}]*)}/g;

	for (const blockMatch of source.matchAll(declarationBlockPattern)) {
		const body = blockMatch.groups?.body;
		if (!body) continue;

		const bodyOffset = (blockMatch.index ?? 0) + 1;
		const declarations = collectSideBorderDeclarations(body);
		const widthSources = declarations.filter(
			(declaration) =>
				(declaration.kind === "shorthand" &&
					hasThickBorderWidth(declaration.value) &&
					hasSolidBorderStyle(declaration.value) &&
					shorthandBorderColor(declaration.value) === null) ||
				(declaration.kind === "width" && hasThickBorderWidth(declaration.value)),
		);

		for (const widthSource of widthSources) {
			const colorDeclaration = declarations.find(
				(declaration) =>
					declaration.side === widthSource.side && declaration.kind === "color",
			);
			const color = colorDeclaration?.value ?? "";

			if (!color || !isVisibleColor(color)) {
				continue;
			}

			findings.push({
				file: relativePath,
				line: lineNumberAt(source, bodyOffset + widthSource.index),
				snippet: `${widthSource.snippet}; ${colorDeclaration?.snippet}`,
			});
		}
	}

	return findings;
}

function extractCssRuleBlock(source: string, selector: string): string {
	const selectorIndex = source.indexOf(selector);
	if (selectorIndex === -1) return "";

	const openBraceIndex = source.indexOf("{", selectorIndex);
	if (openBraceIndex === -1) return "";

	let depth = 0;
	for (let index = openBraceIndex; index < source.length; index += 1) {
		const character = source[index];
		if (character === "{") depth += 1;
		if (character === "}") depth -= 1;
		if (depth === 0) return source.slice(selectorIndex, index + 1);
	}

	return "";
}

function extractDivSnippetAt(source: string, index: number): string {
	const divStartIndex = source.lastIndexOf("<div", index);
	if (divStartIndex === -1) return "";

	let depth = 0;
	for (const match of source.slice(divStartIndex).matchAll(/<\/?div\b[^>]*>/g)) {
		const tag = match[0];
		if (tag.startsWith("</")) {
			depth -= 1;
		} else {
			depth += 1;
		}

		if (depth === 0) {
			const tagEndIndex = divStartIndex + (match.index ?? 0) + tag.length;
			return source.slice(divStartIndex, tagEndIndex);
		}
	}

	return "";
}

function extractDivByClassSnippet(source: string, className: string): string {
	const marker = `class="${className}"`;
	const startIndex = source.indexOf(marker);
	if (startIndex === -1) return "";

	return extractDivSnippetAt(source, startIndex);
}

function collectDivSnippetsByClassToken(source: string, classToken: string): string[] {
	const classPattern = new RegExp(`<div\\b[^>]*class="[^"]*\\b${classToken}\\b[^"]*"`, "g");
	const snippets: string[] = [];

	for (const match of source.matchAll(classPattern)) {
		const snippet = extractDivSnippetAt(source, match.index ?? 0);
		if (snippet) snippets.push(snippet);
	}

	return snippets;
}

describe("prototype final polish static contract", () => {
	it("does not use thick colored side accent borders in active prototype CSS", () => {
		const scannedFiles = [
			...collectActiveRootCssFiles(),
			...collectActiveSharedCssFiles(),
			...collectActiveRootHtmlFiles(),
		];
		const requiredScannedFiles = [
			"tokens-style.css",
			"shared/fonts.css",
			"shared/layout-components.css",
			"shared/layout-gallery.css",
			"shared/layout-overlay.css",
			"shared/layout-shell.css",
			"shared/layout-state.css",
			"shared/prototype-interactions.css",
			"shared/prototype-toggles.css",
			"shared/theme-switcher.css",
			"page-a-shares.html",
			"page-agent-console.html",
			"page-agent-console-v2.html",
			"page-strategy-studio.html",
			"page-markets-screener.html",
		];
		const missingScannedFiles = requiredScannedFiles.filter(
			(file) => !scannedFiles.includes(file),
		);

		expect(missingScannedFiles).toEqual([]);
		const findings = scannedFiles.flatMap(collectColoredSideBorderFindings);

		expect(findings).toEqual([]);
	});

	it("keeps superseded agent console out of the root prototype release surface", () => {
		const rootHtmlFiles = collectActiveRootHtmlFiles();

		expect(rootHtmlFiles).not.toContain("page-agent-console.html");
		expect(rootHtmlFiles).toContain("page-agent-console-v2.html");
	});

	it("uses explicit A-share red and green stepped heatmap colors instead of low-chroma graphite mixes", () => {
		const source = readPrototypeFile("page-a-shares.html");
		const mapContainerCss = extractCssRuleBlock(source, ".map-container");
		const mapContainerMarkup = extractDivByClassSnippet(source, "map-container");
		const marketStructureCellMarkup = [
			...collectDivSnippetsByClassToken(source, "treemap-cell-iv"),
			...collectDivSnippetsByClassToken(source, "heatmap-cell"),
		].join("\n");
		const requiredTokens = [
			"--map-market-up-1: oklch(0.305 0.062 22);",
			"--map-market-up-2: oklch(0.358 0.088 22);",
			"--map-market-up-3: oklch(0.414 0.116 22);",
			"--map-market-up-4: oklch(0.475 0.144 22);",
			"--map-market-down-1: oklch(0.300 0.050 155);",
			"--map-market-down-2: oklch(0.352 0.070 155);",
			"--map-market-down-3: oklch(0.406 0.092 155);",
			"--map-market-down-4: oklch(0.462 0.112 155);",
		];
		const requiredMapCellSemantics = [
			'data-direction="up"',
			'data-direction="down"',
			"▲",
			"▼",
		];

		const missingTokens = requiredTokens.filter((token) => !mapContainerCss.includes(token));
		const missingMapCellSemantics = requiredMapCellSemantics.filter(
			(semantic) => !marketStructureCellMarkup.includes(semantic),
		);

		expect(missingTokens).toEqual([]);
		expect(mapContainerCss).not.toMatch(/--map-market-(?:up|down)-[1-4]:\s*color-mix\(/);
		expect(mapContainerMarkup).toContain("A股：红涨绿跌");
		expect(missingMapCellSemantics).toEqual([]);
	});
});
