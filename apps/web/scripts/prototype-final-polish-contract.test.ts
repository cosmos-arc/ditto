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

function collectActiveSharedCssFiles(): string[] {
	return readdirSync(sharedDir, { withFileTypes: true })
		.filter((entry) => entry.isFile() && entry.name.endsWith(".css"))
		.map((entry) => `shared/${entry.name}`)
		.sort();
}

function isThickBorderWidth(width: string): boolean {
	return Number.parseFloat(width) >= 2;
}

function isVisibleColor(color: string): boolean {
	return !/^(?:transparent|currentColor)\b/i.test(color.trim());
}

function collectColoredSideBorderFindings(relativePath: string): StaticFinding[] {
	const source = readPrototypeFile(relativePath);
	const findings: StaticFinding[] = [];
	const sideBorderPattern =
		/border-(left|right|inline-start|inline-end):\s*([0-9]*\.?[0-9]+)px\s+solid\s+([^;]+)/g;

	for (const match of source.matchAll(sideBorderPattern)) {
		const [, , width, color] = match;
		if (!width || !color || !isThickBorderWidth(width) || !isVisibleColor(color)) {
			continue;
		}

		findings.push({
			file: relativePath,
			line: lineNumberAt(source, match.index ?? 0),
			snippet: match[0].trim(),
		});
	}

	const declarationBlockPattern = /{(?<body>[^{}]*)}/g;

	for (const blockMatch of source.matchAll(declarationBlockPattern)) {
		const body = blockMatch.groups?.body;
		if (!body) continue;

		const bodyOffset = (blockMatch.index ?? 0) + 1;
		const splitBorderDeclarations = [
			...body.matchAll(
				/border-(left|right|inline-start|inline-end)-(width|color):\s*([^;]+)/g,
			),
		];

		for (const widthDeclaration of splitBorderDeclarations.filter(
			(declaration) => declaration[2] === "width",
		)) {
			const side = widthDeclaration[1];
			const width = widthDeclaration[3]?.trim() ?? "";
			const colorDeclaration = splitBorderDeclarations.find(
				(declaration) => declaration[1] === side && declaration[2] === "color",
			);
			const color = colorDeclaration?.[3]?.trim() ?? "";

			if (!isThickBorderWidth(width) || !color || !isVisibleColor(color)) {
				continue;
			}

			findings.push({
				file: relativePath,
				line: lineNumberAt(source, bodyOffset + (widthDeclaration.index ?? 0)),
				snippet: `${widthDeclaration[0].trim()}; ${colorDeclaration?.[0].trim()}`,
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

function extractDivByClassSnippet(source: string, className: string): string {
	const marker = `class="${className}"`;
	const startIndex = source.indexOf(marker);
	if (startIndex === -1) return "";

	const divStartIndex = source.lastIndexOf("<div", startIndex);
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

describe("prototype final polish static contract", () => {
	it("does not use thick colored side accent borders in active prototype CSS", () => {
		const scannedFiles = [
			...collectActiveSharedCssFiles(),
			...collectActiveRootHtmlFiles(),
		];

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
		const requiredMapSemantics = [
			"A股：红涨绿跌",
			'data-direction="up"',
			'data-direction="down"',
			"▲",
			"▼",
		];

		const missingTokens = requiredTokens.filter((token) => !mapContainerCss.includes(token));
		const missingMapSemantics = requiredMapSemantics.filter(
			(semantic) => !mapContainerMarkup.includes(semantic),
		);

		expect(missingTokens).toEqual([]);
		expect(mapContainerCss).not.toMatch(/--map-market-(?:up|down)-[1-4]:\s*color-mix\(/);
		expect(missingMapSemantics).toEqual([]);
	});
});
