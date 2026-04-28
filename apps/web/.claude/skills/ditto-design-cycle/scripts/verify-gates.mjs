#!/usr/bin/env bun

import { createServer } from "node:http";
import { mkdir, readFile, stat, writeFile } from "node:fs/promises";
import { basename, extname, join, relative, resolve, sep } from "node:path";
import { chromium } from "playwright";
import {
	buildGateSummary,
	parseArgs,
	toIssue,
} from "./verify-gates-core.mjs";

const DEFAULT_OUT_DIR = "test-results/ditto-design-cycle-gates";
const USAGE = `Usage:
  bun .claude/skills/ditto-design-cycle/scripts/verify-gates.mjs --prototype <path-to-html>

Options:
  --prototype <path>       Prototype HTML file to verify.
  --viewport <LABEL=WxH>   Viewport to verify. Can be passed multiple times.
                           Default: VP-STANDARD=1536x1080 and VP-COMPACT=1366x768.
  --out-dir <path>         Output directory. Default: test-results/ditto-design-cycle-gates.
  --strict                 Treat P2 findings as blocking.
  --help                   Show this help.
`;

async function main() {
	const options = parseArgs(process.argv.slice(2));
	if (options.help) {
		console.log(USAGE);
		return;
	}

	const prototypePath = resolve(process.cwd(), options.prototype);
	await ensureFileExists(prototypePath);

	const outDir = resolve(process.cwd(), options.outDir ?? DEFAULT_OUT_DIR);
	await mkdir(outDir, { recursive: true });

	const staticServer = await startStaticServer(process.cwd());
	const browser = await chromium.launch({ channel: "chromium" });
	const allIssues = [];
	const captures = [];

	try {
		for (const viewport of options.viewports) {
			const pageResult = await verifyViewport(
				browser,
				prototypePath,
				staticServer.baseUrl,
				viewport,
				outDir,
			);
			allIssues.push(...pageResult.issues);
			captures.push(pageResult.capture);
		}
	} finally {
		await browser.close();
		await staticServer.close();
	}

	const summary = buildGateSummary(allIssues, { strict: options.strict });
	const report = renderReport({
		prototypePath,
		viewports: options.viewports,
		captures,
		summary,
	});
	await writeFile(join(outDir, "report.md"), report, "utf8");
	await writeFile(
		join(outDir, "summary.json"),
		`${JSON.stringify({ prototypePath, captures, summary }, null, 2)}\n`,
		"utf8",
	);

	console.log(report);
	if (summary.status === "fail") {
		process.exit(1);
	}
}

async function ensureFileExists(path) {
	const fileStat = await stat(path).catch(() => null);
	if (!fileStat?.isFile()) {
		throw new Error(`Prototype file not found: ${path}`);
	}
}

async function verifyViewport(browser, prototypePath, baseUrl, viewport, outDir) {
	const page = await browser.newPage({
		viewport: { width: viewport.width, height: viewport.height },
	});
	const pageIssues = createPageIssueCollector(page);
	const issues = [];

	try {
		const prototypeUrl = `${baseUrl}/${toUrlPath(relative(process.cwd(), prototypePath))}`;
		const response = await page.goto(prototypeUrl, {
			waitUntil: "networkidle",
			timeout: 30_000,
		});
		if (!response?.ok() && response?.status() !== 0) {
			issues.push(
				toIssue(
					"load",
					"P0",
					`${viewport.label}: failed to load prototype document`,
					{ status: response?.status() ?? "no response" },
				),
			);
		}
		await page.waitForFunction(() => document.fonts.ready, null, {
			timeout: 5_000,
		}).catch(() => {
			issues.push(
				toIssue("gate-1-css", "P1", `${viewport.label}: document fonts did not settle`),
			);
		});

		issues.push(...classifyPageIssues(pageIssues.issues, viewport.label));
		issues.push(...(await checkToolUiIsolation(page, viewport.label)));
		issues.push(...(await checkCssResources(page, viewport.label)));
		issues.push(...(await checkShellStructure(page, viewport.label)));
		issues.push(...(await checkViewportIntegrity(page, viewport.label)));
		issues.push(...(await checkFixedStickyOverlap(page, viewport.label)));

		const screenshotPath = join(outDir, `${safeName(basename(prototypePath))}-${viewport.label}.png`);
		await page.screenshot({ path: screenshotPath, fullPage: true });

		return {
			issues,
			capture: {
				viewport,
				screenshotPath,
			},
		};
	} finally {
		await page.close();
	}
}

