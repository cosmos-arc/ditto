export const DEFAULT_VIEWPORT = { width: 1536, height: 900 };
export const DEFAULT_OUT_DIR = "docs/review/visual-audit";

export const USAGE = `Usage:
  bun scripts/visual-audit.mjs --route <route> --react-base <url> --prototype-base <url>
  bun scripts/visual-audit.mjs --all --react-base <url> --prototype-base <url>

Options:
  --route <route>          Audit one configured route.
  --all                    Audit every configured route.
  --react-base <url>       Base URL for the React app.
  --prototype-base <url>   Base URL for prototype HTML files.
  --viewport <WxH>         Viewport size. Default: 1536x900.
  --out-dir <path>         Output directory. Default: docs/review/visual-audit.
  --help                   Show this help.
`;

export function parseArgs(argv) {
	const options = {
		all: false,
		outDir: DEFAULT_OUT_DIR,
		viewport: DEFAULT_VIEWPORT,
	};

	for (let index = 0; index < argv.length; index += 1) {
		const arg = argv[index];
		if (arg === "--help" || arg === "-h") {
			return { help: true };
		}
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

export function parseViewport(value) {
	const match = value.match(/^(\d+)x(\d+)$/);
	if (!match) {
		throw new Error(`Invalid --viewport "${value}". Expected WIDTHxHEIGHT.`);
	}

	const viewport = {
		width: Number.parseInt(match[1], 10),
		height: Number.parseInt(match[2], 10),
	};
	if (viewport.width <= 0 || viewport.height <= 0) {
		throw new Error("--viewport dimensions must be greater than zero");
	}

	return viewport;
}

export function resolvePages(options, pages) {
	if (options.all) {
		return pages;
	}

	const page = pages.find(
		(item) => item.route === options.route || item.resolvedRoute === options.route,
	);
	if (!page) {
		const knownRoutes = pages.map((item) => item.route).join(", ");
		throw new Error(`Unknown route "${options.route}". Known routes: ${knownRoutes}`);
	}
	return [page];
}

export function validateTargetKeyParity(config) {
	const prototypeKeys = Object.keys(config.prototypeTargets);
	const reactKeys = Object.keys(config.reactTargets);
	const warnings = [];

	for (const key of prototypeKeys) {
		if (!reactKeys.includes(key)) {
			warnings.push(`prototype target "${key}" has no matching react target`);
		}
	}
	for (const key of reactKeys) {
		if (!prototypeKeys.includes(key)) {
			warnings.push(`react target "${key}" has no matching prototype target`);
		}
	}

	return warnings;
}

export function renderReport(metrics) {
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
		...metrics.warnings.targets.map((warning) => `targets: ${warning}`),
		...metrics.warnings.prototype.map((warning) => `prototype: ${warning}`),
		...metrics.warnings.react.map((warning) => `react: ${warning}`),
	];

	lines.push("", "## Warnings", "");
	if (warnings.length === 0) {
		lines.push("No missing target selectors or page issues.");
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
