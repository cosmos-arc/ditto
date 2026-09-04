import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const currentDir = dirname(fileURLToPath(import.meta.url));

const LIVE_DERIVED_HOOK_FILES = [
	"use-positions.ts",
	"use-signals.ts",
	"use-signal-detail.ts",
	"use-signals-queue.ts",
	"use-orders-summary.ts",
] as const;

describe("trading live hook architecture", () => {
	it("does not conditionally return another hook from live-mode branches", () => {
		const offenders = LIVE_DERIVED_HOOK_FILES.filter((fileName) => {
			const source = readFileSync(join(currentDir, fileName), "utf8");
			return /if\s*\([^)]*shouldUsePrototypeMocks\(\)[^)]*\)\s*\{[\s\S]*return\s+useDailyDecision/u.test(source);
		});

		expect(offenders).toEqual([]);
	});
});