async function startStaticServer(rootDir) {
	const root = resolve(rootDir);
	const server = createServer(async (request, response) => {
		try {
			const requestUrl = new URL(request.url ?? "/", "http://127.0.0.1");
			const pathname = decodeURIComponent(requestUrl.pathname);
			if (pathname === "/favicon.ico") {
				response.writeHead(204);
				response.end();
				return;
			}
			const candidate = resolve(root, `.${pathname}`);
			if (candidate !== root && !candidate.startsWith(`${root}${sep}`)) {
				response.writeHead(403);
				response.end("Forbidden");
				return;
			}
			const file = await readFile(candidate);
			response.writeHead(200, { "content-type": contentTypeFor(candidate) });
			response.end(file);
		} catch {
			response.writeHead(404);
			response.end("Not found");
		}
	});

	await new Promise((resolveListen, rejectListen) => {
		server.once("error", rejectListen);
		server.listen(0, "127.0.0.1", () => {
			server.off("error", rejectListen);
			resolveListen();
		});
	});

	const address = server.address();
	if (!address || typeof address === "string") {
		throw new Error("Failed to start static server");
	}

	return {
		baseUrl: `http://127.0.0.1:${address.port}`,
		close: () =>
			new Promise((resolveClose, rejectClose) => {
				server.close((error) => {
					if (error) {
						rejectClose(error);
					} else {
						resolveClose();
					}
				});
			}),
	};
}

function contentTypeFor(path) {
	const extension = extname(path);
	if (extension === ".html") return "text/html; charset=utf-8";
	if (extension === ".css") return "text/css; charset=utf-8";
	if (extension === ".js") return "text/javascript; charset=utf-8";
	if (extension === ".svg") return "image/svg+xml";
	if (extension === ".png") return "image/png";
	if (extension === ".jpg" || extension === ".jpeg") return "image/jpeg";
	if (extension === ".woff2") return "font/woff2";
	return "application/octet-stream";
}

function createPageIssueCollector(page) {
	const issues = [];

	page.on("requestfailed", (request) => {
		const failure = request.failure();
		issues.push({
			type: "requestfailed",
			resourceType: request.resourceType(),
			url: request.url(),
			message: failure?.errorText ?? "unknown failure",
		});
	});
	page.on("response", (response) => {
		const request = response.request();
		if (request.resourceType() === "document" || response.ok()) {
			return;
		}
		issues.push({
			type: "response",
			resourceType: request.resourceType(),
			url: response.url(),
			message: `${response.status()}`,
		});
	});
	page.on("pageerror", (error) => {
		issues.push({
			type: "pageerror",
			resourceType: "script",
			url: page.url(),
			message: error.message,
		});
	});
	page.on("console", (message) => {
		if (message.type() !== "error") {
			return;
		}
		const text = message.text().trim();
		if (text) {
			issues.push({
				type: "console",
				resourceType: "console",
				url: page.url(),
				message: text,
			});
		}
	});

	return { issues };
}

function classifyPageIssues(pageIssues, viewportLabel) {
	return pageIssues.map((issue) => {
		const isLocalCss =
			issue.resourceType === "stylesheet" &&
			(issue.url.startsWith("file://") || issue.url.includes("/docs/"));
		const severity = isLocalCss || issue.type === "pageerror" ? "P0" : "P1";
		return toIssue(
			"gate-1-css",
			severity,
			`${viewportLabel}: ${issue.type} ${issue.resourceType} ${issue.message}`,
			{ url: issue.url },
		);
	});
}

