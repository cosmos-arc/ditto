export const DEFAULT_VIEWPORTS = [
	{ label: "VP-STANDARD", width: 1536, height: 1080 },
	{ label: "VP-COMPACT", width: 1366, height: 768 },
];

const BLOCKING_SEVERITIES = new Set(["P0", "P1"]);

export function parseArgs(argv) {
	const options = {
		strict: false,
		viewports: [],
	};

	for (let index = 0; index < argv.length; index += 1) {
		const arg = argv[index];

		if (arg === "--help" || arg === "-h") {
			return { help: true };
		}
		if (arg === "--strict") {
			options.strict = true;
			continue;
		}

		const next = argv[index + 1];
		if (!next) {
			throw new Error(`Missing value for ${arg}`);
		}

		if (arg === "--prototype") {
			options.prototype = next;
		} else if (arg === "--viewport") {
			options.viewports.push(parseViewport(next));
		} else if (arg === "--out-dir") {
			options.outDir = next;
		} else {
			throw new Error(`Unknown option: ${arg}`);
		}
		index += 1;
	}

	if (!options.prototype) {
		throw new Error("Missing required --prototype");
	}
	if (options.viewports.length === 0) {
		options.viewports = DEFAULT_VIEWPORTS;
	}

	return options;
}

export function parseViewport(value) {
	const match = value.match(/^([A-Z0-9_-]+)=(\d+)x(\d+)$/i);
	if (!match) {
		throw new Error(`Invalid --viewport "${value}". Expected LABEL=WIDTHxHEIGHT`);
	}

	const viewport = {
		label: match[1],
		width: Number.parseInt(match[2], 10),
		height: Number.parseInt(match[3], 10),
	};
	if (viewport.width <= 0 || viewport.height <= 0) {
		throw new Error("--viewport dimensions must be greater than zero");
	}

	return viewport;
}

export function toIssue(gate, severity, message, details = undefined) {
	return { gate, severity, message, details };
}

export function buildGateSummary(issues, options = {}) {
	const blocking = [];
	const nonBlocking = [];

	for (const issue of issues) {
		if (isBlocking(issue, options)) {
			blocking.push(issue);
		} else {
			nonBlocking.push(issue);
		}
	}

	return {
		status: blocking.length > 0 ? "fail" : "pass",
		blocking,
		nonBlocking,
		issues,
	};
}

function isBlocking(issue, options) {
	if (options.strict && issue.severity === "P2") {
		return true;
	}
	return BLOCKING_SEVERITIES.has(issue.severity);
}
