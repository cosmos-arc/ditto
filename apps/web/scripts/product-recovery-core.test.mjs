import { describe, expect, it } from "vitest";
import {
	activePrototypePages,
	buildPrototypeBaselineRecord,
	summarizePageCompletion,
} from "./product-recovery-core.mjs";

describe("product recovery evidence", () => {
	it("selects only active page prototypes for the frozen baseline", () => {
		const pages = activePrototypePages({
			pages: [
				{ id: "home", file: "page-home.html", status: "reviewed" },
				{ id: "token-showcase", file: "page-token-showcase.html", status: "reviewed" },
				{ id: "ai-copilot", file: "page-ai-copilot.html", status: "reviewed" },
				{ id: "legacy", file: "page-legacy.html", status: "archived-specimen" },
			],
		});

		expect(pages.map((page) => page.id)).toEqual(["home"]);
	});

	it("refuses to build a frozen record without source and screenshot hashes", () => {
		expect(() =>
			buildPrototypeBaselineRecord({
				baselineCommit: "abc123",
				browserVersion: "Chromium 1",
				capturedAt: "2026-08-29",
				pages: [{ id: "home", file: "page-home.html" }],
				artifacts: new Map(),
			}),
		).toThrow("home");
	});

	it("does not confuse a verified prototype with verified React parity", () => {
		const summary = summarizePageCompletion({
			route: "/portfolio/model",
			landing: {
				reactRouteStatus: "implemented",
				prototypeVerified: true,
				reactParityVerified: false,
				reactTestRefs: ["src/features/portfolio/components/portfolio/model-components.test.tsx"],
			},
			liveData: { readPaths: ["/api/v1/trade/daily-decision/v3"], mockFallback: false },
			states: { universal: ["loading", "empty", "error", "stale"], pageSpecific: ["blocked"] },
			overlays: [
				{ reactComponent: "TradingPositionDetailDrawer" },
				{ reactComponent: "PrototypeOnlyOverlay" },
			],
		});

		expect(summary.route).toBe("verified");
		expect(summary.liveData).toBe("wired");
		expect(summary.visualParity).toBe("pending");
		expect(summary.states).toEqual({ declared: 5, testRefs: 1 });
		expect(summary.overlays).toEqual({ concrete: 1, total: 2 });
		expect(summary.workflow).toBe("pending");
	});

	it("recognizes a governed write-only page as wired live data", () => {
		const summary = summarizePageCompletion({
			landing: {
				reactRouteStatus: "implemented",
				reactParityVerified: true,
				reactTestRefs: ["src/features/research/components/experiment-create-page.test.tsx"],
			},
			liveData: {
				readPaths: [],
				writePaths: ["/api/v1/research/experiments/{experiment_id}/preflight"],
				mockFallback: false,
			},
			states: { universal: ["loading", "empty", "error", "stale"], pageSpecific: [] },
			overlays: [],
		});

		expect(summary.liveData).toBe("wired");
		expect(summary.workflow).toBe("verified");
	});
});
