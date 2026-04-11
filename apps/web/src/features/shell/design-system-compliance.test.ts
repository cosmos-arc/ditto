import { describe, it, expect } from "vitest";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, extname, basename } from "node:path";

/* ------------------------------------------------------------------ */
/*  Helpers                                                            */
/* ------------------------------------------------------------------ */

const SRC_ROOT = join(import.meta.dirname, "../../");

function readAllFiles(
	dir: string,
	extensions: string[],
	exclude: string[] = [],
): Map<string, string> {
	const result = new Map<string, string>();

	function walk(current: string) {
		for (const entry of readdirSync(current)) {
			const full = join(current, entry);
			const stat = statSync(full);

			if (stat.isDirectory()) {
				if (exclude.some((ex) => full.includes(ex))) continue;
				walk(full);
			} else if (
				stat.isFile() &&
				extensions.includes(extname(full)) &&
				!exclude.some((ex) => full.includes(ex))
			) {
				result.set(full, readFileSync(full, "utf-8"));
			}
		}
	}

	walk(dir);
	return result;
}

/* ------------------------------------------------------------------ */
/*  1. Legacy token references                                         */
/* ------------------------------------------------------------------ */

describe("Legacy token compliance", () => {
	const LEGACY_TOKEN_MAP: Record<string, string> = {
		"--color-surface-hover": "--color-interaction-hover-subtle-bg",
		"--color-foreground-primary": "--color-foreground",
		"--color-status-success": "--color-system-healthy",
		"--color-status-error": "--color-system-down",
		"--color-status-warning": "--color-risk-warning",
		"--color-surface-base": "--color-surface-1",
		"--color-surface-elevated": "--color-surface-2",
		"--color-brand-primary": "--color-brand-500",
		"--color-brand-accent": "--color-accent",
		"--color-border-default": "--color-border",
	};

	const files = readAllFiles(join(SRC_ROOT, "features"), [".tsx", ".css"], [
		"node_modules",
		".test.",
	]);

	it("no legacy token references in feature source files", () => {
		const violations: string[] = [];

		for (const [filePath, content] of files) {
			const relPath = filePath.replace(SRC_ROOT, "");
			for (const [legacy] of Object.entries(LEGACY_TOKEN_MAP)) {
				// Match as CSS variable usage: var(--xxx) or direct reference
				const pattern = new RegExp(
					`var\\(${legacy.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}\\)|` +
						`${legacy.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}(?=\\s*[:;)])`,
					"g",
				);
				const matches = content.match(pattern);
				if (matches) {
					violations.push(
						`${relPath}: ${legacy} (${matches.length}x) → use ${LEGACY_TOKEN_MAP[legacy]}`,
					);
				}
			}
		}

		expect(violations.join("\n"), `${violations.length} legacy token references found:\n`).toBe(
			"",
		);
	});

	it("all legacy token aliases are unreferenced in features", () => {
		const legacyNames = Object.keys(LEGACY_TOKEN_MAP);
		const totalRefs: string[] = [];

		for (const [filePath, content] of files) {
			const relPath = filePath.replace(SRC_ROOT, "");
			for (const legacy of legacyNames) {
				if (content.includes(legacy)) {
					totalRefs.push(relPath);
				}
			}
		}

		expect(
			totalRefs.length,
			`Total files still referencing legacy tokens: ${totalRefs.length}`,
		).toBe(0);
	});
});

/* ------------------------------------------------------------------ */
/*  2. Arbitrary pixel font sizes                                      */
/* ------------------------------------------------------------------ */

describe("Typography compliance", () => {
	const files = readAllFiles(join(SRC_ROOT, "features"), [".tsx"], [
		"node_modules",
		".test.",
	]);

	// text-[10px] → text-xs, text-[13px] → text-base, text-[24px] → text-3xl
	const FORBIDDEN_FONT_SIZES: Record<string, string> = {
		"text-\\[10px\\]": "text-xs",
		"text-\\[13px\\]": "text-base",
		"text-\\[24px\\]": "text-3xl",
		"text-\\[var\\(--text-xs\\)\\]": "text-xs",
		"text-\\[var\\(--text-sm\\)\\]": "text-sm",
		"text-\\[var\\(--font-size-10\\)\\]": "text-xs",
		"text-\\[var\\(--font-size-12\\)\\]": "text-sm",
	};

	it("no arbitrary pixel font sizes that should use semantic utilities", () => {
		const violations: string[] = [];

		for (const [filePath, content] of files) {
			const relPath = filePath.replace(SRC_ROOT, "");
			for (const [pattern, replacement] of Object.entries(FORBIDDEN_FONT_SIZES)) {
				const regex = new RegExp(pattern, "g");
				const matches = content.match(regex);
				if (matches) {
					violations.push(
						`${relPath}: ${matches[0]} → ${replacement} (${matches.length}x)`,
					);
				}
			}
		}

		expect(
			violations.join("\n"),
			`${violations.length} arbitrary font-size usages found:\n`,
		).toBe("");
	});
});

/* ------------------------------------------------------------------ */
/*  3. Page-level spacing compliance                                   */
/* ------------------------------------------------------------------ */

describe("Page spacing compliance", () => {
	const pageFiles = readAllFiles(join(SRC_ROOT, "features"), [".tsx"], [
		"node_modules",
		".test.",
	]);

	// Only check files ending in *-page.tsx
	const pageEntries = [...pageFiles.entries()].filter(
		([path]) => basename(path).endsWith("-page.tsx"),
	);

	it("page containers use density-responsive panel padding", () => {
		const violations: string[] = [];

		for (const [filePath, content] of pageEntries) {
			const relPath = filePath.replace(SRC_ROOT, "");
			// Raw p-4 or px-4 py-4 at the main container level should use token
			// Check for raw Tailwind padding in the main panel div
			if (content.match(/className="[^"]*\bp-[34]\b/) && !content.includes("density-panel-padding")) {
				violations.push(`${relPath}: uses raw p-3/p-4 instead of density-panel-padding`);
			}
		}

		expect(
			violations.join("\n"),
			`${violations.length} pages with raw padding:\n`,
		).toBe("");
	});

	it("page grid gaps use density tokens, not raw gap-4", () => {
		const violations: string[] = [];

		for (const [filePath, content] of pageEntries) {
			const relPath = filePath.replace(SRC_ROOT, "");
			// gap-4 at the top-level grid should be a density token
			if (
				content.match(/className="[^"]*\bgap-4\b/) &&
				!content.includes("density-gutter") &&
				!content.includes("section-gap")
			) {
				violations.push(`${relPath}: uses raw gap-4 instead of density token`);
			}
		}

		expect(
			violations.join("\n"),
			`${violations.length} pages with raw gap-4:\n`,
		).toBe("");
	});
});