async function checkToolUiIsolation(page, viewportLabel) {
	const result = await page.evaluate(() => {
		const checkedDefaultView = document.querySelector("#view-default")?.checked ?? false;
		const selectors = [".proto-nav", ".style-label", ".skip-link"];
		const visibleTools = [];

		for (const selector of selectors) {
			for (const element of document.querySelectorAll(selector)) {
				const rect = element.getBoundingClientRect();
				const computed = getComputedStyle(element);
				const intersectsViewport =
					rect.right > 0 &&
					rect.bottom > 0 &&
					rect.left < window.innerWidth &&
					rect.top < window.innerHeight;
				const isVisible =
					computed.display !== "none" &&
					computed.visibility !== "hidden" &&
					Number.parseFloat(computed.opacity || "1") > 0 &&
					rect.width > 0 &&
					rect.height > 0 &&
					intersectsViewport;
				const isGalleryTool = Boolean(element.closest("#states-gallery, #overlays-gallery"));
				if (isVisible && !isGalleryTool) {
					visibleTools.push({
						selector,
						rect: rectToJson(rect),
					});
				}
			}
		}

		return { checkedDefaultView, visibleTools };

		function rectToJson(rect) {
			return {
				x: Math.round(rect.x),
				y: Math.round(rect.y),
				width: Math.round(rect.width),
				height: Math.round(rect.height),
			};
		}
	});

	const issues = [];
	if (!result.checkedDefaultView) {
		issues.push(
			toIssue("gate-0-tool-ui", "P0", `${viewportLabel}: #view-default is not checked`),
		);
	}
	for (const tool of result.visibleTools) {
		issues.push(
			toIssue(
				"gate-0-tool-ui",
				"P0",
				`${viewportLabel}: prototype tool UI is visible (${tool.selector})`,
				tool.rect,
			),
		);
	}
	return issues;
}

async function checkCssResources(page, viewportLabel) {
	const result = await page.evaluate(() => {
		const stylesheets = Array.from(document.styleSheets).map((sheet) => {
			try {
				return {
					href: sheet.href,
					rules: sheet.cssRules.length,
					ok: true,
				};
			} catch (error) {
				return {
					href: sheet.href,
					rules: 0,
					ok: false,
					error: error instanceof Error ? error.message : String(error),
				};
			}
		});
		const tokenSheets = stylesheets.filter((sheet) => {
			const href = sheet.href ?? "";
			return href.includes("tokens-") || href.endsWith("tokens-style.css");
		});
		const rootStyle = getComputedStyle(document.documentElement);
		const variables = ["--font-size-12", "--text-primary"].map((name) => ({
			name,
			value: rootStyle.getPropertyValue(name).trim(),
		}));

		return { tokenSheets, variables };
	});

	const issues = [];
	if (result.tokenSheets.length === 0) {
		issues.push(
			toIssue("gate-1-css", "P0", `${viewportLabel}: no token CSS stylesheets loaded`),
		);
	}
	for (const sheet of result.tokenSheets) {
		if (!sheet.ok || sheet.rules <= 0) {
			issues.push(
				toIssue(
					"gate-1-css",
					"P0",
					`${viewportLabel}: token stylesheet has no readable rules`,
					{ href: sheet.href, rules: sheet.rules, error: sheet.error },
				),
			);
		}
	}
	for (const variable of result.variables) {
		if (!variable.value) {
			issues.push(
				toIssue(
					"gate-1-css",
					"P0",
					`${viewportLabel}: critical token variable is empty (${variable.name})`,
				),
			);
		}
	}
	return issues;
}

