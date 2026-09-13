#!/usr/bin/env bun

import { spawnSync } from "node:child_process";
import path from "node:path";

const WEB_ROOT = path.resolve(import.meta.dir, "..");
const REPOSITORY_ROOT = path.resolve(WEB_ROOT, "..", "..");
const dependencyCruiser = path.join(WEB_ROOT, "node_modules/dependency-cruiser/bin/dependency-cruise.mjs");
const typescriptLoader = path.join(WEB_ROOT, "scripts/dependency-cruiser-typescript-loader.mjs");

const cruise = spawnSync(
	"node",
	[
		"--import",
		path.join(REPOSITORY_ROOT, "tooling/dev/node-runtime.mjs"),
		dependencyCruiser,
		"--config",
		"dependency-cruiser.config.mjs",
		"--output-type",
		"json",
		"src",
	],
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

const errors = [];
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
		if ((cruiseResult.summary?.totalCruised ?? 0) === 0) {
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
	}
}

if (errors.length > 0) {
	process.stderr.write(`${errors.join("\n")}\n`);
	process.exit(1);
}
process.stdout.write("Dependency cruise passed.\n");
