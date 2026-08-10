export const DEFAULT_VIEWPORT = { width: 1536, height: 900 };
export const DEFAULT_OUT_DIR = "docs/review/visual-audit";
export const NAVIGATION_WAIT_UNTIL = "load";

export function isSuccessfulResponseStatus(status) {
	return (status >= 200 && status < 300) || status === 304;
}

export function shouldIgnoreRequestFailure(resourceType, errorText) {
	return resourceType === "script" && errorText === "net::ERR_ABORTED";
}

export const USAGE = `Usage:
  bun .agents/skills/ditto-app-dev/scripts/visual-audit.mjs --route <route> --react-base <url> --prototype-base <url>
  bun .agents/skills/ditto-app-dev/scripts/visual-audit.mjs --all --react-base <url> --prototype-base <url>

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

	const page = pages.find((item) => item.route === options.route || item.resolvedRoute === options.route);
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

/**
 * Properties to skip when reporting style diffs.
 * These are structural/layout props already covered by the Rect Deltas table,
 * or props that are expected to differ between prototype HTML and React (e.g. fontFamily).
 */
const SKIP_DIFF_PROPS = new Set([
	"display",
	"position",
	"width",
	"height",
	"padding",
	"gap",
	"gridTemplateRows",
	"gridTemplateColumns",
	"lineHeight",
	"fontFamily",
]);

export function renderReport(metrics) {
	const names = [...new Set([...Object.keys(metrics.prototype), ...Object.keys(metrics.react)])];
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
		"| Target | Prototype | React | \u0394x | \u0394y | \u0394w | \u0394h |",
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

	// Style diffs between prototype and React
	const styleDiffs = buildStyleDiffs(names, metrics.prototype, metrics.react);
	if (styleDiffs.length > 0) {
		lines.push("", "## Style Diffs", "");
		lines.push("| Target | Property | Prototype | React |");
		lines.push("| --- | --- | --- | --- |");
		for (const diff of styleDiffs) {
			lines.push(`| ${diff.target} | \`${diff.prop}\` | ${diff.prototype} | ${diff.react} |`);
		}
	}

	// Pseudo-element diffs
	const pseudoDiffs = buildPseudoDiffs(names, metrics.prototype, metrics.react);
	if (pseudoDiffs.length > 0) {
		lines.push("", "## Pseudo-element Style Diffs", "");
		lines.push("| Target | Pseudo | Property | Prototype | React |");
		lines.push("| --- | --- | --- | --- | --- |");
		for (const diff of pseudoDiffs) {
			lines.push(`| ${diff.target} | ${diff.pseudo} | \`${diff.prop}\` | ${diff.prototype} | ${diff.react} |`);
		}
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

function buildStyleDiffs(names, prototypeMetrics, reactMetrics) {
	const diffs = [];

	for (const name of names) {
		const proto = prototypeMetrics[name];
		const react = reactMetrics[name];
		if (!proto?.styles || !react?.styles) continue;

		for (const [prop, protoValue] of Object.entries(proto.styles)) {
			if (SKIP_DIFF_PROPS.has(prop)) continue;
			const reactValue = react.styles[prop];
			if (protoValue !== reactValue) {
				diffs.push({
					target: name,
					prop,
					prototype: truncate(protoValue),
					react: truncate(reactValue),
				});
			}
		}
	}

	return diffs;
}

function buildPseudoDiffs(names, prototypeMetrics, reactMetrics) {
	const diffs = [];

	for (const name of names) {
		const proto = prototypeMetrics[name];
		const react = reactMetrics[name];
		if (!proto?.pseudoStyles || !react?.pseudoStyles) continue;

		for (const pseudo of ["::before", "::after"]) {
			const protoPseudo = proto.pseudoStyles[pseudo];
			const reactPseudo = react.pseudoStyles[pseudo];
			if (!protoPseudo && !reactPseudo) continue;

			// If only one side has the pseudo-element, note the mismatch
			if (!protoPseudo || !reactPseudo) {
				diffs.push({
					target: name,
					pseudo,
					prop: "(existence)",
					prototype: protoPseudo ? "present" : "absent",
					react: reactPseudo ? "present" : "absent",
				});
				continue;
			}

			for (const [prop, protoValue] of Object.entries(protoPseudo)) {
				const reactValue = reactPseudo[prop];
				if (protoValue !== reactValue) {
					diffs.push({
						target: name,
						pseudo,
						prop,
						prototype: truncate(protoValue),
						react: truncate(reactValue),
					});
				}
			}
		}
	}

	return diffs;
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

function truncate(value) {
	if (!value) return value;
	const str = String(value);
	return str.length > 80 ? `${str.slice(0, 77)}...` : str;
}
