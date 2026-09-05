#!/usr/bin/env bun

import { gzipSync } from "node:zlib";
import { existsSync, readFileSync, readdirSync, statSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const WEB_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const DIST_ROOT = path.join(WEB_ROOT, "dist");
const MANIFEST_PATH = path.join(DIST_ROOT, ".vite/manifest.json");
const KIB = 1024;

const BUDGETS = Object.freeze({
	javascriptGzip: 300 * KIB,
	cssGzip: 120 * KIB,
	maxChunkRaw: 500 * KIB,
	coreFontsRaw: 300 * KIB,
});

function walk(directory) {
	return readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
		const absolutePath = path.join(directory, entry.name);
		return entry.isDirectory() ? walk(absolutePath) : [absolutePath];
	});
}

function formatKib(bytes) {
	return `${(bytes / KIB).toFixed(2)} KiB`;
}

if (!existsSync(DIST_ROOT)) {
	throw new Error(`Production build output is missing: ${DIST_ROOT}`);
}
if (!existsSync(MANIFEST_PATH)) {
	throw new Error(`Vite production manifest is missing: ${MANIFEST_PATH}`);
}

const files = walk(DIST_ROOT).map((absolutePath) => ({
	absolutePath,
	relativePath: path.relative(DIST_ROOT, absolutePath),
	size: statSync(absolutePath).size,
}));
const javascript = files.filter(({ relativePath }) => relativePath.endsWith(".js"));
const css = files.filter(({ relativePath }) => relativePath.endsWith(".css"));
const fonts = files.filter(({ relativePath }) => /\.(?:woff2?|ttf|otf)$/u.test(relativePath));
const chunks = [...javascript, ...css];
const filesByPath = new Map(files.map((file) => [file.relativePath, file]));

const manifest = JSON.parse(readFileSync(MANIFEST_PATH, "utf8"));
if (typeof manifest !== "object" || manifest === null || Array.isArray(manifest)) {
	throw new Error("Vite production manifest must be an object");
}
const entries = Object.entries(manifest);
const entry = entries.find(([, value]) => value?.isEntry === true && value.src === "index.html");
if (!entry) throw new Error("Vite production manifest must contain the index.html entry");

const initialJavascriptPaths = new Set();
const initialCssPaths = new Set();
const visitedManifestKeys = new Set();
function visitStaticImports(key) {
	if (visitedManifestKeys.has(key)) return;
	visitedManifestKeys.add(key);
	const record = manifest[key];
	if (typeof record !== "object" || record === null || Array.isArray(record)) {
		throw new Error(`Invalid Vite manifest record: ${key}`);
	}
	if (typeof record.file === "string" && record.file.endsWith(".js")) initialJavascriptPaths.add(record.file);
	for (const cssPath of record.css ?? []) initialCssPaths.add(cssPath);
	for (const importedKey of record.imports ?? []) visitStaticImports(importedKey);
}
visitStaticImports(entry[0]);

function selectedFiles(paths, kind) {
	return [...paths].map((relativePath) => {
		const file = filesByPath.get(relativePath);
		if (!file) throw new Error(`Vite manifest references a missing ${kind} asset: ${relativePath}`);
		return file;
	});
}

const initialJavascript = selectedFiles(initialJavascriptPaths, "JavaScript");
const initialCss = selectedFiles(initialCssPaths, "CSS");
const dynamicEntries = entries.filter(([, value]) => value?.isDynamicEntry === true);

const initialJavascriptGzip = initialJavascript.reduce(
	(total, file) => total + gzipSync(readFileSync(file.absolutePath)).byteLength,
	0,
);
const initialCssGzip = initialCss.reduce(
	(total, file) => total + gzipSync(readFileSync(file.absolutePath)).byteLength,
	0,
);
const coreFontsRaw = fonts.reduce((total, file) => total + file.size, 0);
const largestChunk = chunks.reduce(
	(current, file) => (file.size > current.size ? file : current),
	{ relativePath: "<none>", size: 0 },
);

const measurements = [
	{ name: "initial JavaScript gzip", actual: initialJavascriptGzip, limit: BUDGETS.javascriptGzip },
	{ name: "initial CSS gzip", actual: initialCssGzip, limit: BUDGETS.cssGzip },
	{ name: `largest raw chunk (${largestChunk.relativePath})`, actual: largestChunk.size, limit: BUDGETS.maxChunkRaw },
	{ name: "core font assets raw", actual: coreFontsRaw, limit: BUDGETS.coreFontsRaw },
];

console.log("Ditto Web production asset budget");
console.log(
	`Initial JavaScript chunks: ${initialJavascript.length}; initial CSS chunks: ${initialCss.length}; dynamic entries: ${dynamicEntries.length}; font assets: ${fonts.length}`,
);
for (const measurement of measurements) {
	const status = measurement.actual <= measurement.limit ? "PASS" : "FAIL";
	console.log(
		`${status} ${measurement.name}: ${formatKib(measurement.actual)} / ${formatKib(measurement.limit)}`,
	);
}

const failures = measurements.filter(({ actual, limit }) => actual > limit);
if (dynamicEntries.length === 0) {
	console.log("FAIL route lazy-loading: Vite manifest contains no dynamic entries");
	process.exitCode = 1;
} else {
	console.log(`PASS route lazy-loading: ${dynamicEntries.length} dynamic entries`);
}
if (failures.length > 0) {
	process.exitCode = 1;
}
