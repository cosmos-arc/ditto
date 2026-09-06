#!/usr/bin/env bun

import { mkdir, writeFile } from "node:fs/promises";
import { join } from "node:path";
import { chromium } from "playwright";
import { PNG } from "pngjs";
import { PROTOTYPE_NORMALIZE_CSS, VISUAL_AUDIT_PAGES } from "../visual-audit.config.generated.mjs";
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

const FIXED_NOW = "2026-08-25T09:30:00+08:00";
const VISUAL_SETTLE_MS = 750;
const DETERMINISTIC_CSS = `
  *, *::before, *::after {
    animation: none !important;
    caret-color: transparent !important;
    transition: none !important;
  }
  .reveal-up {
    opacity: 1 !important;
    transform: none !important;
  }
`;

const STYLE_PROPS = [
	// Layout
	"display",
	"position",
	"width",
	"height",
	"padding",
	"gap",
	"gridTemplateRows",
	"gridTemplateColumns",
	// Visual effects
	"boxShadow",
	"backdropFilter",
	"WebkitBackdropFilter",
	"borderColor",
	"borderLeftColor",
	"borderBottomColor",
	"borderStyle",
	"opacity",
	"background",
	"backgroundImage",
	"filter",
	"transform",
	"zIndex",
	// Typography
	"fontFamily",
	"fontWeight",
	"fontSize",
	"letterSpacing",
	"fontFeatureSettings",
	"textRendering",
	"WebkitFontSmoothing",
	// Existing color/token props
	"borderRadius",
	"borderWidth",
	"lineHeight",
	"backgroundColor",
	"color",
];

/** Subset of properties relevant to pseudo-elements (::before / ::after). */
const PSEUDO_STYLE_PROPS = [
	"display",
	"position",
	"width",
	"height",
	"padding",
	"content",
	"background",
	"backgroundImage",
	"boxShadow",
	"opacity",
	"borderStyle",
	"borderColor",
	"borderWidth",
	"borderRadius",
	"filter",
	"transform",
	"zIndex",
	"top",
	"right",
	"bottom",
	"left",
	"clipPath",
	"pointerEvents",
];

function trimTrailingSlash(value) {
	return value.replace(/\/+$/, "");
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

function createPageIssueCollector(page) {
	const issues = [];

	page.on("requestfailed", (request) => {
		const failure = request.failure();
		if (shouldIgnoreRequestFailure(request.resourceType(), failure?.errorText ?? "")) {
			return;
		}
		issues.push(`requestfailed ${request.resourceType()} ${request.url()}: ${failure?.errorText ?? "unknown failure"}`);
	});
	page.on("response", (response) => {
		const request = response.request();
		if (
			request.resourceType() === "document" ||
			isSuccessfulResponseStatus(response.status()) ||
			isIgnorableAssetUrl(response.url())
		) {
			return;
		}
		issues.push(`response ${response.status()} ${request.resourceType()} ${response.url()}`);
	});
	page.on("pageerror", (error) => {
		issues.push(`pageerror: ${error.message}`);
	});
	page.on("console", (message) => {
		if (message.type() !== "error") {
			return;
		}
		if (isIgnorableAssetUrl(message.location().url)) {
			return;
		}
		const text = message.text().trim();
		if (text) {
			issues.push(`console error: ${text}`);
		}
	});

	return {
		issues,
	};
}

async function captureTargetMetrics(page, targets) {
	const metrics = {};
	const warnings = [];

	for (const [name, selector] of Object.entries(targets)) {
		if (!selector) continue;
		const element = await page.$(selector);
		if (!element) {
			metrics[name] = null;
			warnings.push(`Missing selector "${name}": ${selector}`);
			continue;
		}

		metrics[name] = await element.evaluate(
			(node, { props, pseudoProps }) => {
				const rect = node.getBoundingClientRect();
				const computed = window.getComputedStyle(node);
				const styles = Object.fromEntries(props.map((prop) => [prop, computed[prop]]));

				const pseudoStyles = {};
				for (const pseudo of ["::before", "::after"]) {
					const pseudoComputed = window.getComputedStyle(node, pseudo);
					const pseudoMap = Object.fromEntries(pseudoProps.map((prop) => [prop, pseudoComputed[prop]]));
					const content = pseudoComputed.content;
					const hasContent = content && content !== "none" && content !== '""';
					if (hasContent) {
						pseudoStyles[pseudo] = pseudoMap;
					}
				}

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
					pseudoStyles: Object.keys(pseudoStyles).length > 0 ? pseudoStyles : undefined,
				};
			},
			{ props: STYLE_PROPS, pseudoProps: PSEUDO_STYLE_PROPS },
		);
		metrics[name].selector = selector;
	}

	return { metrics, warnings };
}

