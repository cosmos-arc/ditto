#!/usr/bin/env bun

import { mkdir, writeFile } from "node:fs/promises";
import { join } from "node:path";
import { chromium } from "playwright";
import {
	PROTOTYPE_NORMALIZE_CSS,
	VISUAL_AUDIT_PAGES,
} from "./visual-audit.config.mjs";

const DEFAULT_VIEWPORT = { width: 1536, height: 900 };
const DEFAULT_OUT_DIR = "docs/review/visual-audit";
const STYLE_PROPS = [
	"display",
	"position",
	"width",
	"height",
	"padding",
	"gap",
	"gridTemplateRows",
	"gridTemplateColumns",
	"fontSize",
	"lineHeight",
	"borderRadius",
	"borderWidth",
	"backgroundColor",
	"color",
];

function parseArgs(argv) {
	const options = {
		all: false,
		outDir: DEFAULT_OUT_DIR,
		viewport: DEFAULT_VIEWPORT,
	};

	for (let index = 0; index < argv.length; index += 1) {
		const arg = argv[index];
		if (arg === "--all") {
			options.all = true;
			continue;
		}

		const next = argv[index + 1];
		if (!next) {
			throw new Error(`Missing value for ${arg}`);
		}

		if (arg === "--route") {
			options.route = next;
		} else if (arg === "--react-base") {
			options.reactBase = next;
		} else if (arg === "--prototype-base") {
			options.prototypeBase = next;
		} else if (arg === "--viewport") {
			options.viewport = parseViewport(next);
		} else if (arg === "--out-dir") {
			options.outDir = next;
		} else {
			throw new Error(`Unknown option: ${arg}`);
		}
		index += 1;
	}

	if (!options.reactBase) {
		throw new Error("Missing required --react-base");
	}
	if (!options.prototypeBase) {
		throw new Error("Missing required --prototype-base");
	}
	if (options.all === Boolean(options.route)) {
		throw new Error("Pass exactly one of --route <route> or --all");
	}

	return options;
}

function parseViewport(value) {
	const match = value.match(/^(\d+)x(\d+)$/);
	if (!match) {
		throw new Error(`Invalid --viewport "${value}". Expected WIDTHxHEIGHT.`);
	}

	return {
		width: Number.parseInt(match[1], 10),
		height: Number.parseInt(match[2], 10),
	};
}

function trimTrailingSlash(value) {
	return value.replace(/\/+$/, "");
}

function resolvePages(options) {
	if (options.all) {
		return VISUAL_AUDIT_PAGES;
	}

	const page = VISUAL_AUDIT_PAGES.find(
		(item) => item.route === options.route || item.resolvedRoute === options.route,
	);
	if (!page) {
		const knownRoutes = VISUAL_AUDIT_PAGES.map((item) => item.route).join(", ");
		throw new Error(`Unknown route "${options.route}". Known routes: ${knownRoutes}`);
	}
	return [page];
}

function buildUrls(config, options) {
	const reactBase = trimTrailingSlash(options.reactBase);
	const prototypeBase = trimTrailingSlash(options.prototypeBase);
	const reactPath = config.resolvedRoute ?? config.route;

	return {
		react: `${reactBase}${reactPath}`,
		prototype: `${prototypeBase}/${config.prototype}`,
	};
}

async function captureTargetMetrics(page, targets) {
	const metrics = {};
	const warnings = [];

	for (const [name, selector] of Object.entries(targets)) {
		const element = await page.$(selector);
		if (!element) {
			metrics[name] = null;
			warnings.push(`Missing selector "${name}": ${selector}`);
			continue;
		}

		metrics[name] = await element.evaluate((node, props) => {
			const rect = node.getBoundingClientRect();
			const computed = window.getComputedStyle(node);
			const styles = Object.fromEntries(
				props.map((prop) => [prop, computed[prop]]),
			);

			return {
				selector: undefined,
				rect: {
					x: Math.round(rect.x * 100) / 100,
					y: Math.round(rect.y * 100) / 100,
					width: Math.round(rect.width * 100) / 100,
					height: Math.round(rect.height * 100) / 100,
					top: Math.round(rect.top * 100) / 100,
					right: Math.round(rect.right * 100) / 100,
					bottom: Math.round(rect.bottom * 100) / 100,
					left: Math.round(rect.left * 100) / 100,
				},
				styles,
			};
		}, STYLE_PROPS);
		metrics[name].selector = selector;
	}

	return { metrics, warnings };
}

async function openPage(page, url) {
	const response = await page.goto(url, {
		waitUntil: "networkidle",
		timeout: 30_000,
	});

	if (!response?.ok()) {
		const status = response?.status() ?? "no response";
		throw new Error(`Failed to load ${url}: ${status}`);
	}
}

