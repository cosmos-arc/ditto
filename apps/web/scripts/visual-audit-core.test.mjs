import { describe, expect, it } from "vitest";
import {
	parseArgs,
	renderReport,
	resolvePages,
	USAGE,
	validateTargetKeyParity,
} from "./visual-audit-core.mjs";

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
		expect(() => parseArgs(["--viewport", "0x900"])).toThrow(
			"--viewport dimensions must be greater than zero",
		);
	});

	it("returns help usage without requiring bases", () => {
		expect(parseArgs(["--help"])).toEqual({ help: true });
		expect(USAGE).toContain("visual-audit");
	});

	it("resolves configured and concrete sample routes", () => {
		expect(resolvePages({ route: "/", all: false }, pages)).toHaveLength(1);
		expect(resolvePages({ route: "/instruments/600519", all: false }, pages)[0]?.route).toBe(
			"/instruments/$id",
		);
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
				prototype: ["Missing selector \"status\": .status-bar"],
				react: ["pageerror: boom"],
			},
		});

		expect(report).toContain('targets: prototype target "secondary" has no matching react target');
		expect(report).toContain("react: pageerror: boom");
	});
});