async function openPage(page, url) {
	const response = await page.goto(url, {
		waitUntil: NAVIGATION_WAIT_UNTIL,
		timeout: 30_000,
	});

	if (!response?.ok()) {
		const status = response?.status() ?? "no response";
		throw new Error(`Failed to load ${url}: ${status}`);
	}
}

async function prepareDeterministicPage(page) {
	await page.emulateMedia({ reducedMotion: "reduce" });
	await page.addInitScript((fixedNow) => {
		const NativeDate = Date;
		const epoch = NativeDate.parse(fixedNow);
		class FrozenDate extends NativeDate {
			constructor(...args) {
				super(...(args.length === 0 ? [epoch] : args));
			}

			static now() {
				return epoch;
			}
		}
		Object.defineProperty(globalThis, "Date", { configurable: true, value: FrozenDate });
	}, FIXED_NOW);
}

async function auditPage(browser, config, options) {
	const urls = buildUrls(config, options);
	const routeOutDir = join(options.outDir, config.name);
	await mkdir(routeOutDir, { recursive: true });

	const prototypePage = await browser.newPage({ viewport: options.viewport });
	const reactPage = await browser.newPage({ viewport: options.viewport });
	const prototypeIssues = createPageIssueCollector(prototypePage);
	const reactIssues = createPageIssueCollector(reactPage);
	const targetWarnings = validateTargetKeyParity(config);

	try {
		await Promise.all([prepareDeterministicPage(prototypePage), prepareDeterministicPage(reactPage)]);
		await openPage(prototypePage, urls.prototype);
		await prototypePage.addStyleTag({ content: `${PROTOTYPE_NORMALIZE_CSS}\n${DETERMINISTIC_CSS}` });
		await prototypePage.waitForLoadState("networkidle");
		await prototypePage.evaluate(() => document.fonts.ready);

		await openPage(reactPage, urls.react);
		await reactPage.addStyleTag({ content: DETERMINISTIC_CSS });
		await reactPage.waitForSelector("[data-slot='header']", { state: "attached", timeout: 10_000 });
		await reactPage.waitForTimeout(VISUAL_SETTLE_MS);
		await reactPage.evaluate(() => document.fonts.ready);

		const prototype = await captureTargetMetrics(prototypePage, config.prototypeTargets);
		const react = await captureTargetMetrics(reactPage, config.reactTargets);

		const prototypeScreenshot = await prototypePage.screenshot({
			path: join(routeOutDir, "prototype.png"),
			fullPage: false,
		});
		const reactScreenshot = await reactPage.screenshot({
			path: join(routeOutDir, "react.png"),
			fullPage: false,
		});
		const pixelDiffRatio = calculatePixelDiffRatio(
			PNG.sync.read(prototypeScreenshot),
			PNG.sync.read(reactScreenshot),
		);

		const capturedMetrics = {
			capturedAt: new Date().toISOString(),
			route: config.route,
			resolvedRoute: config.resolvedRoute ?? config.route,
			name: config.name,
			prototypeFile: config.prototype,
			urls,
			viewport: options.viewport,
			prototype: prototype.metrics,
			react: react.metrics,
			pixelDiffRatio,
			warnings: {
				targets: targetWarnings,
				prototype: [...prototype.warnings, ...prototypeIssues.issues],
				react: [...react.warnings, ...reactIssues.issues],
			},
		};
		const evaluation = evaluateVisualAudit(capturedMetrics, config);
		const metrics = { ...capturedMetrics, evaluation };

		await writeFile(join(routeOutDir, "metrics.json"), `${JSON.stringify(metrics, null, 2)}\n`, "utf8");
		await writeFile(join(routeOutDir, "report.md"), renderReport(metrics), "utf8");

		return {
			name: config.name,
			route: config.route,
			outDir: routeOutDir,
			passed: evaluation.passed,
			failures: evaluation.failures,
			warnings: metrics.warnings.targets.length + metrics.warnings.prototype.length + metrics.warnings.react.length,
		};
	} finally {
		await prototypePage.close();
		await reactPage.close();
	}
}

async function main() {
	const options = parseArgs(process.argv.slice(2));
	if (options.help) {
		console.log(USAGE);
		return;
	}
	const pages = resolvePages(options, VISUAL_AUDIT_PAGES);
	const browser = await chromium.launch({ channel: "chromium" });

	try {
		const results = [];
		for (const page of pages) {
			results.push(await auditPage(browser, page, options));
		}

		for (const result of results) {
			console.log(
				`${result.passed ? "PASS" : "FAIL"} ${result.route} (${result.name}) -> ${result.outDir} with ${result.warnings} warnings`,
			);
		}

		const failed = results.filter((result) => !result.passed);
		if (failed.length > 0) {
			throw new Error(
				`Visual audit failed for ${failed.map((result) => `${result.route}: ${result.failures.length} blocker(s)`).join(", ")}`,
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
