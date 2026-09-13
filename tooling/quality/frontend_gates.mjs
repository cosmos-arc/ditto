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
const SEND_BEACON = /\bnavigator\.sendBeacon\b/u;
// Biome's noRestrictedGlobals only sees bare identifier references, so qualified
// and computed access (window.fetch, globalThis["WebSocket"], and constant-folded
// forms such as globalThis["fet" + "ch"]) is caught here: any computed access on
// a network-capable receiver whose bracket expression contains a string literal.
const QUALIFIED_NETWORK_ACCESS = /\b(?:window|globalThis|self)(?:\.(?:fetch|EventSource|XMLHttpRequest|WebSocket)\b|\[\s*[^\]]*["'][^\]]*\])/u;
const NETWORK_CAPABILITY_ZONE = /^src\/(?:api|mocks|test|tests)\//u;

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
		if (SEND_BEACON.test(text) && !relativeWebPath.startsWith("src/api/")) {
			errors.push(`${location}: sendBeacon access is restricted to src/api`);
		}
		if (
			QUALIFIED_NETWORK_ACCESS.test(text) &&
			!NETWORK_CAPABILITY_ZONE.test(relativeWebPath) &&
			!TEST_MODULE.test(file)
		) {
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