async function checkShellStructure(page, viewportLabel) {
	const result = await page.evaluate(() => {
		const view = document.getElementById("default-view");
		if (!view) {
			return { error: "#default-view not found" };
		}
		const shell = findShell(view);
		if (!shell) {
			return { error: "shell root not found" };
		}

		const rect = shell.getBoundingClientRect();
		const computed = getComputedStyle(shell);
		const isRadar = shell.classList.contains("shell-radar");
		const gridColumns =
			computed.display === "grid"
				? computed.gridTemplateColumns.split(" ").filter(Boolean).length
				: 0;
		const areas = {
			rail: findVisible(".shell-rail, [data-contract-slot='rail']"),
			header: findVisible(".shell-header, .studio-header, .object-header, [data-contract-slot='header']"),
			main: findVisible(
				".shell-main, .ai-main, .ops-main, .main-content, .main-grid, .studio-main, .catalog-main, .object-main, [data-contract-slot='main']",
			),
			secondary: findVisible(
				".shell-sidebar, .ai-inspector, .ops-detail, .right-rail, .studio-inspector, .catalog-detail, [data-contract-slot='sidebar'], [data-contract-slot='detail'], [data-contract-slot='right-rail'], [data-contract-slot='inspector']",
			),
		};

		return {
			rect: rectToJson(rect),
			display: computed.display,
			gridColumns,
			isRadar,
			areas,
		};

		function findShell(root) {
			const directShell = Array.from(root.children).find((element) =>
				element.matches(
					".shell-v2, .shell-home, .shell-analytical, .shell-radar, .shell-ops, .shell-studio, .ai-shell, .intel-shell, .risk-shell, .studio-shell, .object-shell, .catalog-shell",
				),
			);
			return (
				directShell ??
				root.querySelector(
					".shell-v2, .shell-home, .shell-analytical, .shell-radar, .shell-ops, .shell-studio, .ai-shell, .intel-shell, .risk-shell, .studio-shell, .object-shell, .catalog-shell",
				)
			);
		}

		function findVisible(selector) {
			const element = document.querySelector(selector);
			if (!element) return null;
			const elementRect = element.getBoundingClientRect();
			return {
				selector,
				width: Math.round(elementRect.width),
				height: Math.round(elementRect.height),
			};
		}

		function rectToJson(elementRect) {
			return {
				width: Math.round(elementRect.width),
				height: Math.round(elementRect.height),
			};
		}
	});

	if (result.error) {
		return [toIssue("gate-2-shell", "P0", `${viewportLabel}: ${result.error}`)];
	}

	const issues = [];
	if (result.rect.width <= 0 || result.rect.height <= 0) {
		issues.push(toIssue("gate-2-shell", "P0", `${viewportLabel}: shell has zero size`));
	}
	if (result.display !== "grid" && !(result.isRadar && result.display === "flex")) {
		issues.push(
			toIssue(
				"gate-2-shell",
				"P0",
				`${viewportLabel}: shell display must be grid, or flex for shell-radar`,
				{ display: result.display },
			),
		);
	}
	if (result.display === "grid" && result.gridColumns < 2) {
		issues.push(
			toIssue("gate-2-shell", "P0", `${viewportLabel}: shell grid has fewer than 2 columns`, {
				gridColumns: result.gridColumns,
			}),
		);
	}
	for (const [area, rect] of Object.entries(result.areas)) {
		if (!rect || rect.width <= 0 || rect.height <= 0) {
			const severity = area === "secondary" ? "P1" : "P0";
			issues.push(
				toIssue("gate-2-shell", severity, `${viewportLabel}: shell area is missing or empty (${area})`),
			);
		}
	}
	return issues;
}

async function checkViewportIntegrity(page, viewportLabel) {
	const result = await page.evaluate(() => {
		const bodyStyle = getComputedStyle(document.body);
		const scrollingElement = document.scrollingElement ?? document.documentElement;
		const keyContainers = Array.from(
			document.querySelectorAll(
				".main-content, .tab-band, .tab-content, footer, [role='tabpanel'], .panel-body, .table-container, [data-contract-slot]",
			),
		);
		const hiddenElements = [];
		for (const element of keyContainers) {
			const rect = element.getBoundingClientRect();
			if (rect.width <= 0 || rect.height <= 0) continue;
			if (rect.bottom > window.innerHeight && !hasScrollableAncestor(element)) {
				hiddenElements.push({
					selector: describeElement(element),
					bottom: Math.round(rect.bottom),
					cutoff: Math.round(rect.bottom - window.innerHeight),
				});
			}
		}

		return {
			scrollHeight: Math.round(scrollingElement.scrollHeight),
			clientHeight: Math.round(scrollingElement.clientHeight),
			overflowY: bodyStyle.overflowY,
			hiddenElements: hiddenElements.slice(0, 12),
		};

		function hasScrollableAncestor(element) {
			let current = element.parentElement;
			while (current && current !== document.body) {
				const style = getComputedStyle(current);
				const canScroll = /(auto|scroll)/.test(style.overflowY);
				if (canScroll && current.scrollHeight > current.clientHeight) {
					return true;
				}
				current = current.parentElement;
			}
			return false;
		}

		function describeElement(element) {
			if (element.id) return `#${element.id}`;
			if (element.getAttribute("data-contract-slot")) {
				return `[data-contract-slot="${element.getAttribute("data-contract-slot")}"]`;
			}
			if (typeof element.className === "string" && element.className.trim()) {
				return `.${element.className.trim().split(/\s+/).join(".")}`;
			}
			return element.tagName.toLowerCase();
		}
	});

	const issues = [];
	if (
		result.scrollHeight > result.clientHeight &&
		result.overflowY === "hidden"
	) {
		issues.push(
			toIssue(
				"viewport",
				"P0",
				`${viewportLabel}: body/document content is taller than viewport while overflow-y is hidden`,
				{
					scrollHeight: result.scrollHeight,
					clientHeight: result.clientHeight,
				},
			),
		);
	}
	for (const element of result.hiddenElements) {
		const severity = element.cutoff >= 20 ? "P0" : "P1";
		issues.push(
			toIssue("viewport", severity, `${viewportLabel}: key container extends below viewport`, element),
		);
	}
	return issues;
}