async function auditPage(browser, config, options) {
	const urls = buildUrls(config, options);
	const routeOutDir = join(options.outDir, config.name);
	await mkdir(routeOutDir, { recursive: true });

	const prototypePage = await browser.newPage({ viewport: options.viewport });
	const reactPage = await browser.newPage({ viewport: options.viewport });

	try {
		await openPage(prototypePage, urls.prototype);
		await prototypePage.addStyleTag({ content: PROTOTYPE_NORMALIZE_CSS });
		await prototypePage.waitForLoadState("networkidle");

		await openPage(reactPage, urls.react);

		const prototype = await captureTargetMetrics(
			prototypePage,
			config.prototypeTargets,
		);
		const react = await captureTargetMetrics(reactPage, config.reactTargets);

		await prototypePage.screenshot({
			path: join(routeOutDir, "prototype.png"),
			fullPage: false,
		});
		await reactPage.screenshot({
			path: join(routeOutDir, "react.png"),
			fullPage: false,
		});

		const metrics = {
			capturedAt: new Date().toISOString(),
			route: config.route,
			resolvedRoute: config.resolvedRoute ?? config.route,
			name: config.name,
			prototypeFile: config.prototype,
			urls,
			viewport: options.viewport,
			prototype: prototype.metrics,
			react: react.metrics,
			warnings: {
				prototype: prototype.warnings,
				react: react.warnings,
			},
		};

		await writeFile(
			join(routeOutDir, "metrics.json"),
			`${JSON.stringify(metrics, null, 2)}\n`,
			"utf8",
		);
		await writeFile(
			join(routeOutDir, "report.md"),
			renderReport(metrics),
			"utf8",
		);

		return {
			name: config.name,
			route: config.route,
			outDir: routeOutDir,
			warnings: prototype.warnings.length + react.warnings.length,
		};
	} finally {
		await prototypePage.close();
		await reactPage.close();
	}
}

function renderReport(metrics) {
	const names = [
		...new Set([
			...Object.keys(metrics.prototype),
			...Object.keys(metrics.react),
		]),
	];
	const lines = [
		`# Visual Audit: ${metrics.name}`,
		"",
		`- Route: \`${metrics.route}\``,
		`- React URL: ${metrics.urls.react}`,
		`- Prototype URL: ${metrics.urls.prototype}`,
		`- Viewport: ${metrics.viewport.width}x${metrics.viewport.height}`,
		`- Captured: ${metrics.capturedAt}`,
		"",
		"## Target Rect Deltas",
		"",
		"| Target | Prototype | React | Δx | Δy | Δw | Δh |",
		"| --- | --- | --- | ---: | ---: | ---: | ---: |",
	];

	for (const name of names) {
		const prototype = metrics.prototype[name];
		const react = metrics.react[name];
		const delta = buildRectDelta(prototype?.rect, react?.rect);
		lines.push(
			[
				`| ${name}`,
				formatRect(prototype?.rect),
				formatRect(react?.rect),
				delta ? formatNumber(delta.x) : "n/a",
				delta ? formatNumber(delta.y) : "n/a",
				delta ? formatNumber(delta.width) : "n/a",
				delta ? formatNumber(delta.height) : "n/a",
			].join(" | ") + " |",
		);
	}

	const warnings = [
		...metrics.warnings.prototype.map((warning) => `prototype: ${warning}`),
		...metrics.warnings.react.map((warning) => `react: ${warning}`),
	];

	lines.push("", "## Warnings", "");
	if (warnings.length === 0) {
		lines.push("No missing target selectors.");
	} else {
		for (const warning of warnings) {
			lines.push(`- ${warning}`);
		}
	}

	lines.push("");
	return `${lines.join("\n")}`;
}

function buildRectDelta(prototype, react) {
	if (!prototype || !react) return null;

	return {
		x: react.x - prototype.x,
		y: react.y - prototype.y,
		width: react.width - prototype.width,
		height: react.height - prototype.height,
	};
}

function formatRect(rect) {
	if (!rect) return "missing";
	return `${formatNumber(rect.x)}, ${formatNumber(rect.y)}, ${formatNumber(rect.width)}x${formatNumber(rect.height)}`;
}

function formatNumber(value) {
	return Number.isInteger(value) ? `${value}` : value.toFixed(2);
}

async function main() {
	const options = parseArgs(process.argv.slice(2));
	const pages = resolvePages(options);
	const browser = await chromium.launch();

	try {
		const results = [];
		for (const page of pages) {
			results.push(await auditPage(browser, page, options));
		}

		for (const result of results) {
			console.log(
				`Wrote ${result.route} (${result.name}) to ${result.outDir} with ${result.warnings} warnings`,
			);
		}
	} finally {
		await browser.close();
	}
}

main().catch((error) => {
	console.error(error instanceof Error ? error.message : error);
	process.exit(1);
});
