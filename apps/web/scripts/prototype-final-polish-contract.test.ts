import { existsSync, readFileSync, readdirSync } from "node:fs";
import { join, resolve } from "node:path";
import { describe, expect, it } from "vitest";

const prototypesDir = resolve(import.meta.dirname, "../docs/designs/specs/prototypes");

const activeSharedCssFiles = [
	"shared/layout-components.css",
	"shared/layout-shell.css",
	"shared/layout-state.css",
	"shared/prototype-interactions.css",
	"shared/prototype-toggles.css",
	"shared/theme-switcher.css",
] as const;

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

function collectColoredSideBorderFindings(relativePath: string): StaticFinding[] {
	const source = readPrototypeFile(relativePath);
	const findings: StaticFinding[] = [];
	const sideBorderPattern =
		/border-(left|right):\s*(?:[2-9]|\d{2,})px\s+solid\s+(?!transparent\b|currentColor\b)([^;]+)/g;

	for (const match of source.matchAll(sideBorderPattern)) {
		findings.push({
			file: relativePath,
			line: lineNumberAt(source, match.index ?? 0),
			snippet: match[0].trim(),
		});
	}

	return findings;
}

describe("prototype final polish static contract", () => {
	it("does not use thick colored side accent borders in active prototype CSS", () => {
		const scannedFiles = [
			...activeSharedCssFiles,
			...collectActiveRootHtmlFiles(),
		].filter((relativePath) => existsSync(join(prototypesDir, relativePath)));

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

		for (const token of requiredTokens) {
			expect(source).toContain(token);
		}

		expect(source).not.toMatch(/--map-market-(?:up|down)-[1-4]:\s*color-mix\(/);
		expect(source).toContain("A股：红涨绿跌");
		expect(source).toContain('data-direction="up"');
		expect(source).toContain('data-direction="down"');
		expect(source).toContain("▲");
		expect(source).toContain("▼");
	});
});