async function checkFixedStickyOverlap(page, viewportLabel) {
	const result = await page.evaluate(() => {
		const allElements = Array.from(document.querySelectorAll("body *"));
		const fixedOrSticky = allElements.filter((element) => {
			const position = getComputedStyle(element).position;
			return position === "fixed" || position === "sticky";
		});
		const candidates = allElements.filter((element) =>
			element.matches(
				"button, a, input, select, textarea, table, [role='button'], [role='tabpanel'], [data-contract-slot], .panel, .table-container",
			),
		);
		const overlaps = [];

		for (const overlay of fixedOrSticky) {
			const overlayRect = overlay.getBoundingClientRect();
			if (!isMeaningfulRect(overlayRect)) continue;
			for (const element of candidates) {
				if (element === overlay || overlay.contains(element) || element.contains(overlay)) {
					continue;
				}
				if (getComputedStyle(element).position === "fixed") continue;
				const elementRect = element.getBoundingClientRect();
				if (!isMeaningfulRect(elementRect)) continue;
				const overlapWidth =
					Math.min(elementRect.right, overlayRect.right) -
					Math.max(elementRect.left, overlayRect.left);
				const overlapHeight =
					Math.min(elementRect.bottom, overlayRect.bottom) -
					Math.max(elementRect.top, overlayRect.top);
				if (overlapWidth > 5 && overlapHeight > 5) {
					overlaps.push({
						overlay: describeElement(overlay),
						overlapped: describeElement(element),
						overlapWidth: Math.round(overlapWidth),
						overlapHeight: Math.round(overlapHeight),
					});
				}
			}
		}

		return { overlaps: overlaps.slice(0, 12) };

		function isMeaningfulRect(rect) {
			return rect.width > 0 && rect.height > 0;
		}

		function describeElement(element) {
			if (element.id) return `#${element.id}`;
			if (element.getAttribute("data-contract-slot")) {
				return `[data-contract-slot="${element.getAttribute("data-contract-slot")}"]`;
			}
			if (typeof element.className === "string" && element.className.trim()) {
				return `.${element.className.trim().split(/\s+/).slice(0, 3).join(".")}`;
			}
			return element.tagName.toLowerCase();
		}
	});

	return result.overlaps.map((overlap) =>
		toIssue(
			"fixed-sticky-overlap",
			overlap.overlapHeight >= 20 ? "P0" : "P1",
			`${viewportLabel}: fixed/sticky element overlaps content`,
			overlap,
		),
	);
}

function renderReport({ prototypePath, viewports, captures, summary }) {
	const lines = [
		`# Ditto Design Cycle Gates: ${basename(prototypePath)}`,
		"",
		`- Prototype: \`${prototypePath}\``,
		`- Status: ${summary.status.toUpperCase()}`,
		`- Viewports: ${viewports.map((viewport) => `${viewport.label}=${viewport.width}x${viewport.height}`).join(", ")}`,
		"",
		"## Screenshots",
		"",
	];

	for (const capture of captures) {
		lines.push(`- ${capture.viewport.label}: ${capture.screenshotPath}`);
	}

	lines.push("", "## Blocking Issues", "");
	if (summary.blocking.length === 0) {
		lines.push("None.");
	} else {
		for (const issue of summary.blocking) {
			lines.push(formatIssue(issue));
		}
	}

	lines.push("", "## Non-Blocking Issues", "");
	if (summary.nonBlocking.length === 0) {
		lines.push("None.");
	} else {
		for (const issue of summary.nonBlocking) {
			lines.push(formatIssue(issue));
		}
	}

	return `${lines.join("\n")}\n`;
}

function formatIssue(issue) {
	const details = issue.details ? ` ${JSON.stringify(issue.details)}` : "";
	return `- [${issue.severity}] ${issue.gate}: ${issue.message}${details}`;
}

function safeName(value) {
	return value.replace(/[^a-z0-9_.-]/gi, "-");
}

function toUrlPath(path) {
	return path.split(sep).map(encodeURIComponent).join("/");
}

main().catch((error) => {
	console.error(error instanceof Error ? error.message : error);
	process.exit(1);
});
