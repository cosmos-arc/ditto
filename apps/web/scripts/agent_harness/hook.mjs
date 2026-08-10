#!/usr/bin/env bun

import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { existsSync } from "node:fs";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";

const CACHE_DIRECTORY = ".cache/ditto-agent-harness";
const MAX_FEEDBACK = 6_000;
const EDITABLE_EXTENSIONS = new Set([".css", ".js", ".json", ".jsonc", ".jsx", ".mjs", ".ts", ".tsx"]);

function run(command, args, root, options = {}) {
	return spawnSync(command, args, {
		cwd: root,
		encoding: options.binary ? null : "utf8",
		maxBuffer: 20 * 1024 * 1024,
	});
}

export function gitRoot(start = process.cwd()) {
	const result = run("git", ["rev-parse", "--show-toplevel"], start);
	if (result.status !== 0) {
		throw new Error(result.stderr?.trim() || "unable to resolve repository root");
	}
	return path.resolve(result.stdout.trim());
}

function currentBranch(root) {
	return run("git", ["branch", "--show-current"], root).stdout.trim();
}

function shellSegments(command) {
	return command
		.split(/&&|\|\||;|\n/u)
		.map(
			(segment) =>
				segment.match(/(?:[^\s"']+|"[^"]*"|'[^']*')+/gu)?.map((token) => token.replace(/^(['"])(.*)\1$/u, "$2")) ?? [],
		)
		.filter((tokens) => tokens.length > 0);
}

function executableIndex(tokens, name) {
	return tokens.findIndex((token) => path.basename(token) === name);
}

function gitInvocation(tokens) {
	const index = executableIndex(tokens, "git");
	if (index < 0) {
		return null;
	}
	const args = tokens.slice(index + 1);
	let cursor = 0;
	while (cursor < args.length && args[cursor].startsWith("-")) {
		cursor += ["-C", "-c", "--git-dir", "--work-tree"].includes(args[cursor]) ? 2 : 1;
	}
	return { subcommand: args[cursor] ?? "", args: args.slice(cursor + 1) };
}

function dangerousRemoval(tokens) {
	const index = executableIndex(tokens, "rm");
	if (index < 0) {
		return false;
	}
	const flags = new Set();
	for (const option of tokens.slice(index + 1)) {
		if (option === "--") break;
		if (!option.startsWith("-")) continue;
		if (option === "--recursive") flags.add("r");
		else if (option === "--force") flags.add("f");
		else if (!option.startsWith("--")) for (const flag of option.slice(1)) flags.add(flag);
	}
	return flags.has("r") && flags.has("f");
}

export function policyViolation(command, branch) {
	const compact = command.replace(/\s+/gu, " ").trim();
	if (!compact) return null;

	for (const tokens of shellSegments(command)) {
		const invocation = gitInvocation(tokens);
		if (invocation) {
			const forced = invocation.args.some(
				(argument) => argument.startsWith("--force") || (/^-[^-]/u.test(argument) && argument.slice(1).includes("f")),
			);
			if (invocation.subcommand === "push" && forced) return "force push is blocked";
			if (invocation.subcommand === "reset" && invocation.args.includes("--hard")) return "git reset --hard is blocked";
			if (["commit", "push"].includes(invocation.subcommand) && invocation.args.includes("--no-verify")) {
				return "--no-verify is blocked; fix or report the failing gate";
			}
			if (branch === "main" && ["commit", "push"].includes(invocation.subcommand)) {
				return "commit and push are blocked on main; create a feature branch";
			}
		}
		if (dangerousRemoval(tokens)) return "recursive forced deletion is blocked";
	}

	if (
		/\b(?:npm\s+(?:ci|install|uninstall|update)|yarn\s+(?:add|remove|install)|pnpm\s+(?:add|remove|install|update))\b/u.test(
			compact,
		)
	) {
		return "non-Bun dependency mutation is blocked; use the repository Bun workflow";
	}
	return null;
}

function commandFromPayload(payload) {
	return typeof payload?.tool_input?.command === "string"
		? payload.tool_input.command
		: typeof payload?.command === "string"
			? payload.command
			: "";
}

function normalizeRepositoryPath(raw, root) {
	const absolute = path.resolve(root, raw);
	const relative = path.relative(root, absolute);
	if (relative.startsWith("..") || path.isAbsolute(relative)) return null;
	return relative.split(path.sep).join("/");
}

export function extractEditedFiles(payload, root) {
	const rawPaths = [];
	for (const container of [payload?.tool_input, payload]) {
		if (!container || typeof container !== "object") continue;
		for (const key of ["file_path", "path"]) {
			if (typeof container[key] === "string") rawPaths.push(container[key]);
		}
	}
	const patch = commandFromPayload(payload);
	for (const match of patch.matchAll(/^\*\*\* (?:(?:Add|Update) File|Move to):\s*(.+)$/gmu)) {
		rawPaths.push(match[1].trim());
	}
	return [...new Set(rawPaths.map((raw) => normalizeRepositoryPath(raw, root)).filter(Boolean))].sort();
}

function isHarness(file) {
	return (
		["AGENTS.md", "CLAUDE.md", ".pre-commit-config.yaml"].includes(file) ||
		file.startsWith(".agents/") ||
		file.startsWith(".claude/") ||
		file.startsWith(".codex/") ||
		file.startsWith(".github/workflows/") ||
		file.startsWith("scripts/agent_harness/") ||
		file === "docs/engineering/agent-harness.md"
	);
}

function isTest(file) {
	return /(?:^|\/)(?:tests?\/|[^/]+\.(?:test|spec)\.(?:js|jsx|mjs|ts|tsx)$)/u.test(file);
}

function isDocumentation(file) {
	return /\.(?:md|rst|txt)$/u.test(file);
}

function isStyle(file) {
	return file.startsWith("src/styles/") || file === "DESIGN.md";
}

export function classifyDiff(files) {
	if (files.length === 0) return "none";
	if (files.every((file) => isDocumentation(file) && !isHarness(file) && !isStyle(file))) return "docs";
	if (
		files.some(isStyle) &&
		files.every((file) => isStyle(file) || isHarness(file) || (isDocumentation(file) && !isTest(file)))
	) {
		return "styles";
	}
	if (files.every((file) => isHarness(file) || (isDocumentation(file) && !isTest(file))) && files.some(isHarness)) {
		return "harness";
	}
	if (
		files.every((file) => isTest(file) || (isDocumentation(file) && !isHarness(file) && !isStyle(file))) &&
		files.some(isTest)
	) {
		return "tests";
	}
	return "source";
}

export function verificationCommands(level, files) {
	if (["none", "docs"].includes(level)) return [];
	if (level === "harness") return [["bun", "run", "harness:check"]];
	if (level === "styles") {
		return [
			["bun", "run", "check"],
			["bun", "run", "audit:tokens"],
			["bun", "run", "build:tokens:check"],
		];
	}
	if (level === "source") return [["bun", "run", "check"]];

	const testFiles = files.filter((file) => isTest(file) && /\.(?:js|jsx|mjs|ts|tsx)$/u.test(file));
	const commands = [];
	if (testFiles.length > 0) {
		commands.push(["bunx", "biome", "check", ...testFiles]);
		commands.push(["bunx", "vitest", "run", ...testFiles]);
	} else {
		commands.push(["bun", "run", "test:unit"]);
	}
	commands.push(["bun", "run", "type"]);
	return commands;
}

async function runVerification(root, level, files) {
	const transcripts = [];
	for (const [command, ...args] of verificationCommands(level, files)) {
		const result = run(command, args, root);
		transcripts.push(`$ ${[command, ...args].join(" ")}\n${result.stdout ?? ""}${result.stderr ?? ""}`.trim());
		if (result.status !== 0) return { ok: false, summary: transcripts.join("\n\n").slice(-MAX_FEEDBACK) };
	}
	return { ok: true, summary: transcripts.join("\n\n").slice(-MAX_FEEDBACK) };
}

function receiptPath(root, digest) {
	return path.join(root, CACHE_DIRECTORY, `${digest}.json`);
}

export async function stopDecision({ payload, root, files, digest, verifier = runVerification }) {
	if (files.length === 0) return {};
	const receipt = receiptPath(root, digest);
	if (existsSync(receipt)) return {};
	const level = classifyDiff(files);
	const result = await verifier(root, level, files);
	if (result.ok) {
		await mkdir(path.dirname(receipt), { recursive: true });
		await writeFile(
			receipt,
			`${JSON.stringify({ digest, level, files, verifiedAt: new Date().toISOString() }, null, 2)}\n`,
			"utf8",
		);
		return {};
	}
	if (payload?.stop_hook_active === true) {
		return {
			systemMessage:
				`Verification still fails after the Stop retry. You may finish, but the final response must report this failure explicitly.\n\n${result.summary}`.slice(
					-MAX_FEEDBACK,
				),
		};
	}
	return {
		decision: "block",
		reason: `Changed-scope verification (${level}) failed. Fix it and retry.\n\n${result.summary}`.slice(-MAX_FEEDBACK),
	};
}

function changedPaths(root) {
	const result = run("git", ["diff", "--name-only", "--diff-filter=ACDMRT", "HEAD"], root);
	if (result.status !== 0) throw new Error(result.stderr?.trim() || "unable to inspect git diff");
	return result.stdout.split(/\r?\n/u).filter(Boolean).sort();
}

function diffDigest(root) {
	const result = run("git", ["diff", "--binary", "HEAD"], root, { binary: true });
	if (result.status !== 0) throw new Error(result.stderr?.toString().trim() || "unable to hash git diff");
	return createHash("sha256").update(result.stdout).digest("hex");
}

async function postEdit(payload, root) {
	const files = extractEditedFiles(payload, root).filter(
		(file) => EDITABLE_EXTENSIONS.has(path.extname(file)) && existsSync(path.join(root, file)),
	);
	if (files.length === 0) return { ok: true, summary: "No reliably parsed editable file." };
	const result = run("bunx", ["biome", "check", "--write", ...files], root);
	return {
		ok: result.status === 0,
		summary: `${result.stdout ?? ""}${result.stderr ?? ""}`.slice(-MAX_FEEDBACK),
	};
}

function emit(value) {
	process.stdout.write(`${JSON.stringify(value)}\n`);
}

async function main() {
	const eventIndex = process.argv.indexOf("--event");
	const event = eventIndex >= 0 ? process.argv[eventIndex + 1] : "";
	const root = gitRoot();
	let payload = {};
	if (event !== "check-changed") {
		try {
			const input = await readFile(0, "utf8");
			payload = input.trim() ? JSON.parse(input) : {};
		} catch (error) {
			emit({ systemMessage: `Ditto App hook received invalid JSON: ${error.message}` });
			process.exitCode = 1;
			return;
		}
	}

	if (event === "pre-tool") {
		const violation = policyViolation(commandFromPayload(payload), currentBranch(root));
		emit(violation ? { decision: "block", reason: violation } : {});
		return;
	}
	if (event === "post-tool") {
		const result = await postEdit(payload, root);
		emit(result.ok ? {} : { decision: "block", reason: `File-scoped Biome failed:\n${result.summary}` });
		return;
	}

	const files = changedPaths(root);
	if (event === "check-changed") {
		const result = await runVerification(root, classifyDiff(files), files);
		process.stdout.write(`${result.summary || "No changed-scope verification required."}\n`);
		process.exitCode = result.ok ? 0 : 1;
		return;
	}
	if (event !== "stop") {
		throw new Error(`unknown hook event: ${event}`);
	}
	const digest = files.length > 0 ? diffDigest(root) : createHash("sha256").update("").digest("hex");
	emit(await stopDecision({ payload, root, files, digest }));
}

if (import.meta.main) {
	await main();
}
