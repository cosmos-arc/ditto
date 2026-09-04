#!/usr/bin/env bun

import { readdir, readFile } from "node:fs/promises";
import { join, relative, resolve } from "node:path";
import { auditRouteCoverage, deriveExpectedProductRoutes, normalizeRoute } from "./audit-route-coverage-core.mjs";

const ROOT = resolve(import.meta.dirname, "..");
const ROUTES_DIR = resolve(ROOT, "src/routes");
const CONTRACTS_DIR = resolve(ROOT, "docs/contracts/pages");
const EDITION_MANIFEST_PATH = resolve(ROOT, "docs/designs/specs/prototypes/.edition-manifest.json");
const ALLOWED_NON_PRODUCT_ROUTES = ["/showcase", "/research/node-descriptors", "/instruments"];

const ROUTE_CALL_PATTERN = /createFileRoute\(\s*["'`]([^"'`]+)["'`]\s*\)/g;

async function collectRouteFiles(directory) {
	const entries = await readdir(directory, { withFileTypes: true });
	const files = [];

	for (const entry of entries) {
		const path = join(directory, entry.name);
		if (entry.isDirectory()) {
			files.push(...(await collectRouteFiles(path)));
			continue;
		}

		if (entry.isFile() && path.endsWith(".tsx")) {
			files.push(path);
		}
	}

	return files;
}

async function readProductRouteSources() {
	const [contractFiles, manifestSource] = await Promise.all([
		readdir(CONTRACTS_DIR),
		readFile(EDITION_MANIFEST_PATH, "utf-8"),
	]);
	const contracts = await Promise.all(
		contractFiles
			.filter((file) => file.endsWith(".contract.json"))
			.sort()
			.map(async (file) => JSON.parse(await readFile(resolve(CONTRACTS_DIR, file), "utf-8"))),
	);
	return deriveExpectedProductRoutes(contracts, JSON.parse(manifestSource));
}

async function readActualRoutes() {
	const files = await collectRouteFiles(ROUTES_DIR);
	const routes = [];

	for (const file of files) {
		const source = await readFile(file, "utf-8");

		for (const match of source.matchAll(ROUTE_CALL_PATTERN)) {
			const route = normalizeRoute(match[1]);
			routes.push({
				file: relative(ROOT, file),
				route,
			});
		}
	}

	return routes.sort((left, right) => left.route.localeCompare(right.route));
}

function groupByRoute(entries) {
	const groups = new Map();

	for (const entry of entries) {
		const group = groups.get(entry.route) ?? [];
		group.push(entry.file);
		groups.set(entry.route, group);
	}

	return groups;
}

function formatRouteList(title, routes) {
	if (routes.length === 0) {
		return [];
	}

	return [title, ...routes.map((route) => `  - ${route}`)];
}

const [actualEntries, expectedRoutes] = await Promise.all([readActualRoutes(), readProductRouteSources()]);
const actualRouteGroups = groupByRoute(actualEntries);
const actualRoutes = [...actualRouteGroups.keys()].sort();
const { missingRoutes, unexpectedRoutes } = auditRouteCoverage({
	expectedRoutes,
	actualRoutes,
	allowedNonProductRoutes: ALLOWED_NON_PRODUCT_ROUTES,
});
const failures = [
	...formatRouteList("Missing IA routes:", missingRoutes),
	...formatRouteList("Unexpected product routes:", unexpectedRoutes),
];

if (failures.length > 0) {
	console.error("[audit:routes] Route coverage drift detected.");
	console.error(failures.join("\n"));
	process.exit(1);
}

console.log(`[audit:routes] ${expectedRoutes.length} contract/manifest product routes covered.`);
