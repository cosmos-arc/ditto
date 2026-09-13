#!/usr/bin/env bun

import { readdir, readFile } from "node:fs/promises";
import path from "node:path";

import { findRawColorPrimitives, isCanonicalTokenFile } from "./frontend_color_policy.mjs";

const REPOSITORY_ROOT = path.resolve(import.meta.dir, "../..");
const WEB_ROOT = path.join(REPOSITORY_ROOT, "apps/web");
const SOURCE_EXTENSIONS = new Set([".css", ".js", ".jsx", ".ts", ".tsx"]);
const TEST_MODULE = /\.(?:test|spec)\.(?:js|jsx|ts|tsx)$/u;
const SUPPRESSION = /@ts-ignore|@ts-expect-error/u;
const VITE_BASE_URL = /\bVITE_API_BASE_URL\b/u;
const NETWORK_GLOBAL_NAMES = new Set(["fetch", "EventSource", "XMLHttpRequest", "WebSocket"]);
const SEND_BEACON = /\bnavigator\.sendBeacon\b/u;
// Biome's noRestrictedGlobals only sees bare identifier references. Qualified access
// (window.fetch, navigator.sendBeacon) and computed access are caught here. Computed
// access is folded by stripping quotes/plus/whitespace from the bracket expression and
// requiring an exact match against a network capability name, so constant concatenations
// like globalThis["fet" + "ch"] are flagged while globalThis["crypto"] is not.
const QUALIFIED_NETWORK_ACCESS = /\b(?:window|globalThis|self)\.(?:fetch|EventSource|XMLHttpRequest|WebSocket)\b/u;
const COMPUTED_NETWORK_ACCESS = /\b(?:window|globalThis|self|navigator)\[([^\]]*)\]/gu;
const NETWORK_CAPABILITY_ZONE = /^src\/(?:api|mocks|test|tests)\//u;

function foldsToNetworkGlobal(fragment) {
	const folded = fragment.replace(/["'\s+]/gu, "");
	return folded === "sendBeacon" || NETWORK_GLOBAL_NAMES.has(folded);
}

function reportsQualifiedNetworkAccess(text) {
	if (QUALIFIED_NETWORK_ACCESS.test(text)) return true;
	for (const match of text.matchAll(COMPUTED_NETWORK_ACCESS)) {
		const fragment = match[1] ?? "";
		if ((fragment.includes('"') || fragment.includes("'")) && foldsToNetworkGlobal(fragment)) return true;
	}
	return false;
}

async function sourceFiles(directory) {
	const files = [];
	for (const entry of await readdir(directory, { withFileTypes: true })) {
		const absolute = path.join(directory, entry.name);
		if (entry.isDirectory()) files.push(...(await sourceFiles(absolute)));
		else if (entry.isFile() && SOURCE_EXTENSIONS.has(path.extname(entry.name))) files.push(absolute);
	}
	return files;
}

/**
 * Regex-level policies that dependency-cruiser (import zones) and Biome
 * (restricted globals) cannot express. Returns one error line per violation.
 */
export async function runFrontendGates(webRoot = WEB_ROOT) {
	const errors = [];
	for (const file of await sourceFiles(path.join(webRoot, "src"))) {
		const text = await readFile(file, "utf8");
		const relativeWebPath = path.relative(webRoot, file).split(path.sep).join("/");
		const location = path.relative(webRoot, file);
		if (VITE_BASE_URL.test(text)) {
			errors.push(`${location}: production API routing must come from runtime config`);
		}
		const inNetworkZone = NETWORK_CAPABILITY_ZONE.test(relativeWebPath) || TEST_MODULE.test(file);
		if (SEND_BEACON.test(text) && !inNetworkZone) {
			errors.push(`${location}: sendBeacon access is restricted to src/api and test scaffolding`);
		}
		if (reportsQualifiedNetworkAccess(text) && !inNetworkZone) {
			errors.push(`${location}: qualified network global access is restricted to src/api and test scaffolding`);
		}
		if (TEST_MODULE.test(file)) continue;
		if (SUPPRESSION.test(text)) {
			errors.push(`${location}: TypeScript suppression is forbidden`);
		}
		if (isCanonicalTokenFile(relativeWebPath)) continue;
		for (const finding of findRawColorPrimitives(text, relativeWebPath)) {
			errors.push(
				`${location}:${finding.line}: raw ${finding.syntax} color must be defined in src/styles/design-tokens`,
			);
		}
	}
	return errors;
}

if (import.meta.main) {
	const errors = await runFrontendGates();
	if (errors.length > 0) {
		process.stderr.write(`${errors.join("\n")}\n`);
		process.exit(1);
	}
	process.stdout.write("Frontend regex gates passed.\n");
}
