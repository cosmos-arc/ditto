import { existsSync, readFileSync } from "node:fs";
import { join, resolve } from "node:path";
import { spawnSync } from "node:child_process";

const prototypesDir = "prototype";
const archivedPrototypeIds = new Set(["ai-overview", "ai-copilot"]);
const verifier = resolve(
	import.meta.dirname,
	"../../..",
	"apps/web/scripts/prototype/verify-gates.mjs",
);
export const gateViewports = [
	{ name: "VP-STANDARD", width: 1536, height: 1080 },
	{ name: "VP-COMPACT", width: 1366, height: 768 },
	{ name: "VP-NARROW", width: 1200, height: 800 },
] as const;

type ManifestPage = {
	id: string;
	file: string;
	status?: string;
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
		page.status !== "archived-specimen" &&
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

export function defaultViewportArgs(): string[] {
	return gateViewports.flatMap((viewport) => [
		"--viewport",
		`${viewport.name}=${viewport.width}x${viewport.height}`,
	]);
}

function hasExplicitViewport(args: readonly string[]): boolean {
	return args.some((arg) => arg === "--viewport" || arg.startsWith("--viewport="));
}

function hasPrototypeArg(args: readonly string[]): boolean {
	return args.some((arg) => arg === "--prototype" || arg.startsWith("--prototype="));
}

function normalizeGateArgs(args: readonly string[]): string[] {
	return args.flatMap((arg) => {
		for (const option of ["--prototype", "--viewport", "--out-dir"] as const) {
			const prefix = `${option}=`;
			if (arg.startsWith(prefix)) return [option, arg.slice(prefix.length)];
		}

		return [arg];
	});
}

export function buildPassthroughGateArgs(args: readonly string[]): string[] {
	const normalizedArgs = normalizeGateArgs(args);
	if (!hasPrototypeArg(args) || hasExplicitViewport(args)) return normalizedArgs;

	return [...normalizedArgs, ...defaultViewportArgs()];
}

export function buildDefaultPrototypeGateArgs(prototypePath: string, outDir: string): string[] {
	return ["--prototype", prototypePath, ...defaultViewportArgs(), "--out-dir", outDir];
}

function printWrapperHelp(): void {
	console.log(`Usage:
  bun run prototype:gates
  bun run prototype:gates -- --prototype <path> [--viewport NAME=WIDTHxHEIGHT]
  bun run prototype:gates -- --prototype=<path> [--viewport=NAME=WIDTHxHEIGHT]

Wrapper default viewports:
  VP-STANDARD=1536x1080
  VP-COMPACT=1366x768
  VP-NARROW=1200x800

When --prototype is provided without --viewport, the wrapper injects the same default viewports.
When any --viewport is provided, the wrapper preserves the explicit viewport list.`);
}

function main(args: string[]): number {
	if (args.includes("--help") || args.includes("-h")) {
		printWrapperHelp();
		return 0;
	}

	if (hasPrototypeArg(args)) {
		return runVerifier(buildPassthroughGateArgs(args));
	}

	const failures: string[] = [];

	for (const page of readManifest().pages.filter(isActiveRoutePrototype)) {
		const prototypePath = join(prototypesDir, page.file);
		const outDir = join("test-results/ditto-design-cycle-gates", page.id);
		console.log(`\n=== prototype:gates ${page.id} ===`);
		const status = runVerifier(buildDefaultPrototypeGateArgs(prototypePath, outDir));
		if (status !== 0) failures.push(page.id);
	}

	if (failures.length > 0) {
		console.error(`\nprototype:gates failed for: ${failures.join(", ")}`);
		return 1;
	}

	console.log("\nprototype:gates passed for every active route prototype.");
	return 0;
}

if (import.meta.main) {
	process.exit(main(process.argv.slice(2)));
}
