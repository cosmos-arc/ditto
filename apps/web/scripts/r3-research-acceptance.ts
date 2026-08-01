import { createHash } from "node:crypto";
import { spawnSync } from "node:child_process";
import { mkdir, writeFile } from "node:fs/promises";
import { join, relative, resolve } from "node:path";

type AcceptanceOptions = {
	readonly fixture: true;
	readonly outDir: string;
};

type CommandCapture = {
	readonly returncode: number;
	readonly stdout: string;
	readonly stderr: string;
};

type AcceptanceDependencies = {
	readonly checkedAt?: Date;
	readonly sourceCommit?: string;
	readonly runCommand?: (command: readonly string[]) => CommandCapture;
};

type CommandEvidence = CommandCapture & {
	readonly name: "ui-contract-suite";
	readonly command: readonly string[];
	readonly passed: boolean;
	readonly artifact_hashes: {
		readonly command_transcript: string;
	};
};

type AcceptanceReport = {
	readonly schema: "ditto.r3-research-frontend-acceptance";
	readonly version: 1;
	readonly generated_at: string;
	readonly source_commit: string;
	readonly mode: "deterministic_fixture";
	readonly passed: boolean;
	readonly release_status: "RELEASE_ACCEPTANCE_BLOCKED";
	readonly r2_live_gate: "NOT_EVALUATED";
	readonly scope: typeof ACCEPTANCE_SCOPE;
	readonly command: CommandEvidence;
};

const PROJECT_ROOT = resolve(import.meta.dirname, "..");
const DEFAULT_OUT_DIR = "docs/review/r3-research-acceptance/deterministic";
const OUTPUT_LIMIT = 12_000;

export const ACCEPTANCE_SCOPE = {
	mode: "deterministic_fixture",
	runtime: "jsdom + isolated MSW HTTP fixtures",
	proves: ["studio_experiment_review_flow", "refresh_recovery", "hard_gate_blocked_ui", "typed_live_boundary"],
	doesNotProve: [
		"provider_entitlement",
		"certified_live_data",
		"live_96_month_history",
		"real_browser_acceptance",
		"production_recovery",
	],
} as const;

const FIXTURE_TESTS = [
	"src/features/research/components/experiment-create-page.test.tsx",
	"src/features/research/components/experiment-detail-page.test.tsx",
	"src/features/research/components/experiment-run-recovery.test.tsx",
	"src/features/research/components/review-detail-page.test.tsx",
	"src/features/research/components/review-queue-page.test.tsx",
	"src/features/research/live-boundary.test.tsx",
] as const;

function invariant(condition: unknown, message: string): asserts condition {
	if (!condition) throw new Error(message);
}

export function parseAcceptanceArgs(args: readonly string[]): AcceptanceOptions {
	let fixture = false;
	let outDir = DEFAULT_OUT_DIR;

	for (let index = 0; index < args.length; index += 1) {
		const argument = args[index];
		if (argument === "--fixture") {
			fixture = true;
			continue;
		}
		if (argument === "--out-dir") {
			const value = args[index + 1];
			invariant(value, "Missing value for --out-dir");
			outDir = value;
			index += 1;
			continue;
		}
		throw new Error(`Unknown option: ${argument}`);
	}

	invariant(fixture, "--fixture is required");
	return { fixture: true, outDir };
}

export function buildFixtureCommand(): readonly string[] {
	return ["bunx", "vitest", "run", ...FIXTURE_TESTS];
}

function runCommand(command: readonly string[]): CommandCapture {
	const result = spawnSync(command[0], command.slice(1), {
		cwd: PROJECT_ROOT,
		encoding: "utf8",
	});
	return {
		returncode: result.status ?? 1,
		stdout: (result.stdout ?? "").slice(-OUTPUT_LIMIT),
		stderr: (result.stderr ?? "").slice(-OUTPUT_LIMIT),
	};
}

function sourceCommit(): string {
	const result = spawnSync("git", ["rev-parse", "HEAD"], {
		cwd: PROJECT_ROOT,
		encoding: "utf8",
	});
	invariant(result.status === 0, "Unable to resolve frontend source commit");
	return result.stdout.trim();
}

function sha256(payload: string): string {
	return createHash("sha256").update(payload).digest("hex");
}

function canonicalJson(value: unknown): string {
	return `${JSON.stringify(value, null, 2)}\n`;
}

export async function runFixtureAcceptance(
	options: AcceptanceOptions,
	dependencies: AcceptanceDependencies = {},
): Promise<AcceptanceReport> {
	const command = buildFixtureCommand();
	const capture = (dependencies.runCommand ?? runCommand)(command);
	const transcript = canonicalJson({
		command,
		returncode: capture.returncode,
		stderr: capture.stderr.slice(-OUTPUT_LIMIT),
		stdout: capture.stdout.slice(-OUTPUT_LIMIT),
	});
	const commandEvidence: CommandEvidence = {
		name: "ui-contract-suite",
		command,
		returncode: capture.returncode,
		stdout: capture.stdout.slice(-OUTPUT_LIMIT),
		stderr: capture.stderr.slice(-OUTPUT_LIMIT),
		passed: capture.returncode === 0,
		artifact_hashes: { command_transcript: sha256(transcript) },
	};
	const checkedAt = dependencies.checkedAt ?? new Date();
	const report: AcceptanceReport = {
		schema: "ditto.r3-research-frontend-acceptance",
		version: 1,
		generated_at: checkedAt.toISOString().replace(/\.\d{3}Z$/u, "Z"),
		source_commit: dependencies.sourceCommit ?? sourceCommit(),
		mode: "deterministic_fixture",
		passed: commandEvidence.passed,
		release_status: "RELEASE_ACCEPTANCE_BLOCKED",
		r2_live_gate: "NOT_EVALUATED",
		scope: ACCEPTANCE_SCOPE,
		command: commandEvidence,
	};

	const outDir = resolve(PROJECT_ROOT, options.outDir);
	const reportPath = join(outDir, "report.json");
	await mkdir(outDir, { recursive: true });
	await writeFile(reportPath, canonicalJson(report), "utf8");
	await writeFile(
		join(outDir, "manifest.json"),
		canonicalJson({
			schema: "ditto.r3-research-frontend-evidence-manifest",
			version: 1,
			entries: [
				{
					relative_path: relative(PROJECT_ROOT, reportPath),
					sha256: sha256(canonicalJson(report)),
					mode: report.mode,
					generated_at: report.generated_at,
					source_commit: report.source_commit,
					command: command.join(" "),
				},
			],
		}),
		"utf8",
	);
	return report;
}

async function main(args: readonly string[]): Promise<void> {
	const options = parseAcceptanceArgs(args);
	const report = await runFixtureAcceptance(options);
	console.log(canonicalJson(report));
	if (!report.passed) process.exitCode = 1;
}

if (import.meta.main) {
	main(process.argv.slice(2)).catch((error: unknown) => {
		console.error(error instanceof Error ? error.message : error);
		process.exit(1);
	});
}
