#!/usr/bin/env bun

import { readdir, readFile } from "node:fs/promises";
import { spawnSync } from "node:child_process";
import path from "node:path";

const REPOSITORY_ROOT = path.resolve(import.meta.dir, "../..");
const WEB_ROOT = path.join(REPOSITORY_ROOT, "apps/web");
const SOURCE_EXTENSIONS = new Set([".js", ".jsx", ".ts", ".tsx"]);

async function sourceFiles(directory) {
	const files = [];
	for (const entry of await readdir(directory, { withFileTypes: true })) {
		const absolute = path.join(directory, entry.name);
		if (entry.isDirectory()) files.push(...(await sourceFiles(absolute)));
		else if (entry.isFile() && SOURCE_EXTENSIONS.has(path.extname(entry.name))) files.push(absolute);
	}
	return files;
}

const errors = [];
for (const relativeDirectory of ["src/components/ui", "src/lib"]) {
	for (const file of await sourceFiles(path.join(WEB_ROOT, relativeDirectory))) {
		const text = await readFile(file, "utf8");
		if (/from\s+["']@\/features\//u.test(text) || /from\s+["'](?:\.\.\/)+features\//u.test(text)) {
			errors.push(`${path.relative(REPOSITORY_ROOT, file)}: low-level code must not import feature internals`);
		}
	}
}

for (const file of await sourceFiles(path.join(WEB_ROOT, "src"))) {
	const text = await readFile(file, "utf8");
	const relativeWebPath = path.relative(WEB_ROOT, file).split(path.sep).join("/");
	const mayImportGeneratedSchema =
		relativeWebPath.startsWith("src/api/") || /^src\/features\/[^/]+\/api(?:\/|\.ts$)/u.test(relativeWebPath);
	if (!mayImportGeneratedSchema && /(?:from\s+|import\s*)["'][^"']*api\/generated\/schema["']/u.test(text)) {
		errors.push(
			`${path.relative(REPOSITORY_ROOT, file)}: generated schema imports are restricted to src/api and feature API adapters`,
		);
	}
	if (/from\s+["']@\/lib\/api-client["']/u.test(text)) {
		errors.push(`${path.relative(REPOSITORY_ROOT, file)}: arbitrary legacy API client imports are forbidden`);
	}
	if (/apiClient\.(?:get|getPayload|post|put|patch|delete)\s*</u.test(text)) {
		errors.push(`${path.relative(REPOSITORY_ROOT, file)}: callers may not select API response types`);
	}
	if (/\bVITE_API_BASE_URL\b/u.test(text)) {
		errors.push(`${path.relative(REPOSITORY_ROOT, file)}: production API routing must come from runtime config`);
	}
	const mayUseTypedClient =
		relativeWebPath.startsWith("src/api/") || /^src\/features\/[^/]+\/api(?:\/|\.ts$)/u.test(relativeWebPath);
	if (!mayUseTypedClient && /\bapiClient\.(?:get|getPayload|post|put|patch|delete)\s*\(/u.test(text)) {
		errors.push(`${path.relative(REPOSITORY_ROOT, file)}: typed transport calls belong in feature API adapters`);
	}
	if (/\.(?:test|spec)\.(?:js|jsx|ts|tsx)$/u.test(file)) continue;
	if (/@ts-ignore|@ts-expect-error/u.test(text))
		errors.push(`${path.relative(REPOSITORY_ROOT, file)}: TypeScript suppression is forbidden`);
	if (!file.includes(`${path.sep}styles${path.sep}design-tokens${path.sep}`) && /#[0-9a-fA-F]{3,8}\b/u.test(text)) {
		errors.push(`${path.relative(REPOSITORY_ROOT, file)}: hard-coded color must be a design token`);
	}
}

const dependencyCruiser = path.join(WEB_ROOT, "node_modules/.bin/depcruise");
const typescriptLoader = path.join(WEB_ROOT, "scripts/dependency-cruiser-typescript-loader.mjs");
const cruise = spawnSync(
	dependencyCruiser,
	["--config", "dependency-cruiser.config.mjs", "--output-type", "json", "src"],
	{
		cwd: WEB_ROOT,
		encoding: "utf8",
		env: {
			...process.env,
			NODE_OPTIONS: [process.env.NODE_OPTIONS, `--import=${typescriptLoader}`].filter(Boolean).join(" "),
			NODE_PATH: [path.join(WEB_ROOT, "node_modules"), process.env.NODE_PATH].filter(Boolean).join(path.delimiter),
		},
		maxBuffer: 16 * 1024 * 1024,
	},
);
if (cruise.error) {
	errors.push(`dependency-cruiser failed to start: ${cruise.error.message}`);
} else {
	let cruiseResult;
	try {
		cruiseResult = JSON.parse(cruise.stdout);
	} catch {
		const output = `${cruise.stdout ?? ""}${cruise.stderr ?? ""}`.trim();
		errors.push(output || `dependency-cruiser exited with status ${cruise.status ?? "unknown"}`);
	}

	if (cruiseResult) {
		const totalCruised = cruiseResult.summary?.totalCruised ?? 0;
		if (totalCruised === 0) {
			errors.push("dependency-cruiser did not analyze any source modules");
		}
		const typescript = cruiseResult.summary?.environment?.transpilersFound?.find(
			(transpiler) => transpiler.name === "typescript",
		);
		if (!typescript?.available) {
			errors.push("dependency-cruiser did not load the TypeScript parser");
		}

		for (const violation of cruiseResult.summary?.violations ?? []) {
			if (violation.rule?.severity !== "error") continue;
			errors.push(`${violation.rule.name}: ${violation.from} -> ${violation.to}`);
		}

		const featureGraph = new Map();
		const testModule = /\.(?:test|spec)\.(?:js|jsx|ts|tsx)$/u;
		const featureName = (modulePath) => /^src\/features\/([^/]+)\//u.exec(modulePath)?.[1];
		for (const module of cruiseResult.modules ?? []) {
			if (testModule.test(module.source)) continue;
			const fromFeature = featureName(module.source);
			if (!fromFeature) continue;
			if (!featureGraph.has(fromFeature)) featureGraph.set(fromFeature, new Set());
			for (const dependency of module.dependencies ?? []) {
				if (testModule.test(dependency.resolved)) continue;
				const toFeature = featureName(dependency.resolved);
				if (toFeature && toFeature !== fromFeature) featureGraph.get(fromFeature).add(toFeature);
			}
		}

		let nextIndex = 0;
		const indices = new Map();
		const lowLinks = new Map();
		const stack = [];
		const onStack = new Set();
		const stronglyConnected = [];
		function visit(feature) {
			indices.set(feature, nextIndex);
			lowLinks.set(feature, nextIndex);
			nextIndex += 1;
			stack.push(feature);
			onStack.add(feature);

			for (const dependency of featureGraph.get(feature) ?? []) {
				if (!indices.has(dependency)) {
					visit(dependency);
					lowLinks.set(feature, Math.min(lowLinks.get(feature), lowLinks.get(dependency)));
				} else if (onStack.has(dependency)) {
					lowLinks.set(feature, Math.min(lowLinks.get(feature), indices.get(dependency)));
				}
			}

			if (lowLinks.get(feature) !== indices.get(feature)) return;
			const component = [];
			let member;
			do {
				member = stack.pop();
				onStack.delete(member);
				component.push(member);
			} while (member !== feature);
			if (component.length > 1) stronglyConnected.push(component.sort());
		}

		for (const feature of featureGraph.keys()) {
			if (!indices.has(feature)) visit(feature);
		}
		for (const cycle of stronglyConnected.sort((left, right) => left[0].localeCompare(right[0]))) {
			errors.push(`feature-dependency-cycle: ${cycle.join(" <-> ")}`);
		}
	}
}

if (errors.length > 0) {
	process.stderr.write(`${errors.join("\n")}\n`);
	process.exit(1);
}
process.stdout.write("Frontend architecture checks passed.\n");
