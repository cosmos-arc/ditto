import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { spawnSync } from "node:child_process";

const prototypesDir = "docs/designs/specs/prototypes";
const archivedPrototypeIds = new Set(["ai-overview", "ai-copilot"]);
const verifier = ".claude/skills/ditto-design-cycle/scripts/verify-gates.mjs";

type ManifestPage = {
	id: string;
	file: string;
};

type EditionManifest = {
	pages: ManifestPage[];
};

function readManifest(): EditionManifest {
	return JSON.parse(
		readFileSync(join(prototypesDir, ".edition-manifest.json"), "utf8"),
	) as EditionManifest;
}

function isActiveRoutePrototype(page: ManifestPage): boolean {
	return (
		page.file.startsWith("page-") &&
		page.file.endsWith(".html") &&
		!archivedPrototypeIds.has(page.id) &&
		existsSync(join(prototypesDir, page.file))
	);
}

function runVerifier(args: string[]): number {
	const result = spawnSync(process.execPath, [verifier, ...args], {
		stdio: "inherit",
		env: process.env,
	});

	if (result.error) {
		console.error(result.error.message);
		return 1;
	}

	if (result.signal) {
		console.error(`verify-gates stopped with signal ${result.signal}`);
		return 1;
	}

	return result.status ?? 1;
}

const passthroughArgs = process.argv.slice(2);

if (passthroughArgs.includes("--prototype") || passthroughArgs.includes("--help")) {
	process.exit(runVerifier(passthroughArgs));
}

const failures: string[] = [];

for (const page of readManifest().pages.filter(isActiveRoutePrototype)) {
	const prototypePath = join(prototypesDir, page.file);
	const outDir = join("test-results/ditto-design-cycle-gates", page.id);
	console.log(`\n=== prototype:gates ${page.id} ===`);
	const status = runVerifier(["--prototype", prototypePath, "--out-dir", outDir]);
	if (status !== 0) failures.push(page.id);
}

if (failures.length > 0) {
	console.error(`\nprototype:gates failed for: ${failures.join(", ")}`);
	process.exit(1);
}

console.log("\nprototype:gates passed for every active route prototype.");
