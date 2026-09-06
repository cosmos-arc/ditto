import { describe, expect, it } from "vitest";
import {
	calculatePixelDiffRatio,
	evaluateVisualAudit,
	isIgnorableAssetUrl,
	isSuccessfulResponseStatus,
	NAVIGATION_WAIT_UNTIL,
	parseArgs,
	renderReport,
	resolvePages,
	shouldIgnoreRequestFailure,
	USAGE,
	validateTargetKeyParity,
} from "./visual-audit-core.mjs";
import {
	PROTOTYPE_NORMALIZE_CSS,
	VISUAL_AUDIT_PAGES,
} from "../visual-audit.config.generated.mjs";

const pages = [
	{
		route: "/",
		name: "home",
		prototype: "page-home.html",
		prototypeTargets: { shell: ".shell-home" },
		reactTargets: { shell: "#root > div" },
	},
	{
		route: "/instruments/$id",
		name: "instrument-hub",
		prototype: "page-instrument-hub.html",
		resolvedRoute: "/instruments/600519",
		prototypeTargets: { shell: ".shell-hub" },
		reactTargets: { shell: "#root > div" },
	},
];

describe("visual audit core", () => {
	it("carries contract thresholds into every generated visual audit page", () => {
		for (const page of VISUAL_AUDIT_PAGES) {
			expect(page.visualThresholds, page.name).toMatchObject({
				consoleErrors: 0,
				pageErrors: 0,
				missingSelectors: 0,
				targetMismatch: 0,
				pixelDiffRatio: expect.any(Number),
			});
			expect(page.targetThresholds, page.name).toEqual(expect.objectContaining({ header: expect.any(Object) }));
		}
	});

	it("normalizes object-hub prototypes against the outer shell geometry", () => {
		const strategyDetail = VISUAL_AUDIT_PAGES.find((page) => page.name === "strategies-detail");
		const reviewDetail = VISUAL_AUDIT_PAGES.find((page) => page.name === "review-detail");

		expect(strategyDetail?.prototypeTargets.header).toBe(".shell-header");
		expect(reviewDetail?.resolvedRoute).toBe(
			"/research/reviews/exp-rotation-v4?strategyId=seed_etf_industry_rotation&version=4",
		);
		expect(PROTOTYPE_NORMALIZE_CSS).toContain("#default-view > .shell-hub");
		expect(PROTOTYPE_NORMALIZE_CSS).toContain('.tab-panel[aria-hidden="false"]');
		expect(PROTOTYPE_NORMALIZE_CSS).toContain("grid-area: main !important");
		expect(PROTOTYPE_NORMALIZE_CSS).toContain("> .danger-confirmation-summary");
	});

	it("normalizes the legacy studio tray and compact sidebars to the live workspace geometry", () => {
		expect(PROTOTYPE_NORMALIZE_CSS).toContain("> .shell-studio > .studio-logs");
		expect(PROTOTYPE_NORMALIZE_CSS).toContain("height: 132px !important");
		expect(PROTOTYPE_NORMALIZE_CSS).toContain("--prototype-studio-source-width: 200px");
		expect(PROTOTYPE_NORMALIZE_CSS).toContain(":has(> .shell-studio) > .status-bar");
	});

	it("calculates an exact pixel diff ratio from equal-sized RGBA images", () => {
		const prototype = { width: 1, height: 1, data: new Uint8Array([0, 0, 0, 255]) };
		const matching = { width: 1, height: 1, data: new Uint8Array([0, 0, 0, 255]) };
		const changed = { width: 1, height: 1, data: new Uint8Array([255, 255, 255, 255]) };

		expect(calculatePixelDiffRatio(prototype, matching)).toBe(0);
		expect(calculatePixelDiffRatio(prototype, changed)).toBe(1);
		expect(() => calculatePixelDiffRatio(prototype, { ...changed, width: 2 })).toThrow("dimensions must match");
	});

	it("ignores only the browser favicon probe, not real asset failures", () => {
		expect(isIgnorableAssetUrl("http://127.0.0.1:8888/favicon.ico")).toBe(true);
		expect(isIgnorableAssetUrl("http://127.0.0.1:8888/assets/app.js")).toBe(false);
		expect(isIgnorableAssetUrl("")).toBe(false);
	});

	it("fails when a required header is displaced eight pixels beyond its contract threshold", () => {
		const result = evaluateVisualAudit(
			{
				prototype: {
					header: { rect: { x: 56, y: 0, width: 1480, height: 68 } },
				},
				react: {
					header: { rect: { x: 56, y: 8, width: 1480, height: 68 } },
				},
				warnings: { targets: [], prototype: [], react: [] },
				pixelDiffRatio: 0.01,
			},
			{
				targetThresholds: {
					header: { x: 4, y: 4, widthRatio: 0.03, heightRatio: 0.05 },
				},
				visualThresholds: {
					consoleErrors: 0,
					pageErrors: 0,
					missingSelectors: 0,
					targetMismatch: 0,
					pixelDiffRatio: 0.02,
				},
			},
		);

		expect(result.passed).toBe(false);
		expect(result.failures).toContainEqual(
			expect.objectContaining({ code: "geometry-y", target: "header", actual: 8, allowed: 4 }),
		);
	});

	it("fails closed on missing selectors, browser errors, target drift, and pixel drift", () => {
		const result = evaluateVisualAudit(
			{
				prototype: { main: null },
				react: { main: null },
				warnings: {
					targets: ['prototype target "detail" has no matching react target'],
					prototype: ['Missing selector "main": .main'],
					react: ["console error: render failed", "pageerror: broken page"],
				},
				pixelDiffRatio: 0.03,
			},
			{
				targetThresholds: {},
				visualThresholds: {
					consoleErrors: 0,
					pageErrors: 0,
					missingSelectors: 0,
					targetMismatch: 0,
					pixelDiffRatio: 0.02,
				},
			},
		);

		expect(result.passed).toBe(false);
		expect(result.failures.map((failure) => failure.code)).toEqual(
			expect.arrayContaining([
				"target-mismatch",
				"missing-selector",
				"console-error",
				"page-error",
				"pixel-diff",
			]),
		);
	});

	it("uses proportional width and height thresholds and accepts their boundary", () => {
		const result = evaluateVisualAudit(
			{
				prototype: {
					main: { rect: { x: 0, y: 0, width: 1000, height: 400 } },
				},
				react: {
					main: { rect: { x: 0, y: 0, width: 1030, height: 420 } },
				},
				warnings: { targets: [], prototype: [], react: [] },
				pixelDiffRatio: 0.02,
			},
			{
				targetThresholds: {
					main: { x: 4, y: 4, widthRatio: 0.03, heightRatio: 0.05 },
				},
				visualThresholds: {
					consoleErrors: 0,
					pageErrors: 0,
					missingSelectors: 0,
					targetMismatch: 0,
					pixelDiffRatio: 0.02,
				},
			},
		);

		expect(result).toEqual({ passed: true, failures: [] });
	});

	it("does not require network idle for live pages that poll", () => {
		expect(NAVIGATION_WAIT_UNTIL).toBe("load");
	});

	it("accepts cache revalidation responses as successful", () => {
		expect(isSuccessfulResponseStatus(200)).toBe(true);
		expect(isSuccessfulResponseStatus(304)).toBe(true);
		expect(isSuccessfulResponseStatus(404)).toBe(false);
	});

	it("ignores aborted speculative scripts but keeps real asset failures", () => {
		expect(shouldIgnoreRequestFailure("script", "net::ERR_ABORTED")).toBe(true);
		expect(shouldIgnoreRequestFailure("stylesheet", "net::ERR_ABORTED")).toBe(false);
		expect(shouldIgnoreRequestFailure("script", "net::ERR_CONNECTION_REFUSED")).toBe(false);
	});

	it("parses route options and viewport", () => {
		const options = parseArgs([
			"--route",
			"/",
			"--react-base",
			"http://127.0.0.1:5176",
			"--prototype-base",
			"http://127.0.0.1:8766",
			"--viewport",
			"1200x800",
		]);

		expect(options).toMatchObject({
			all: false,
			route: "/",
			reactBase: "http://127.0.0.1:5176",
			prototypeBase: "http://127.0.0.1:8766",
			viewport: { width: 1200, height: 800 },
		});
	});

	it("rejects non-positive viewport dimensions", () => {
		expect(() => parseArgs(["--viewport", "0x900"])).toThrow("--viewport dimensions must be greater than zero");
	});

	it("returns help usage without requiring bases", () => {
		expect(parseArgs(["--help"])).toEqual({ help: true });
		expect(USAGE).toContain("visual-audit");
	});

	it("resolves configured and concrete sample routes", () => {
		expect(resolvePages({ route: "/", all: false }, pages)).toHaveLength(1);
		expect(resolvePages({ route: "/instruments/600519", all: false }, pages)[0]?.route).toBe("/instruments/$id");
		expect(resolvePages({ all: true }, pages)).toHaveLength(2);
	});

	it("warns when target keys are missing their counterpart", () => {
		expect(
			validateTargetKeyParity({
				prototypeTargets: { main: ".main", secondary: ".secondary" },
				reactTargets: { main: "#main", sidebar: "#sidebar" },
			}),
		).toEqual([
			'prototype target "secondary" has no matching react target',
			'react target "sidebar" has no matching prototype target',
		]);
	});

	it("renders target parity and page issue warnings", () => {
		const report = renderReport({
			capturedAt: "2026-04-11T00:00:00.000Z",
			route: "/",
			resolvedRoute: "/",
			name: "home",
			prototypeFile: "page-home.html",
			urls: {
				react: "http://127.0.0.1:5176/",
				prototype: "http://127.0.0.1:8766/page-home.html",
			},
			viewport: { width: 1536, height: 900 },
			prototype: { shell: null },
			react: { shell: null },
			warnings: {
				targets: ['prototype target "secondary" has no matching react target'],
				prototype: ['Missing selector "status": .status-bar'],
				react: ["pageerror: boom"],
			},
			pixelDiffRatio: 0.04,
			evaluation: {
				passed: false,
				failures: [{ code: "geometry-y", target: "header", actual: 8, allowed: 4 }],
			},
		});

		expect(report).toContain('targets: prototype target "secondary" has no matching react target');
		expect(report).toContain("react: pageerror: boom");
		expect(report).toContain("Result: **FAIL**");
		expect(report).toContain("Pixel diff: **4.00%**");
		expect(report).toContain("geometry-y (header): actual 8, allowed 4");
	});
});
