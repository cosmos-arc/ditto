#!/usr/bin/env bun

import { readdir, readFile } from "node:fs/promises";
import { join, relative, resolve } from "node:path";

const ROOT = resolve(import.meta.dirname, "..");
const ROUTES_DIR = resolve(ROOT, "src/routes");

const IA_ROUTES = [
	"/",
	"/markets",
	"/markets/a-shares",
	"/markets/screener",
	"/markets/watchlist",
	"/markets/intelligence",
	"/markets/calendar",
	"/instruments/$id",
	"/research",
	"/research/factors",
	"/research/factors/$id",
	"/research/strategies",
	"/research/strategies/$id",
	"/research/strategies/$id/studio",
	"/research/backtest",
	"/research/backtest/$id",
	"/research/experiments",
	"/research/experiments/new",
	"/research/experiments/$id",
	"/research/node-descriptors",
	"/research/regime",
	"/research/reviews",
	"/research/reviews/$id",
	"/research/universes",
	"/trading",
	"/trading/signals",
	"/trading/orders",
	"/trading/portfolio",
	"/trading/risk",
	"/platform",
	"/platform/agents",
	"/platform/data-products",
	"/platform/settings",
];

const DEV_ONLY_ROUTES = ["/showcase"];
const LAYOUT_ONLY_ROUTES = ["/instruments"];

const ROUTE_CALL_PATTERN = /createFileRoute\(\s*["'`]([^"'`]+)["'`]\s*\)/g;

function normalizeRoute(route) {
	const normalized = route.replace(/\/+$/, "");
	return normalized === "" ? "/" : normalized;
}

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

const actualEntries = await readActualRoutes();
const actualRouteGroups = groupByRoute(actualEntries);
const actualRoutes = [...actualRouteGroups.keys()].sort();
const expectedRoutes = new Set(IA_ROUTES);
const devOnlyRoutes = new Set(DEV_ONLY_ROUTES);
const layoutOnlyRoutes = new Set(LAYOUT_ONLY_ROUTES);

const missingRoutes = IA_ROUTES.filter((route) => !actualRouteGroups.has(route));
const unexpectedRoutes = actualRoutes.filter(
	(route) => !expectedRoutes.has(route) && !devOnlyRoutes.has(route) && !layoutOnlyRoutes.has(route),
);
const failures = [
	...formatRouteList("Missing IA routes:", missingRoutes),
	...formatRouteList("Unexpected product routes:", unexpectedRoutes),
];

if (failures.length > 0) {
	console.error("[audit:routes] Route coverage drift detected.");
	console.error(failures.join("\n"));
	process.exit(1);
}

console.log(`[audit:routes] ${IA_ROUTES.length} IA routes covered.`);
