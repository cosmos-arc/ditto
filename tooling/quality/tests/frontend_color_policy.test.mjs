import { describe, expect, test } from "bun:test";

import { findRawColorPrimitives, isCanonicalTokenFile } from "../frontend_color_policy.mjs";

describe("frontend color policy", () => {
	test("detects every supported raw color syntax with line numbers", () => {
		const findings = findRawColorPrimitives(`
.hex { color: #abc; }
.rgb { color: rgb(1 2 3); }
.hsl { color: hsl(20 30% 40%); }
.oklch { color: oklch(0.5 0.1 200); }
`, "src/example.css");

		expect(findings.map(({ syntax, line }) => ({ syntax, line }))).toEqual([
			{ syntax: "hex", line: 2 },
			{ syntax: "rgb", line: 3 },
			{ syntax: "hsl", line: 4 },
			{ syntax: "oklch", line: 5 },
		]);
	});

	test("ignores comments but checks CSS and component string literals", () => {
		expect(findRawColorPrimitives("/* #fff oklch(1 0 0) */", "src/example.css")).toEqual([]);
		expect(findRawColorPrimitives('const color = "rgba(0, 0, 0, .2)";', "src/example.tsx")).toHaveLength(1);
	});

	test("only design-token definitions are canonical color sources", () => {
		expect(isCanonicalTokenFile("src/styles/design-tokens/tokens-semantic.css")).toBe(true);
		expect(isCanonicalTokenFile("src/styles/themes/light.css")).toBe(false);
		expect(isCanonicalTokenFile("src/styles/globals.css")).toBe(false);
	});
});
